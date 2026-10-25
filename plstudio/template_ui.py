"""Per-figure templates, with a dedicated formatting window and preview."""
from __future__ import annotations

from .i18n import tr

import copy
import json
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
    QTreeWidget, QTreeWidgetItem, QStackedWidget)

from .data import write_json
from .figure_style import DEFAULT_OPTIONS, validate_options, plot_items, layer_key
from .origin_format import (PropertyTabs, LAYER_SECTIONS, PLOT_SECTIONS, AxisDialog,
                            axis_defaults, ColorEdit, AXIS_SIDES, axis_direction, PAGE_SECTIONS)
from .chart_group import FigureGroup, Chart
from .chart_settings import chart_settings, validate_chart_styles
from .plotting import DEFAULT_STYLE
from .trends import DEFAULT_TRENDS, METRICS
from .trend_ui import update_position_choices
from .overlay import DEFAULT_OVERLAY

KINDS = {"spectrum": "光譜／擬合圖", "overlay": "PL 疊圖", "trends": "Condition 趨勢圖"}

# key, user-facing name, widget type (list means a choice selector)
SECTIONS = {
    "頁面／圖層": [
        ("orientation", "頁面方向", ["custom", "portrait", "landscape"]), ("page_color", "頁面顏色", str),
        ("layer_color", "繪圖區背景", str), ("layout_mode", "版面配置", ["tight", "manual"]),
        ("columns", "多面板欄數（0＝自動）", int), ("left", "左邊界（頁面比例）", float),
        ("right", "右邊界", float), ("bottom", "下邊界", float), ("top", "上邊界", float),
        ("hspace", "面板上下間距", float), ("wspace", "面板左右間距", float),
        ("share_x", "連結疊圖 X 軸", bool),
        ("panel_labels", "面板編號", bool), ("panel_label_style", "編號形式", ["a", "A", "1"]),
        ("panel_label_x", "編號 X 位置（圖層比例）", float), ("panel_label_y", "編號 Y 位置", float)],
    "座標軸": [
        ("xscale", "X 尺度", ["linear", "log", "symlog"]), ("yscale", "Y 尺度", ["linear", "log", "symlog"]),
        ("reverse_x", "反轉 X 軸", bool), ("reverse_y", "反轉 Y 軸", bool),
        ("axis_color", "軸線顏色", str), ("axis_width", "軸線寬度 pt", float),
        ("top_axis", "顯示上軸", bool), ("right_axis", "顯示右軸", bool),
        ("x_label_size", "X 標題字級", float), ("y_label_size", "Y 標題字級", float),
        ("title_size", "圖標題字級", float), ("tick_size", "刻度字級", float),
        ("font_weight", "文字粗細", ["normal", "bold"]), ("text_color", "標題文字顏色", str),
        ("label_pad", "標題與軸距離 pt", float)],
    "刻度／格線": [
        ("tick_direction", "刻度方向", ["in", "out", "inout"]), ("major_length", "主刻度長度 pt", float),
        ("minor_length", "次刻度長度 pt", float), ("tick_width", "刻度線寬 pt", float),
        ("x_major_step", "X 主刻度間隔（0＝自動）", float), ("y_major_step", "Y 主刻度間隔", float),
        ("x_major_count", "X 自動刻度數", int), ("y_major_count", "Y 自動刻度數", int),
        ("minor_ticks", "顯示次刻度", bool), ("minor_divisions", "主刻度間細分數", int),
        ("x_rotation", "X 刻度旋轉角度", float), ("y_rotation", "Y 刻度旋轉角度", float),
        ("x_format", "X 數值格式", ["auto", "fixed", "scientific", "plain"]),
        ("y_format", "Y 數值格式", ["auto", "fixed", "scientific", "plain"]), ("decimals", "固定小數位數", int),
        ("special_x_ticks", "指定 X 刻度（逗號分隔）", list), ("special_y_ticks", "指定 Y 刻度", list),
        ("minor_grid", "顯示次格線", bool), ("grid_color", "格線顏色", str),
        ("grid_width", "格線寬度 pt", float), ("grid_style", "格線形式", ["-", "--", ":", "-."]),
        ("grid_alpha", "格線不透明度", float)],
    "線條／符號": [
        ("palette", "配色", ["preserve", "tab10", "Set2", "Dark2", "viridis", "plasma", "Greys"]),
        ("line_style", "全圖線型", ["preserve", "-", "--", "-.", ":", "None"]),
        ("line_alpha", "曲線不透明度", float),
        ("marker", "符號", ["preserve", "None", "o", "s", "^", "v", "D", "x", "+", "*"]),
        ("marker_size", "符號大小 pt", float), ("marker_face", "符號填色（auto 沿用）", str),
        ("marker_edge", "符號邊色", str), ("marker_edge_width", "符號邊線寬 pt", float),
        ("bar_edge", "長條邊線顏色", str), ("bar_hatch", "長條填紋（如 / 或 x）", str), ("bar_alpha", "長條不透明度", float),
        ("error_width", "誤差棒線寬 pt", float), ("error_capsize", "誤差棒端帽長度 pt", float)],
    "圖例": [
        ("legend_loc", "位置", ["best", "upper right", "upper left", "lower left", "lower right", "center left", "center right", "upper center", "lower center", "center"]),
        ("legend_columns", "欄數", int), ("legend_frame", "顯示邊框", bool),
        ("legend_alpha", "背景不透明度", float), ("legend_size", "字級 pt", float),
        ("legend_title", "圖例標題", str), ("legend_outside", "移到圖層右側外部", bool),
        ("legend_reverse", "反轉順序", bool), ("legend_face", "背景顏色", str),
        ("legend_edge", "邊框顏色", str), ("legend_spacing", "列間距", float)],
    "參考線／Inset": [
        ("reference_x", "垂直參考線（X 值）", list), ("reference_y", "水平參考線（Y 值）", list),
        ("reference_color", "參考線顏色", str), ("reference_style", "參考線型", ["--", "-", ":", "-."]),
        ("inset", "顯示局部放大圖", bool), ("inset_layer", "放大圖來源面板編號", int),
        ("inset_box", "放大圖位置 L,B,W,H（比例）", list),
        ("inset_xlim", "放大 X 範圍（下限,上限）", list), ("inset_ylim", "放大 Y 範圍", list),
        ("inset_connectors", "顯示放大區連接線", bool)],
    "輸出": [
        ("transparent", "透明背景（PNG／SVG／PDF）", bool),
        ("tight_export", "裁切至內容（改變輸出實際尺寸）", bool),
        ("export_pad", "裁切留白 inch", float), ("jpeg_quality", "JPEG 品質 1–100", int)],
}


