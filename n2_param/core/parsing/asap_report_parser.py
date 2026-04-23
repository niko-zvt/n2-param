"""
Parse Micromeritics ASAP plain-text exports into ParsedReport objects.

Handles page breaks, repeated headers, and summary sections.
"""

from __future__ import annotations

import re
from typing import Final

from n2_param.core.models import (
    AnalysisLogRow,
    BJHDesorptionRow,
    ParsedReport,
    SummaryMetrics,
)

_ANALYSIS_LOG_LINE: Final[re.Pattern[str]] = re.compile(r"^\s*ANALYSIS LOG\s*$", re.MULTILINE)
_FLOAT_RE: Final[str] = r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
_DATA_ROW_RE: Final[re.Pattern[str]] = re.compile(
    rf"^\s+(?P<a>{_FLOAT_RE})\s+(?P<b>{_FLOAT_RE})\s+(?P<c>{_FLOAT_RE})\s",
)


class AsapReportParser:
    """Stateful parser for a single ASAP document string."""

    def parse(self, text: str) -> ParsedReport:
        """
        Parse full report text.

        Args:
            text: Raw ASAP export as a single string.

        Returns:
            ParsedReport with extracted tables and metrics.

        Raises:
            ValueError: If text is empty after stripping.
        """
        if not isinstance(text, str):
            raise TypeError("text must be str")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            raise ValueError("text is empty")

        warnings: list[str] = []
        sample_id = self._parse_sample_id(normalized)
        analysis_log = self._parse_merged_analysis_log(normalized, warnings)
        bjh_rows = self._parse_bjh_desorption_distribution(normalized, warnings)
        summary = self._parse_summary_metrics(normalized, warnings)

        return ParsedReport(
            sample_id=sample_id,
            analysis_log=tuple(analysis_log),
            bjh_desorption_rows=tuple(bjh_rows),
            summary=summary,
            warnings=tuple(warnings),
        )

    def _parse_sample_id(self, text: str) -> str | None:
        """Extract SAMPLE ID field from the header block."""
        match = re.search(r"^\s*SAMPLE ID:\s*(.+?)\s+COMPL\b", text, re.MULTILINE)
        if match is not None:
            return match.group(1).strip()
        fallback = re.search(r"^\s*SAMPLE ID:\s*(.+?)\s*$", text, re.MULTILINE)
        if fallback is None:
            return None
        return fallback.group(1).strip()

    def _parse_merged_analysis_log(self, text: str, warnings: list[str]) -> list[AnalysisLogRow]:
        """Merge ANALYSIS LOG tables across page breaks into one chronological series."""
        matches = list(_ANALYSIS_LOG_LINE.finditer(text))
        if not matches:
            warnings.append("missing_analysis_log_section")
            return []

        rows: list[AnalysisLogRow] = []
        saw_column_header = False

        for index, match in enumerate(matches):
            block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            block = text[match.end() : block_end]
            header_match = re.search(
                r"RELATIVE\s+PRESSURE.*?VOL ADSORBED",
                block,
                flags=re.DOTALL,
            )
            if header_match is None:
                continue

            saw_column_header = True
            after_header = block[header_match.end() :]
            for raw_line in after_header.splitlines():
                line = raw_line.rstrip("\n")
                if not line.strip():
                    continue
                m = _DATA_ROW_RE.match(line)
                if m is None:
                    continue
                rel = float(m.group("a"))
                p_mm = float(m.group("b"))
                vol = float(m.group("c"))
                rows.append(
                    AnalysisLogRow(
                        relative_pressure=rel,
                        pressure_mmhg=p_mm,
                        vol_adsorbed_cc_g_stp=vol,
                    )
                )

        if not rows:
            if saw_column_header:
                warnings.append("analysis_log_has_no_numeric_rows")
            else:
                warnings.append("analysis_log_header_not_found")
        return rows

    def _parse_bjh_data_rows_in_block(self, block: str) -> list[BJHDesorptionRow]:
        """
        Read numeric BJH desorption table rows from one text block (header already skipped).

        Args:
            block: A slice of the report that starts with the BJH distribution marker line.

        Returns:
            One ``BJHDesorptionRow`` for each data line.
        """
        rows: list[BJHDesorptionRow] = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if "PORE DIAMETER" in line or ("RANGE" in line and "DIAMETER" in line):
                continue
            if "(A )" in line or "(cc/g)" in line or "(sq." in line:
                continue

            nums = [float(x) for x in re.findall(_FLOAT_RE, line)]
            if len(nums) < 7:
                continue
            low, high, avg, iv, cv, ia, ca = nums[:7]
            rows.append(
                BJHDesorptionRow(
                    pore_diameter_low_a=low,
                    pore_diameter_high_a=high,
                    average_diameter_a=avg,
                    incremental_pore_volume_cc_g=iv,
                    cumulative_pore_volume_cc_g=cv,
                    incremental_pore_area_sq_m_g=ia,
                    cumulative_pore_area_sq_m_g=ca,
                )
            )
        return rows

    def _parse_bjh_desorption_distribution(
        self,
        text: str,
        warnings: list[str],
    ) -> list[BJHDesorptionRow]:
        """
        Parse BJH DESORPTION PORE DISTRIBUTION REPORT tabular data.

        Continuations on later pages (repeated report title) are concatenated, like
        the merged ANALYSIS LOG.
        """
        marker = "BJH DESORPTION PORE DISTRIBUTION REPORT"
        block_starts = [m.start() for m in re.finditer(re.escape(marker), text)]
        if not block_starts:
            warnings.append("missing_bjh_desorption_distribution")
            return []

        out: list[BJHDesorptionRow] = []
        end_of_last_markers: tuple[str, ...] = (
            "\f",
            "SUMMARY REPORT",
            "BJH ADSORPTION PORE DISTRIBUTION REPORT",
        )
        mlen = len(marker)
        for bi, start in enumerate(block_starts):
            if bi + 1 < len(block_starts):
                block = text[start : block_starts[bi + 1]]
            else:
                rest = text[start:]
                cut = len(rest)
                for em in end_of_last_markers:
                    pos = rest.find(em, mlen)
                    if pos > 0:
                        cut = min(cut, pos)
                block = rest[:cut]
            out.extend(self._parse_bjh_data_rows_in_block(block))
        if not out:
            warnings.append("bjh_desorption_distribution_has_no_rows")
        return out

    def _parse_summary_metrics(self, text: str, warnings: list[str]) -> SummaryMetrics:
        """Extract selected BJH desorption summary lines under SUMMARY REPORT."""
        surface = self._parse_line_after_heading(
            text,
            heading="BJH CUMULATIVE DESORPTION SURFACE AREA OF PORES",
            warning_key="missing_bjh_desorption_surface_area",
            warnings=warnings,
        )
        volume = self._parse_line_after_heading(
            text,
            heading="BJH CUMULATIVE DESORPTION PORE VOLUME OF PORES",
            warning_key="missing_bjh_desorption_pore_volume",
            warnings=warnings,
        )
        diameter = self._parse_value_same_line(
            text,
            pattern=rf"BJH DESORPTION AVERAGE PORE DIAMETER.*?:\s*({_FLOAT_RE})",
            warning_key="missing_bjh_desorption_avg_pore_diameter",
            warnings=warnings,
        )
        return SummaryMetrics(
            bjh_cumulative_desorption_surface_area_sq_m_g=surface,
            bjh_cumulative_desorption_pore_volume_cc_g=volume,
            bjh_desorption_average_pore_diameter_a=diameter,
        )

    def _parse_line_after_heading(
        self,
        text: str,
        heading: str,
        warning_key: str,
        warnings: list[str],
    ) -> float | None:
        """Read numeric value from the BETWEEN ... DIAMETER: line following a heading."""
        idx = text.find(heading)
        if idx < 0:
            warnings.append(warning_key)
            return None
        tail = text[idx:]
        next_lines = tail.splitlines()
        for line in next_lines[1:5]:
            match = re.search(rf"DIAMETER:\s*({_FLOAT_RE})", line)
            if match is not None:
                return float(match.group(1))
        warnings.append(warning_key)
        return None

    def _parse_value_same_line(
        self,
        text: str,
        pattern: str,
        warning_key: str,
        warnings: list[str],
    ) -> float | None:
        """Find a numeric capture on the same line as a distinctive label."""
        regex = re.compile(pattern, re.MULTILINE)
        match = regex.search(text)
        if match is None:
            warnings.append(warning_key)
            return None
        return float(match.group(1))