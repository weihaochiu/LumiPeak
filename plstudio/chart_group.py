"""Compose independent, physically sized figures in a scrollable Qt group."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from .figure_style import figure_size, save_figure
from .i18n import tr
from .chart_settings import chart_settings


@dataclass
class Chart:
    key: str
    title: str
    figure: Figure
    settings: dict


def render_charts(primary, kind, spectra, settings):
    """Render one full-size figure per DATA, overlay mode or trend metric.

    Each renderer receives just one plot request. The group never changes a
    figure's dimensions, font sizes, line widths, or axes positions.
    """
    from .plotting import DEFAULT_STYLE, draw_spectra, _add_fit_summary
    from .overlay import DEFAULT_OVERLAY, draw_overlay
    from .trends import DEFAULT_TRENDS, METRICS, draw_trends, prepare_trends
    charts, prepared = [], None
    if kind == "trends":
        defaults = DEFAULT_STYLE | DEFAULT_TRENDS | settings
        prepared = prepare_trends(spectra, defaults)
        requests = [("trend:"+key, tr(METRICS[key][0]), defaults | {"view": key}, None, i)
                    for i, key in enumerate(prepared["metrics"], 1)]
    elif kind == "overlay":
        defaults = DEFAULT_STYLE | DEFAULT_OVERLAY | settings
        modes = ["raw", "normalized"] if defaults["intensity"] == "both" else [defaults["intensity"]]
        requests = [("overlay:"+mode, tr("原始 Intensity（Counts）") if mode == "raw" else "Normalized intensity",
                     defaults | {"intensity": mode}, None, 1 if mode == "raw" else 2) for mode in modes]
    else:
        defaults = DEFAULT_STYLE | settings
        requests = [("spectrum:"+s.id, s.name, defaults | {"fit_summary": True}, s, 1) for s in spectra if s.plot]
        if not requests:
            requests = [("spectrum:empty", tr("尚未匯入資料"), defaults, None, 1)]
    for key, title, style, spectrum, source_index in requests:
        style = chart_settings(style, key)
        # Preserve old numeric layer overrides when a former subplot becomes
        # its own figure. New edits use semantic keys and survive reordering.
        layers = style.get("figure_options", {}).get("layers", {})
        if key not in layers and str(source_index) in layers:
            layers[key] = copy.deepcopy(layers[str(source_index)])
        figure = primary if not charts else Figure(facecolor="white")
        figure.set_size_inches(figure_size(style))
        if kind == "trends":
            draw_trends(figure, spectra, style, style.get("font", "Arial"))
        elif kind == "overlay":
            draw_overlay(figure, spectra, style)
        else:
            ax, _ = draw_spectra(figure, [spectrum] if spectrum else [], style)
            if spectrum:
                _add_fit_summary(figure, ax, spectrum, style)
        charts.append(Chart(key, title, figure, style))
    if kind == "overlay" and settings.get("figure_options", {}).get("share_x") and charts:
        for chart in charts[1:]:
            chart.figure.axes[0].sharex(charts[0].figure.axes[0])
    return charts, prepared


def export_chart_group(directory, kind, spectra, settings, extension="png"):
    from .exporting import _available_image_path
    if extension not in ("png", "jpg", "pdf", "svg"):
        raise ValueError(tr("不支援的圖形格式。"))
    charts, _ = render_charts(Figure(), kind, spectra, settings)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, chart in enumerate(charts, 1):
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", chart.title).strip(" .")[:80] or "Plot"
        path = _available_image_path(directory, f"{index:03d}_{stem}", extension)
        save_figure(chart.figure, path, chart.settings)
        paths.append(path)
    return paths


class ChartToolbar(NavigationToolbar2QT):
    """Navigate a chart independently and save at its configured export DPI."""
    chart = None

    def save_figure(self, *args):
        if self.chart is None:
            return super().save_figure(*args)
        path, _ = QFileDialog.getSaveFileName(self, tr("匯出此張圖"), "PL_chart.png",
            "PNG (*.png);;JPEG (*.jpg);;PDF (*.pdf);;SVG (*.svg)")
        if path:
            before = self.chart.figure.get_size_inches().copy()
            try:
                self.chart.figure.set_size_inches(figure_size(self.chart.settings))
                save_figure(self.chart.figure, path, self.chart.settings)
            finally:
                self.chart.figure.set_size_inches(before)


class FigureGroup(QScrollArea):
    """Arrange fixed-size canvases; resizing the viewport only rearranges cards."""
    def __init__(self, primary_canvas, on_click=None, parent=None, navigation=None):
        super().__init__(parent)
        self.primary_canvas = primary_canvas
        self.on_click = on_click
        self.primary_navigation = navigation
        self.cards = []
        self.charts = []
        self.columns = 0
        self.setWidgetResizable(False)
        self.panel = QWidget()
        self.grid = QGridLayout(self.panel)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(14)
        self.setWidget(self.panel)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def set_charts(self, charts, columns=0):
        # Detach the reusable primary canvas before disposing its previous card.
        self.primary_canvas.setParent(self)
        if self.primary_navigation:
            self.primary_navigation.setParent(self)
        for card in self.cards:
            card.canvas._draw_pending = False
            self.grid.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards = []
        self.charts = charts
        self.columns = columns
        for chart in charts:
            card = QWidget()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(chart.title)
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(label)
            logical_dpi = self.logicalDpiX()
            width, height = figure_size(chart.settings)
            chart.figure.set_size_inches(width, height)
            if chart.figure is self.primary_canvas.figure:
                canvas = self.primary_canvas
                chart.figure._original_dpi = logical_dpi
                chart.figure.set_dpi(logical_dpi*canvas.device_pixel_ratio)
            else:
                chart.figure.set_dpi(logical_dpi)
                canvas = FigureCanvasQTAgg(chart.figure)
            if canvas is not self.primary_canvas and self.on_click:
                canvas.mpl_connect("button_press_event", self.on_click)
            # Preview uses a fixed logical pixel density. Export DPI is kept in
            # settings and used only by exporters, never by group arrangement.
            canvas.setFixedSize(round(width*logical_dpi), round(height*logical_dpi))
            if canvas is self.primary_canvas:
                if self.primary_navigation is None:
                    self.primary_navigation = ChartToolbar(canvas, card)
                navigation = self.primary_navigation
            else:
                navigation = ChartToolbar(canvas, card)
            navigation.chart = chart
            navigation.update()
            layout.addWidget(navigation)
            layout.addWidget(canvas)
            # Reparenting the reusable widgets hides them in Qt. Restore their
            # explicit visibility before adding the card to a visible group.
            navigation.show()
            canvas.show()
            card.setFixedSize(canvas.width(), canvas.height()+label.sizeHint().height()+navigation.sizeHint().height()+2*layout.spacing())
            card.canvas = canvas
            card.navigation = navigation
            self.cards.append(card)
            canvas.draw_idle()
        self._arrange()

    def pause_drawing(self):
        """Discard queued redraws when these canvases are no longer visible."""
        self.primary_canvas._draw_pending = False
        for card in self.cards:
            card.canvas._draw_pending = False

    def _arrange(self):
        left, top, right, bottom = self.grid.getContentsMargins()
        if not self.cards:
            self.panel.setFixedSize(left+right, top+bottom)
            return
        width = max(card.width() for card in self.cards)
        columns = self.columns or max(1, (self.viewport().width()-16+self.grid.spacing())//(width+self.grid.spacing()))
        columns = max(1, min(columns, len(self.cards)))
        rows = (len(self.cards)+columns-1)//columns
        column_widths = [0]*columns
        row_heights = [0]*rows
        for i, card in enumerate(self.cards):
            row, column = divmod(i, columns)
            self.grid.addWidget(card, row, column, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            card.show()
            column_widths[column] = max(column_widths[column], card.width())
            row_heights[row] = max(row_heights[row], card.height())
        # sizeHint() excludes newly inserted widgets until Qt processes their
        # Show events. Reading it here could fix the entire panel at 16 x 16
        # (only the margins), clipping every otherwise valid chart. Compute the
        # extent from the already fixed card sizes, independent of event timing.
        self.panel.setFixedSize(left+right+sum(column_widths)+self.grid.spacing()*(columns-1),
                                top+bottom+sum(row_heights)+self.grid.spacing()*(rows-1))
        self.grid.activate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "cards"):
            self._arrange()

    def hideEvent(self, event):
        self.pause_drawing()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._arrange()
        for card in self.cards:
            card.canvas.draw_idle()