class FigureTemplateDialog(QDialog):
    applied = Signal(object)

    def __init__(self, parent, preview_callback):
        super().__init__(parent)
        self.setWindowTitle(tr("Plot Details — 圖片設定"))
        self.resize(1400, 900)
        self.preview_callback = preview_callback
        self.loading = False
        self.drafts = {}
        self.active_kind = None
        self.widgets, self.option_widgets = {}, {}
        self.field_labels = {}
        self.forms = {}
        self.scope = None
        self.scope_layers = {}
        self.chart_styles = {}
        self.tree_signature = None
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("圖型")))
        self.kind = QComboBox()
        for key, label in KINDS.items():
            self.kind.addItem(tr(label), key)
        self.kind.currentIndexChanged.connect(self._switch_kind)
        top.addWidget(self.kind)
        top.addWidget(QLabel(tr("每種圖分別保存；同一個設定檔可包含全部圖型。")))
        top.addStretch()
        layout.addLayout(top)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.object_tree = QTreeWidget()
        self.object_tree.setHeaderLabel(tr("Page / Layer / Plot"))
        self.object_tree.setMinimumWidth(200)
        self.object_tree.currentItemChanged.connect(self._select_object)
        self.object_tree.itemChanged.connect(self._object_visibility)
        splitter.addWidget(self.object_tree)
        self.figure = Figure(figsize=(8, 6), facecolor="white")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.preview_figures = [self.figure]
        self.preview_charts = []
        self.preview_group = FigureGroup(self.canvas, self._preview_double_click)
        self.tabs = QTabWidget()
        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self.tabs)
        self.layer_editor = PropertyTabs(LAYER_SECTIONS)
        self.plot_editor = PropertyTabs(PLOT_SECTIONS)
        self.page_editor = PropertyTabs(PAGE_SECTIONS)
        self.layer_editor.changed.connect(self.preview)
        self.plot_editor.changed.connect(self.preview)
        self.page_editor.changed.connect(self.preview)
        self.editor_stack.addWidget(self.layer_editor)
        self.editor_stack.addWidget(self.plot_editor)
        self.editor_stack.addWidget(self.page_editor)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        self.selection_label = QLabel()
        controls_layout.addWidget(self.selection_label)
        self.axes_button = QPushButton(tr("Axes..."))
        self.axes_button.clicked.connect(self.open_axes)
        controls_layout.addWidget(self.axes_button)
        controls_layout.addWidget(self.editor_stack, 1)
        self.reset_button = QPushButton(tr("重設選取物件格式"))
        self.reset_button.clicked.connect(self.reset_object)
        controls_layout.addWidget(self.reset_button)
        splitter.addWidget(controls)
        splitter.addWidget(self.preview_group)
        splitter.setSizes([240, 580, 580])
        self.canvas.mpl_connect("button_press_event", self._preview_double_click)
        layout.addWidget(splitter, 1)
        base = self._tab("基本／內容")
        for key, label, typ in (
            ("width_cm", tr("寬 cm"), float), ("height_cm", tr("高 cm"), float), ("dpi", "DPI", int),
            ("font", tr("字型"), str), ("font_size", tr("基本字級 pt"), float), ("line_width", tr("線寬 pt"), float),
            ("title", tr("圖標題"), str), ("xlabel", tr("X 軸標題（留白自動）"), str),
            ("ylabel", tr("Y 軸標題（單面板）"), str), ("xmin", tr("X 下限（留白自動）"), "optional"),
            ("xmax", tr("X 上限"), "optional"), ("ymin", tr("Y 下限（單面板）"), "optional"),
            ("ymax", tr("Y 上限"), "optional"), ("legend", tr("顯示圖例"), bool), ("grid", tr("顯示主格線"), bool)):
            self.widgets[key] = self._field(base, key, label, typ)
        self.content = self._tab("圖型專用")
        self.specific_widgets = {}
        for key, label, typ in (
            ("raw", tr("原始光譜"), bool), ("fit", tr("總擬合線"), bool), ("components", tr("分峰線"), bool),
            ("background", tr("背景線"), bool), ("residual", tr("殘差面板"), bool), ("normalize", tr("光譜圖歸一化"), bool),
            ("intensity", tr("疊圖顯示"), ["both", "raw", "normalized"]),
            ("export_mode", tr("疊圖輸出"), ["separate", "raw", "normalized", "both", "current"]),
            ("plot_type", tr("趨勢圖型"), ["dot", "line", "dot-line", "bar", "area"]),
            ("peak", tr("趨勢 Peak 編號"), int), ("view", tr("趨勢顯示"), ["overview", *METRICS]),
            ("x_mode", tr("Condition 座標"), ["category", "numeric", "auto"]),
            ("errorbars", tr("趨勢誤差棒"), bool), ("annotate", tr("趨勢資料名稱"), bool),
            ("bar_width", tr("長條寬度（間距比例）"), float)):
            self.specific_widgets[key] = self._field(self.content, key, label, typ)
        self.metric_checks = {}
        for key, definition in METRICS.items():
            check = QCheckBox(tr(definition[0]))
            check.toggled.connect(self.preview)
            self.content.addRow(check)
            self.metric_checks[key] = check
        view = self.specific_widgets["view"]
        view.blockSignals(True)
        view.clear()
        view.addItem(tr("總覽：同時顯示勾選指標"), "overview")
        for key, definition in METRICS.items():
            view.addItem(tr(definition[0]), key)
        view.setProperty("metric_selector", True)
        view.blockSignals(False)
        for title, fields in SECTIONS.items():
            form = self._tab(title)
            for key, label, typ in fields:
                self.option_widgets[key] = self._field(form, key, label, typ)
        # Keep page dimensions at page level and axis content with common axes.
        for key, target in {"title": "Legends/Titles", "legend": "Legends/Titles", "line_width": "Group",
                            "xlabel": "Axes", "ylabel": "Axes", "xmin": "Axes", "xmax": "Axes",
                            "ymin": "Axes", "ymax": "Axes", "grid": "Ticks / Grids"}.items():
            row = base.takeRow(self.widgets[key])
            self.forms[target].addRow(row.labelItem.widget(), row.fieldItem.widget())
        self.tables = {}
        self._object_table(tr("文字／箭頭"), "annotations", [tr("面板"), tr("文字"), "X", "Y", tr("箭頭目標 X"), tr("箭頭目標 Y"), tr("座標 axes/data"), tr("顏色"), tr("字級")])
        self._object_table(tr("形狀"), "shapes", [tr("面板"), "rectangle/ellipse", "X", "Y", tr("寬"), tr("高"), tr("座標 axes/data"), tr("填色"), tr("邊色"), tr("不透明度")])
        self._object_table(tr("各面板覆寫"), "layers", [tr("面板"), tr("X 下限"), tr("X 上限"), tr("Y 下限"), tr("Y 上限"), tr("X 標題"), tr("Y 標題"), tr("圖標題"), tr("位置 L"), tr("位置 B"), tr("位置 W"), tr("位置 H")])
        row = QHBoxLayout()
        self.copy_axis_content = QCheckBox(tr("套用每張圖時包含座標範圍與標題"))
        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel(tr("套用範圍")))
        self.apply_scope = QComboBox()
        self.apply_scope.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.apply_scope.addItem(tr("目前圖組的每張圖"), "current")
        self.apply_scope.addItem(tr("全部圖型的每張圖"), "all")
        scope_row.addWidget(self.apply_scope)
        scope_row.addWidget(self.copy_axis_content)
        scope_row.addStretch()
        layout.addLayout(scope_row)
        for label, slot in ((tr("OK"), self._accept_settings), (tr("Cancel"), self.close),
                            (tr("Apply"), lambda: self.apply(False)),
                            (tr("套用到每張圖"), self.apply_each_chart),
                            (tr("套用全部圖型設定"), lambda: self.apply(True)), (tr("儲存設定檔"), self.save_dialog),
                            (tr("載入設定檔"), self.load_dialog)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, callback=slot: callback())
            row.addWidget(button)
        layout.addLayout(row)
        self.notice = QLabel(tr("顏色可填名稱或 #RRGGBB；文字支援 Unicode 與 Matplotlib 數學標記。"))
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.axes_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.widgets["font_size"].valueChanged.connect(self._base_font_changed)

    def _base_font_changed(self, value):
        if self.loading:
            return
        for key in ("x_label_size", "y_label_size", "title_size", "tick_size", "legend_size"):
            widget = self.option_widgets[key]
            blocker = QSignalBlocker(widget)
            widget.setValue(value*.85 if key == "legend_size" else value)
            del blocker
        self.preview()

    def _tab(self, title):
        title = {"基本／內容": "Print/Dimensions", "圖型專用": "Plot Content", "頁面／圖層": "Layers",
                 "座標軸": "Axes", "刻度／格線": "Ticks / Grids", "線條／符號": "Group",
                 "圖例": "Legends/Titles", "參考線／Inset": "Inset", "輸出": "Export"}.get(title, title)
        area = QScrollArea()
        area.setWidgetResizable(True)
        widget = QWidget()
        form = QFormLayout(widget)
        self.forms[title] = form
        area.setWidget(widget)
        self.tabs.addTab(area, tr(title))
        return form

    def _field(self, form, key, label, typ):
        if isinstance(typ, list):
            widget = QComboBox()
            widget.addItems(typ)
            widget.currentIndexChanged.connect(self.preview)
        elif typ is bool:
            widget = QCheckBox()
            widget.toggled.connect(self.preview)
        elif typ in (int, float):
            widget = QSpinBox() if typ is int else QDoubleSpinBox()
            widget.setRange(-1000, 10000)
            if typ is float:
                widget.setDecimals(3)
            widget.valueChanged.connect(self.preview)
        else:
            widget = ColorEdit() if "color" in key or key in ("marker_face", "marker_edge", "bar_edge", "legend_face", "legend_edge") else QLineEdit()
            widget.editingFinished.connect(self.preview)
        widget.setProperty("field_type", "array" if typ is list else "optional" if typ == "optional" else "text")
        form.addRow(tr(label), widget)
        self.field_labels[widget] = form.labelForField(widget)
        return widget

    def _object_table(self, title, key, headers):
        form = self._tab(title)
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setMinimumHeight(250)
        table.itemChanged.connect(self.preview)
        form.addRow(table)
        buttons = QHBoxLayout()
        add, remove = QPushButton(tr("新增")), QPushButton(tr("移除選取列"))
        add.clicked.connect(lambda: self._add_table_row(key))
        remove.clicked.connect(lambda: self._remove_table_row(key))
        buttons.addWidget(add)
        buttons.addWidget(remove)
        form.addRow(buttons)
        self.tables[key] = table

    def _add_table_row(self, key):
        defaults = {"annotations": ["1", "Label", ".05", ".95", "", "", "axes", "black", "11"],
                    "shapes": ["1", "rectangle", ".2", ".2", ".2", ".2", "axes", "none", "black", ".5"],
                    "layers": ["1", "", "", "", "", "", "", "", "", "", "", ""]}
        self.loading = True
        table = self.tables[key]
        row = table.rowCount()
        table.insertRow(row)
        for column, value in enumerate(defaults[key]):
            table.setItem(row, column, QTableWidgetItem(value))
        self.loading = False
        self.preview()

    def _remove_table_row(self, key):
        row = self.tables[key].currentRow()
        if row >= 0:
            self.tables[key].removeRow(row)
            self.preview()

    def set_bundle(self, bundle, active="spectrum"):
        self.loading = True
        self.drafts = copy.deepcopy(bundle)
        self.active_kind = None
        self.kind.setCurrentIndex(self.kind.findData(active))
        self.loading = False
        self._switch_kind()

    def _switch_kind(self):
        if self.loading or not self.drafts:
            return
        if self.active_kind is not None:
            try:
                self.drafts[self.active_kind] = self.read_settings()
            except Exception as exc:
                self.notice.setText(str(exc))
                self.loading = True
                self.kind.setCurrentIndex(self.kind.findData(self.active_kind))
                self.loading = False
                return
        self.active_kind = self.kind.currentData()
        self._load_form(self.drafts[self.active_kind])
        self.preview()

    def _set(self, widget, value):
        if isinstance(widget, QComboBox):
            if widget.property("metric_selector"):
                widget.setCurrentIndex(max(0, widget.findData(value)))
            else:
                widget.setCurrentText(str(value))
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.setValue(value)
        else:
            widget.setText(", ".join(str(v) for v in value) if isinstance(value, list) else "" if value is None else str(value))

    def _get(self, widget):
        if isinstance(widget, QComboBox):
            return widget.currentData() if widget.property("metric_selector") else widget.currentText()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            return widget.value()
        text = widget.text().strip()
        if widget.property("field_type") == "array":
            return [float(v.strip()) for v in text.replace("，", ",").split(",") if v.strip()]
        if widget.property("field_type") == "optional":
            return float(text) if text else None
        return text

    def _load_form(self, settings):
        self.loading = True
        if hasattr(self, "axis_dialog"):
            self.axis_dialog.close()
        self.scope = None
        self.scope_layers = copy.deepcopy(settings.get("figure_options", {}).get("layers", {}))
        self.chart_styles = copy.deepcopy(settings.get("chart_styles", {}))
        self.layer_table_snapshot = {str(k): {field: copy.deepcopy(v) for field, v in record.items()
                                    if field in ("xlim", "ylim", "position", "xlabel", "ylabel", "title")}
                                    for k, record in self.scope_layers.items() if str(k).isdigit()}
        self.tree_signature = None
        self.layer_editor.dirty.clear()
        self.plot_editor.dirty.clear()
        self.page_editor.dirty.clear()
        defaults = DEFAULT_STYLE | DEFAULT_OVERLAY | DEFAULT_TRENDS | settings
        options = validate_options(settings.get("figure_options", {}))
        for key, widget in self.widgets.items():
            self._set(widget, defaults.get(key, ""))
        spectrum = {"raw", "fit", "components", "background", "residual", "normalize"}
        overlay = {"intensity", "export_mode"}
        relevant = spectrum if self.active_kind == "spectrum" else overlay if self.active_kind == "overlay" else set(self.specific_widgets)-spectrum-overlay
        for key, widget in self.specific_widgets.items():
            self._set(widget, defaults.get(key, ""))
            widget.setVisible(key in relevant)
            self.content.labelForField(widget).setVisible(key in relevant)
        for key, widget in self.option_widgets.items():
            self._set(widget, options[key])
        for key, check in self.metric_checks.items():
            check.setChecked(key in defaults["metrics"])
            check.setVisible(self.active_kind == "trends")
        records = {"annotations": [], "shapes": [], "layers": []}
        for a in options["annotations"]:
            records["annotations"].append([a.get("layer", 1), a.get("text", ""), *a.get("xy", [0, 0]),
                                           *a.get("to", ["", ""]), a.get("coords", "axes"), a.get("color", "black"), a.get("size", 11)])
        for a in options["shapes"]:
            records["shapes"].append([a.get("layer", 1), a.get("type", "rectangle"), *a.get("xy", [0, 0]),
                                      a.get("width", .2), a.get("height", .2), a.get("coords", "axes"),
                                      a.get("face", "none"), a.get("edge", "black"), a.get("alpha", .5)])
        for layer, a in options["layers"].items():
            if not str(layer).isdigit():
                continue  # Named layers are edited in the object tree.
            records["layers"].append([layer, *a.get("xlim", ["", ""]), *a.get("ylim", ["", ""]),
                                      a.get("xlabel", ""), a.get("ylabel", ""), a.get("title", ""), *a.get("position", ["", "", "", ""])])
        for key, table in self.tables.items():
            table.setRowCount(len(records[key]))
            for row, values in enumerate(records[key]):
                for column, value in enumerate(values):
                    table.setItem(row, column, QTableWidgetItem(str(value)))
        self.loading = False

    def read_settings(self):
        if self.active_kind == "trends":
            update_position_choices(self.metric_checks, self.specific_widgets["view"],
                                    getattr(self.parent(), "spectra", []),
                                    self.specific_widgets["peak"].value(),
                                    self.drafts["trends"].get("include_failed", False),
                                    self.specific_widgets["errorbars"])
        self._refresh_dependencies()
        settings = copy.deepcopy(self.drafts[self.active_kind])
        settings.update({key: self._get(widget) for key, widget in self.widgets.items()})
        for key in ("width_cm", "height_cm", "dpi", "font_size", "line_width"):
            if not np.isfinite(settings[key]) or settings[key] <= 0:
                raise ValueError(tr('{0} 必須為正數。').format(key, ''))
        for lo, hi in (("xmin", "xmax"), ("ymin", "ymax")):
            if any(settings[k] is not None and not np.isfinite(settings[k]) for k in (lo, hi)):
                raise ValueError(tr("座標範圍必須是有限值。"))
            if settings[lo] is not None and settings[hi] is not None and settings[lo] >= settings[hi]:
                raise ValueError(tr("座標下限必須小於上限。"))
        specific = ({"raw", "fit", "components", "background", "residual", "normalize"} if self.active_kind == "spectrum"
                    else {"intensity", "export_mode"} if self.active_kind == "overlay"
                    else {"plot_type", "peak", "view", "x_mode", "errorbars", "annotate", "bar_width"})
        for key, widget in self.specific_widgets.items():
            if key in specific:
                settings[key] = self._get(widget)
        if self.active_kind == "trends":
            settings["metrics"] = [key for key, check in self.metric_checks.items() if check.isChecked()]
            settings["connect"] = settings["plot_type"] in ("line", "dot-line", "area")
        options = {key: self._get(widget) for key, widget in self.option_widgets.items()}
        self._commit_scope()
        options.update(annotations=[], shapes=[], layers=copy.deepcopy(self.scope_layers))
        table_layers = {}
        for key, table in self.tables.items():
            for row in range(table.rowCount()):
                cells = [table.item(row, c).text().strip() if table.item(row, c) else "" for c in range(table.columnCount())]
                layer = int(cells[0])
                if layer < 1:
                    raise ValueError(tr("面板編號需大於零。"))
                if key == "annotations":
                    record = {"layer": layer, "text": cells[1], "xy": [float(cells[2]), float(cells[3])],
                              "coords": cells[6], "color": cells[7], "size": float(cells[8])}
                    if cells[4] or cells[5]:
                        record["to"] = [float(cells[4]), float(cells[5])]
                    options[key].append(record)
                elif key == "shapes":
                    options[key].append({"layer": layer, "type": cells[1], "xy": [float(cells[2]), float(cells[3])],
                                         "width": float(cells[4]), "height": float(cells[5]), "coords": cells[6],
                                         "face": cells[7], "edge": cells[8], "alpha": float(cells[9])})
                else:
                    record = {}
                    for start, name in ((1, "xlim"), (3, "ylim"), (8, "position")):
                        length = 4 if name == "position" else 2
                        if any(cells[start:start+length]):
                            record[name] = [float(v) for v in cells[start:start+length]]
                    record.update({name: cells[i] for i, name in ((5, "xlabel"), (6, "ylabel"), (7, "title")) if cells[i]})
                    table_layers[str(layer)] = record
        for layer in self.layer_table_snapshot.keys() | table_layers.keys():
            before = self.layer_table_snapshot.get(layer, {})
            after = table_layers.get(layer, {})
            for field in before.keys() | after.keys():
                if before.get(field) != after.get(field):
                    record = options["layers"].setdefault(layer, {})
                    if field in after:
                        record[field] = after[field]
                    else:
                        record.pop(field, None)
        settings["figure_options"] = validate_options(options)
        settings["chart_styles"] = copy.deepcopy(self.chart_styles)
        validate_chart_styles(settings)
        self.layer_table_snapshot = table_layers
        self.scope_layers = copy.deepcopy(options["layers"])
        return settings

    def _commit_scope(self):
        if not self.scope:
            return
        level, layer, plot = self.scope
        if level == "chart":
            patch = self.page_editor.values(True)
            if patch:
                record = self.chart_styles.setdefault(layer, {})
                if "font_size" in patch:
                    for key in ("x_label_size", "y_label_size", "title_size", "tick_size", "legend_size"):
                        record.setdefault("figure_options", {})[key] = patch["font_size"]*(.85 if key == "legend_size" else 1)
                for key in ("orientation", "page_color"):
                    if key in patch:
                        record.setdefault("figure_options", {})[key] = patch.pop(key)
                record.update(patch)
            return
        if level == "layer":
            patch = self.layer_editor.values(True)
            if not patch:
                return
            record = self.scope_layers.setdefault(layer, copy.deepcopy(self._scope_record(layer)))
            for key in ("title", "legend"):
                if key in patch:
                    record[key] = patch.pop(key)
            if set(patch) & {"manual_position", "left", "top", "width", "height"}:
                values = self.layer_editor.values()
                if values["manual_position"]:
                    record["position"] = [values["left"]/100, 1-(values["top"]+values["height"])/100,
                                          values["width"]/100, values["height"]/100]
                else:
                    record.pop("position", None)
            for key in ("manual_position", "left", "top", "width", "height"):
                patch.pop(key, None)
            if patch:
                record.setdefault("options", {}).update(patch)
        elif level == "plot":
            patch = self.plot_editor.values(True)
            if patch:
                self.scope_layers.setdefault(layer, copy.deepcopy(self._scope_record(layer))).setdefault("plots", {}).setdefault(plot, {}).update(patch)

    def _all_axes(self):
        return [(chart, i, ax) for chart in self.preview_charts for i, ax in enumerate(chart.figure.axes, 1)]

    def _scope_record(self, key):
        if key in self.scope_layers:
            return self.scope_layers[key]
        for chart, index, ax in self._all_axes():
            if layer_key(ax, index) == key:
                layers = chart.settings.get("figure_options", {}).get("layers", {})
                return layers.get(key, layers.get(str(index), {}))
        return {}

    def _rebuild_object_tree(self):
        signature = (self.active_kind, tuple((chart.key, layer_key(ax, i), tuple((key, artist.get_label())
                     for key, artist in plot_items(ax))) for chart, i, ax in self._all_axes()))
        if signature == self.tree_signature:
            return
        previous = self.scope
        self.object_tree.blockSignals(True)
        self.object_tree.clear()
        page = QTreeWidgetItem(self.object_tree, ["Page — "+tr(KINDS[self.active_kind])])
        page.setData(0, Qt.ItemDataRole.UserRole, ("page", "", ""))
        common = QTreeWidgetItem(page, [tr("Common Display — 共用格式")])
        common.setData(0, Qt.ItemDataRole.UserRole, ("common", "", ""))
        target = page
        pages = {}
        for chart, i, ax in self._all_axes():
            if chart.key not in pages:
                chart_page = QTreeWidgetItem(page, ["Page — "+chart.title])
                chart_page.setData(0, Qt.ItemDataRole.UserRole, ("chart", chart.key, ""))
                pages[chart.key] = chart_page
                if previous == ("chart", chart.key, ""):
                    target = chart_page
            key = layer_key(ax, i)
            layer = QTreeWidgetItem(pages[chart.key], [f"Layer{i} — "+ax.get_title()])
            data = ("layer", key, "")
            layer.setData(0, Qt.ItemDataRole.UserRole, data)
            layer.setCheckState(0, Qt.CheckState.Checked if ax.get_visible() else Qt.CheckState.Unchecked)
            if previous == data:
                target = layer
            for number, (plot_key, artist) in enumerate(plot_items(ax), 1):
                label = artist.get_label()
                item = QTreeWidgetItem(layer, [label if label and not label.startswith("_") else f"Plot{number}"])
                data = ("plot", key, plot_key)
                item.setData(0, Qt.ItemDataRole.UserRole, data)
                visible = artist.patches[0].get_visible() if hasattr(artist, "patches") and artist.patches else getattr(artist, "get_visible", lambda: True)()
                item.setCheckState(0, Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
                if previous == data:
                    target = item
        self.object_tree.expandAll()
        self.object_tree.setCurrentItem(target)
        self.object_tree.blockSignals(False)
        self.tree_signature = signature
        self._select_object(target, None)

    def _selected_axis(self):
        if not self.scope:
            return None
        return next((ax for _, i, ax in self._all_axes() if layer_key(ax, i) == self.scope[1]), None)

    def _select_object(self, item, previous):
        if self.loading or item is None:
            return
        previous_scope = self.scope
        try:
            self._commit_scope()
            scope = tuple(item.data(0, Qt.ItemDataRole.UserRole))
            self.scope = scope
            level, key, plot = scope
            self.selection_label.setText(item.text(0))
            self.axes_button.setEnabled(level in ("layer", "plot"))
            self.reset_button.setEnabled(level in ("chart", "layer", "plot"))
            if level == "chart":
                settings = next(chart.settings for chart in self.preview_charts if chart.key == key)
                self.page_editor.load(settings | validate_options(settings.get("figure_options", {})))
                self.editor_stack.setCurrentWidget(self.page_editor)
                return
            if level in ("page", "common"):
                self.editor_stack.setCurrentWidget(self.tabs)
                for i in range(self.tabs.count()):
                    self.tabs.setTabVisible(i, level == "common" or i in (0, 1, 2, 6, 8))
                if not self.tabs.isTabVisible(self.tabs.currentIndex()):
                    self.tabs.setCurrentIndex(0)
                return
            ax = self._selected_axis()
            if ax is None:
                return
            global_options = validate_options({k: self._get(w) for k, w in self.option_widgets.items()})
            record = self._scope_record(key)
            local = global_options | record.get("options", {})
            if level == "layer":
                box = ax.get_position()
                x, y, width, height = record.get("position", [box.x0, box.y0, box.width, box.height])
                values = local | {"title": record.get("title", ax.get_title()),
                    "legend": record.get("legend", self.widgets["legend"].isChecked()),
                    "manual_position": "position" in record, "left": x*100,
                    "top": (1-y-height)*100, "width": width*100, "height": height*100}
                self.layer_editor.load(values)
                self.editor_stack.setCurrentWidget(self.layer_editor)
            else:
                artist = dict(plot_items(ax))[plot]
                bar = hasattr(artist, "patches")
                from matplotlib.colors import to_hex
                values = local | {"color": to_hex(artist.patches[0].get_facecolor() if bar else artist.get_color()),
                                  "line_width": self.widgets["line_width"].value()}
                if not bar:
                    values.update(line_width=artist.get_linewidth(), line_style=artist.get_linestyle(),
                                  line_alpha=artist.get_alpha() if artist.get_alpha() is not None else 1,
                                  marker=artist.get_marker(), marker_size=artist.get_markersize())
                self.plot_editor.load(values | record.get("plots", {}).get(plot, {}))
                self.plot_editor.setTabVisible(0, not bar)
                self.plot_editor.setTabVisible(1, not bar)
                self.plot_editor.setTabVisible(2, bar)
                # Bar fill color belongs on Pattern as well as the Line tab.
                self.plot_editor.setTabVisible(0, True)
                for field in ("line_width", "line_style", "line_alpha"):
                    self.plot_editor.fields[field].setEnabled(not bar)
                self.editor_stack.setCurrentWidget(self.plot_editor)
        except Exception as exc:
            self.scope = previous_scope
            self.notice.setText(str(exc))
            if previous is not None:
                self.object_tree.blockSignals(True)
                self.object_tree.setCurrentItem(previous)
                self.object_tree.blockSignals(False)

    def _object_visibility(self, item, column):
        if self.loading:
            return
        level, layer, plot = item.data(0, Qt.ItemDataRole.UserRole)
        visible = item.checkState(0) == Qt.CheckState.Checked
        record = self.scope_layers.setdefault(layer, {})
        if level == "layer":
            record["visible"] = visible
        elif level == "plot":
            record.setdefault("plots", {}).setdefault(plot, {})["visible"] = visible
        self.preview()

    def open_axes(self, direction="bottom"):
        try:
            settings = self.read_settings()
            ax = self._selected_axis()
            if ax is None:
                return
            layer = self.scope[1]
            record = self._scope_record(layer)
            options = settings["figure_options"] | record.get("options", {})
            values = {side: axis_defaults(ax, side, settings, options) for side in AXIS_SIDES}
            def update(axes):
                candidate = copy.deepcopy(self.scope_layers)
                candidate.setdefault(layer, {})["axes"] = axes
                validate_options(settings["figure_options"] | {"layers": candidate})
                self.scope_layers = candidate
                self.preview()
            self.axis_dialog = AxisDialog(self, layer, values, record.get("axes", {}), update,
                                          bool(getattr(ax, "_pl_categorical", False)))
            side = {"x": "bottom", "y": "left"}.get(direction, direction)
            self.axis_dialog.axes_list.setCurrentRow(AXIS_SIDES.index(side) if side in AXIS_SIDES else 0)
            self.axis_dialog.show()
        except Exception as exc:
            self.notice.setText(str(exc))

    def reset_object(self):
        if not self.scope:
            return
        level, layer, plot = self.scope
        self.layer_editor.dirty.clear()
        self.plot_editor.dirty.clear()
        self.page_editor.dirty.clear()
        if level == "chart":
            self.chart_styles.pop(layer, None)
        elif level == "layer":
            self.scope_layers.pop(layer, None)
        elif level == "plot":
            self.scope_layers.get(layer, {}).get("plots", {}).pop(plot, None)
        self.scope = None
        self.preview()
        self._select_object(self.object_tree.currentItem(), None)

    def _preview_double_click(self, event):
        if not event.dblclick:
            return
        ax = event.inaxes
        direction = None
        for _, _, owner in self._all_axes():
            rulers = getattr(owner, "_pl_side_axes", {"bottom": owner, "left": owner})
            # Include uncustomized mirrored spines, which still live on owner.
            rulers = {side: rulers.get(side, owner) for side in AXIS_SIDES}
            for side, candidate in rulers.items():
                which = axis_direction(side)
                axis = getattr(candidate, which+"axis")
                objects = [axis.label, *axis.get_ticklabels()]
                if candidate is owner:
                    objects = [axis.label] if side in ("bottom", "left") else []
                    for tick in axis.get_major_ticks():
                        objects.append(tick.label1 if side in ("bottom", "left") else tick.label2)
                objects.append(candidate.spines[side])
                if any(obj.get_visible() and obj.contains(event)[0] for obj in objects):
                    ax, direction = owner, side
                    break
            if direction:
                break
        if ax is None:
            return
        key = next((layer_key(a, i) for _, i, a in self._all_axes() if a is ax), None)
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        iterator = QTreeWidgetItemIterator(self.object_tree)
        hit = None if direction else next((plot_key for plot_key, artist in plot_items(ax)
                    if hasattr(artist, "contains") and artist.contains(event)[0]), None)
        while iterator.value():
            item = iterator.value()
            level, layer, plot = item.data(0, Qt.ItemDataRole.UserRole)
            if layer == key and ((hit is not None and level == "plot" and plot == hit) or (hit is None and level == "layer")):
                self.object_tree.setCurrentItem(item)
                if direction:
                    self.open_axes(direction)
                break
            iterator += 1

    def _accept_settings(self):
        if self.apply(False):
            self.close()

    def apply_each_chart(self):
        """Copy a selected chart format to the chosen group(s), preserving data."""
        try:
            settings = self.read_settings()
            source = next((chart for chart in self.preview_charts if self.scope and
                           (chart.key == self.scope[1] or any(layer_key(ax, i) == self.scope[1]
                            for i, ax in enumerate(chart.figure.axes, 1)))), self.preview_charts[0])
            effective = chart_settings(DEFAULT_STYLE | settings, source.key)
            page_keys = {key for _, fields in PAGE_SECTIONS for key, _, _ in fields}
            options = validate_options(effective.get("figure_options", {}))
            page_patch = {key: effective[key] for key in page_keys if key in effective}
            page_patch["figure_options"] = {key: copy.deepcopy(value) for key, value in options.items() if key != "layers"}
            content = self.copy_axis_content.isChecked()
            if not content:
                for key in ("annotations", "shapes", "reference_x", "reference_y", "special_x_ticks", "special_y_ticks"):
                    page_patch["figure_options"].pop(key, None)
            all_kinds = self.apply_scope.currentData() == "all"
            kinds = list(KINDS) if all_kinds else [self.active_kind]
            bundle, count = {}, 0
            source_layers = [copy.deepcopy(self._scope_record(layer_key(ax, i)))
                             for i, ax in enumerate(source.figure.axes, 1)]
            from .chart_group import render_charts
            for kind in kinds:
                target = copy.deepcopy(settings if kind == self.active_kind else self.drafts[kind])
                charts = self.preview_charts if kind == self.active_kind else render_charts(
                    Figure(), kind, getattr(self.parent(), "spectra", []), target)[0]
                styles = target.setdefault("chart_styles", {})
                layers = target.setdefault("figure_options", {}).setdefault("layers", {})
                for chart in charts:
                    target_style = styles.setdefault(chart.key, {})
                    page_options = target_style.get("figure_options", {}) | copy.deepcopy(page_patch["figure_options"])
                    target_style.update(copy.deepcopy(page_patch))
                    target_style["figure_options"] = page_options
                    for index, target_ax in enumerate(chart.figure.axes, 1):
                        if index > len(source_layers):
                            continue
                        target_key = layer_key(target_ax, index)
                        record = copy.deepcopy(source_layers[index-1])
                        if not content:
                            existing = layers.get(target_key, layers.get(str(index), {}))
                            for key in ("title", "xlabel", "ylabel", "xlim", "ylim"):
                                record.pop(key, None)
                                if key in existing:
                                    record[key] = copy.deepcopy(existing[key])
                            for axis in record.get("axes", {}).values():
                                for key in ("minimum", "maximum", "label", "special_ticks", "references"):
                                    axis.pop(key, None)
                            for side, axis in existing.get("axes", {}).items():
                                for key in ("minimum", "maximum", "label", "special_ticks", "references"):
                                    if key in axis:
                                        record.setdefault("axes", {}).setdefault(side, {})[key] = copy.deepcopy(axis[key])
                        # Match curve roles rather than spectrum identifiers.
                        plots = record.pop("plots", {})
                        source_plots = plot_items(source.figure.axes[index-1])
                        target_plots, mapped = plot_items(target_ax), {}
                        for target_id, _ in target_plots:
                            role = target_id.split(":", 1)[-1]
                            match = next((k for k, _ in source_plots if k.split(":", 1)[-1] == role), None)
                            if match is None and len(target_plots) == 1 and source_plots:
                                match = self.scope[2] if self.scope and self.scope[0] == "plot" else source_plots[0][0]
                            if match in plots:
                                mapped[target_id] = copy.deepcopy(plots[match])
                        if mapped:
                            record["plots"] = mapped
                        if kind != self.active_kind or chart.key != source.key:
                            layers[target_key] = record
                validate_chart_styles(target)
                validate_options(target["figure_options"])
                bundle[kind] = target
                count += len(charts)
            self.drafts.update(bundle)
            self._load_form(bundle[self.active_kind])
            self.preview()
            if self.apply(all_kinds):
                self.notice.setText(tr("已套用到 {0} 張獨立圖。").format(count))
        except Exception as exc:
            self.notice.setText(str(exc))

    def _refresh_dependencies(self):
        """Disable controls that do not apply to the current data or figure."""
        def enable(widget, allowed, reason):
            widget.setEnabled(allowed)
            widget.setToolTip("" if allowed else reason)
            label = self.field_labels.get(widget)
            if label is not None:
                label.setEnabled(allowed)
                label.setToolTip("" if allowed else reason)

        results = [s.result for s in getattr(self.parent(), "spectra", []) if s.plot and s.result]
        if self.active_kind == "trends":
            errorbars = self.specific_widgets["errorbars"]
            enable(errorbars, errorbars.isEnabled(), errorbars.toolTip())
        if self.active_kind == "spectrum":
            for key, allowed, reason in (
                ("fit", bool(results), tr("尚無選取資料的擬合結果。")),
                ("residual", bool(results), tr("需要擬合結果才能顯示殘差。")),
                ("components", any(len(r["peaks"]) > 1 for r in results), tr("需要至少兩個擬合峰。")),
                ("background", any("b_" in r["components"] for r in results), tr("所選擬合結果沒有背景模型。"))):
                widget = self.specific_widgets[key]
                enable(widget, allowed, reason)
                if not allowed:
                    blocker = QSignalBlocker(widget)
                    widget.setChecked(False)
                    del blocker
                self.content.labelForField(widget).setToolTip("" if allowed else reason)
                self.content.labelForField(widget).setEnabled(allowed)

        bar = self.active_kind == "trends" and self.specific_widgets["plot_type"].currentText() == "bar"
        enable(self.specific_widgets["bar_width"], bar, tr("僅長條圖適用。"))
        for key in ("bar_edge", "bar_hatch", "bar_alpha"):
            enable(self.option_widgets[key], bar, tr("僅長條圖適用。"))
        for key in ("line_style", "line_alpha", "marker", "marker_size", "marker_face", "marker_edge", "marker_edge_width"):
            enable(self.option_widgets[key], not bar, tr("長條圖請使用長條邊線、填紋及透明度設定。"))
        categorical = False
        if self.active_kind == "trends":
            mode = self.specific_widgets["x_mode"].currentText()
            categorical = mode == "category"
            if mode == "auto":
                labels = [s.condition.strip() or s.name for s in getattr(self.parent(), "spectra", []) if s.plot]
                try:
                    categorical = not labels or not all(np.isfinite(float(label)) for label in labels)
                except ValueError:
                    categorical = True
        scale = self.option_widgets["xscale"]
        for index in range(scale.count()):
            scale.model().item(index).setEnabled(not categorical or scale.itemText(index) == "linear")
        if categorical:
            blocker = QSignalBlocker(scale)
            scale.setCurrentText("linear")
            del blocker
        scale.setToolTip(tr("類別 Condition 使用線性排列；數值軸才可選對數尺度。") if categorical else "")
        for key in ("x_major_step", "x_major_count", "x_format", "special_x_ticks"):
            enable(self.option_widgets[key], not categorical, tr("類別 Condition 使用樣品名稱刻度。"))
        for key in ("error_width", "error_capsize"):
            available = (self.active_kind == "trends" and self.specific_widgets["errorbars"].isEnabled()
                         and self.specific_widgets["errorbars"].isChecked())
            enable(self.option_widgets[key], available, tr("需要啟用誤差棒，且所選指標有可用標準誤。"))
        for key in ("inset_layer", "inset_box", "inset_xlim", "inset_ylim", "inset_connectors"):
            enable(self.option_widgets[key], self.option_widgets["inset"].isChecked(), tr("請先啟用局部放大圖。"))
        for key in ("left", "right", "bottom", "top", "hspace", "wspace"):
            enable(self.option_widgets[key], self.option_widgets["layout_mode"].currentText() == "manual",
                   tr("請先選擇手動版面配置。"))
        for key in ("panel_label_style", "panel_label_x", "panel_label_y"):
            enable(self.option_widgets[key], self.option_widgets["panel_labels"].isChecked(), tr("請先啟用面板編號。"))
        for key in ("legend_loc", "legend_columns", "legend_frame", "legend_alpha", "legend_size", "legend_title",
                    "legend_outside", "legend_reverse", "legend_face", "legend_edge", "legend_spacing"):
            enable(self.option_widgets[key], self.widgets["legend"].isChecked(), tr("請先啟用圖例。"))
        for key in ("legend_alpha", "legend_face", "legend_edge"):
            enable(self.option_widgets[key], self.widgets["legend"].isChecked() and self.option_widgets["legend_frame"].isChecked(),
                   tr("請先啟用圖例及圖例邊框。"))
        for key in ("minor_length", "minor_divisions"):
            enable(self.option_widgets[key], self.option_widgets["minor_ticks"].isChecked(), tr("請先啟用次刻度。"))
        fixed = any(self.option_widgets[key].currentText() == "fixed" for key in ("x_format", "y_format"))
        enable(self.option_widgets["decimals"], fixed, tr("僅固定小數格式適用。"))
        enable(self.option_widgets["export_pad"], self.option_widgets["tight_export"].isChecked(), tr("請先啟用依內容裁切。"))

    def preview(self):
        if self.loading or not self.active_kind:
            return
        try:
            settings = self.read_settings()
            self.drafts[self.active_kind] = settings
            self.figure.set_layout_engine(None)
            charts = self.preview_callback(self.figure, self.active_kind, settings)
            self.preview_charts = charts or [Chart(self.active_kind, tr(KINDS[self.active_kind]), self.figure, settings)]
            self.preview_figures = [chart.figure for chart in self.preview_charts]
            self.preview_group.set_charts(self.preview_charts, settings["figure_options"]["columns"])
            self._rebuild_object_tree()
            self.notice.setText(tr("預覽已更新。套用後會同步主畫面；儲存設定檔可保留全部圖型的設定。"))
        except Exception as exc:
            self.notice.setText(tr("設定需調整：")+str(exc))

    def apply(self, all_kinds=False):
        try:
            self.drafts[self.active_kind] = self.read_settings()
            bundle = self.drafts if all_kinds else {self.active_kind: self.drafts[self.active_kind]}
            self.applied.emit(copy.deepcopy(bundle))
            self.notice.setText(tr("已套用。"))
            return True
        except Exception as exc:
            QMessageBox.warning(self, tr("設定需調整"), str(exc))
            return False

    def save_file(self, path):
        self.drafts[self.active_kind] = self.read_settings()
        bundle = {kind: {key: value for key, value in settings.items() if key not in ("styles", "trends", "overlay")}
                  for kind, settings in self.drafts.items()}
        write_json(path, {"type": "PLStudioPlotStyle", "version": 2, "figures": bundle})

    def load_file(self, path):
        content = json.loads(Path(path).read_text(encoding="utf-8"))
        if content.get("type") != "PLStudioPlotStyle":
            raise ValueError(tr("不是 PL Studio Figure Template 設定檔。"))
        if content.get("version", 1) == 1:
            bundle = {"spectrum": self.drafts["spectrum"] | content["settings"]}
        elif content["version"] == 2:
            bundle = content["figures"]
        else:
            raise ValueError(tr("不支援的設定檔版本。"))
        for kind, settings in bundle.items():
            if kind not in KINDS or not isinstance(settings, dict):
                raise ValueError(tr("圖型設定無效。"))
            validate_options(settings.get("figure_options", {}))
            validate_chart_styles(settings)
            for key in ("width_cm", "height_cm", "dpi", "font_size", "line_width"):
                if key in settings and (not isinstance(settings[key], (int, float)) or not np.isfinite(settings[key]) or settings[key] <= 0):
                    raise ValueError(tr('{0} 必須為正數。').format(key, ''))
        self.drafts.update(copy.deepcopy(bundle))
        self._load_form(self.drafts[self.active_kind])
        self.preview()
        self.applied.emit(copy.deepcopy(bundle))

    def save_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("儲存全部圖型設定"), "PL_figure_template.json", "Figure Template (*.json)")
        if path:
            try:
                self.save_file(path)
                self.notice.setText(tr("全部圖型設定已儲存：")+path)
            except Exception as exc:
                QMessageBox.warning(self, tr("儲存失敗"), str(exc))

    def load_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("載入並套用設定檔"), "", "Figure Template (*.json)")
        if path:
            try:
                self.load_file(path)
            except Exception as exc:
                QMessageBox.warning(self, tr("載入失敗"), str(exc))
