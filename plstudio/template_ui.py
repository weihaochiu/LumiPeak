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
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .data import write_json
from .figure_style import DEFAULT_OPTIONS, validate_options
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
        self.setWindowTitle(tr("Figure Template — 各圖型設定與模板"))
        self.resize(1400, 900)
        self.preview_callback = preview_callback
        self.loading = False
        self.drafts = {}
        self.active_kind = None
        self.widgets, self.option_widgets = {}, {}
        self.field_labels = {}
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
        self.figure = Figure(figsize=(8, 6), facecolor="white")
        self.canvas = FigureCanvasQTAgg(self.figure)
        splitter.addWidget(self.canvas)
        self.tabs = QTabWidget()
        splitter.addWidget(self.tabs)
        splitter.setSizes([830, 540])
        layout.addWidget(splitter, 1)
        base = self._tab(tr("基本／內容"))
        for key, label, typ in (
            ("width_cm", tr("寬 cm"), float), ("height_cm", tr("高 cm"), float), ("dpi", "DPI", int),
            ("font", tr("字型"), str), ("font_size", tr("基本字級 pt"), float), ("line_width", tr("線寬 pt"), float),
            ("title", tr("圖標題"), str), ("xlabel", tr("X 軸標題（留白自動）"), str),
            ("ylabel", tr("Y 軸標題（單面板）"), str), ("xmin", tr("X 下限（留白自動）"), "optional"),
            ("xmax", tr("X 上限"), "optional"), ("ymin", tr("Y 下限（單面板）"), "optional"),
            ("ymax", tr("Y 上限"), "optional"), ("legend", tr("顯示圖例"), bool), ("grid", tr("顯示主格線"), bool)):
            self.widgets[key] = self._field(base, key, label, typ)
        self.content = self._tab(tr("圖型專用"))
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
        self.tables = {}
        self._object_table(tr("文字／箭頭"), "annotations", [tr("面板"), tr("文字"), "X", "Y", tr("箭頭目標 X"), tr("箭頭目標 Y"), tr("座標 axes/data"), tr("顏色"), tr("字級")])
        self._object_table(tr("形狀"), "shapes", [tr("面板"), "rectangle/ellipse", "X", "Y", tr("寬"), tr("高"), tr("座標 axes/data"), tr("填色"), tr("邊色"), tr("不透明度")])
        self._object_table(tr("各面板覆寫"), "layers", [tr("面板"), tr("X 下限"), tr("X 上限"), tr("Y 下限"), tr("Y 上限"), tr("X 標題"), tr("Y 標題"), tr("圖標題"), tr("位置 L"), tr("位置 B"), tr("位置 W"), tr("位置 H")])
        row = QHBoxLayout()
        for label, slot in ((tr("更新預覽"), self.preview), (tr("套用此圖設定"), lambda: self.apply(False)),
                            (tr("套用全部圖型設定"), lambda: self.apply(True)), (tr("儲存設定檔"), self.save_dialog),
                            (tr("載入設定檔"), self.load_dialog), (tr("關閉"), self.close)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, callback=slot: callback())
            row.addWidget(button)
        layout.addLayout(row)
        self.notice = QLabel(tr("顏色可填名稱或 #RRGGBB；文字支援 Unicode 與 Matplotlib 數學標記。"))
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

    def _tab(self, title):
        area = QScrollArea()
        area.setWidgetResizable(True)
        widget = QWidget()
        form = QFormLayout(widget)
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
            widget = QLineEdit()
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
        options.update(annotations=[], shapes=[], layers={})
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
                    options[key][str(layer)] = record
        settings["figure_options"] = validate_options(options)
        return settings

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
            self.preview_callback(self.figure, self.active_kind, settings)
            self.canvas.draw_idle()
            self.notice.setText(tr("預覽已更新。套用後會同步主畫面；儲存設定檔可保留全部圖型的設定。"))
        except Exception as exc:
            self.notice.setText(tr("設定需調整：")+str(exc))

    def apply(self, all_kinds=False):
        try:
            self.drafts[self.active_kind] = self.read_settings()
            bundle = self.drafts if all_kinds else {self.active_kind: self.drafts[self.active_kind]}
            self.applied.emit(copy.deepcopy(bundle))
            self.notice.setText(tr("已套用。"))
        except Exception as exc:
            QMessageBox.warning(self, tr("設定需調整"), str(exc))

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
