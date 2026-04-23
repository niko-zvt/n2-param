"""
Helpers for embedded matplotlib: keep figure dimensions aligned with the Qt canvas.
"""

from __future__ import annotations

import logging

from matplotlib.backend_bases import Event
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)


def bind_figure_size_to_canvas(figure: Figure, canvas: FigureCanvasQTAgg) -> None:
    """
    Tie figure size in inches to the canvas widget pixel size so the plot uses the available area.

    The canvas resize_event fires when the parent layout or window changes, matching window sizing.

    Args:
        figure: The matplotlib figure to resize.
        canvas: Qt widget hosting that figure.
    """
    if not isinstance(figure, Figure):
        raise TypeError("figure must be matplotlib.figure.Figure")
    if not isinstance(canvas, FigureCanvasQTAgg):
        raise TypeError("canvas must be FigureCanvasQTAgg")

    def on_resize(_event: Event | None) -> None:
        width_px = int(canvas.width())
        height_px = int(canvas.height())
        if width_px < 1 or height_px < 1:
            return
        w_in = width_px / float(figure.get_dpi())
        h_in = height_px / float(figure.get_dpi())
        figure.set_size_inches(w_in, h_in, forward=False)
        if canvas is not None:
            canvas.draw_idle()

    _ = canvas.mpl_connect("resize_event", on_resize)
    logger.debug("Bound figure to canvas for responsive sizing")
