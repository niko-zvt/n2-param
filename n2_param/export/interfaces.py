"""
Abstract and concrete entry points for writing structured ASAP exports to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from n2_param.core.models import ParsedReport
from n2_param.export.sheet_export import LabelGet, export_parsed_to_file


class ExportSink(Protocol):
    """
    Target for writing one parsed report; callers provide display name and i18n lookup for table labels.
    """

    def export_parsed_report(
        self,
        target_path: Path,
        report: ParsedReport,
        *,
        display_name: str,
        label: LabelGet,
    ) -> None:
        """Write ``report`` to ``target_path`` in the format implied by the file extension."""
        ...


class FileExportSink:
    """
    Implement ``ExportSink`` using the bundled sheet layout: ``.xlsx`` or ``.csv`` (semicolon, quoted).
    """

    def export_parsed_report(
        self,
        target_path: Path,
        report: ParsedReport,
        *,
        display_name: str,
        label: LabelGet,
    ) -> None:
        """
        Persist a parsed report to a file.

        Parameters:
            target_path: Destination; extension must be ``.xlsx`` or ``.csv``.
            report: Parsed data.
            display_name: File title row (e.g. sample name).
            label: i18n lookup for ``export.*`` keys (returns UTF-8 text).

        Raises:
            TypeError: If a parameter has an invalid type.
            ValueError: If the file extension is unknown.
        """
        export_parsed_to_file(
            target_path=target_path,
            report=report,
            display_name=display_name,
            label=label,
        )
