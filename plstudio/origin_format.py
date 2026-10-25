"""Object-scoped 2-D formatting controls based on the Origin 2025 User Guide.

Reference: chapter 11, printed pages 225-226 and 233-235. These controls
write portable Matplotlib settings; they do not read Origin binary themes.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QAbstractItemView, QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget, QColorDialog)

from .i18n import tr


class ColorEdit(QLineEdit):
    """A color swatch/picker that also accepts named colors and #RRGGBB."""
    def __init__(self):
        super().__init__()
        self.swatch = self.addAction(QIcon(), QLineEdit.ActionPosition.LeadingPosition)
        self.swatch.triggered.connect(self.choose)
        self.textChanged.connect(self._update_swatch)
        self._update_swatch("")

    def _update_swatch(self, text):
        color = QColor(text)
        pixmap = QPixmap(16, 16)
        pixmap.fill(color if color.isValid() else Qt.GlobalColor.transparent)
        self.swatch.setIcon(QIcon(pixmap))

    def choose(self):
        color = QColorDialog.getColor(QColor(self.text()), self, tr("選擇顏色"))
        if color.isValid():
            self.setText(color.name())
            self.editingFinished.emit()


class PropertyTabs(QTabWidget):
    changed = Signal()

    def __init__(self, sections, parent=None):
        super().__init__(parent)
        self.fields = {}
        self.dirty = set()
        self.loading = False
        for title, fields in sections:
            area = QScrollArea()
            area.setWidgetResizable(True)
            panel = QWidget()
            form = QFormLayout(panel)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for key, label, kind in fields:
                if isinstance(kind, list):
                    widget = QComboBox()
                    widget.addItems(kind)
                    signal = widget.currentTextChanged
                elif kind is bool:
                    widget = QCheckBox()
                    signal = widget.toggled
                elif kind in (float, int):
                    widget = QSpinBox() if kind is int else QDoubleSpinBox()
                    widget.setRange(-1000000, 1000000)
                    if kind is float:
                        widget.setDecimals(4)
                    if key.endswith("alpha"):
                        widget.setRange(0, 1)
                    elif key == "decimals":
                        widget.setRange(0, 15)
                    elif key in ("major_count", "minor_divisions"):
                        widget.setRange(1, 1000)
                    elif key in ("line_width", "marker_size", "label_size", "tick_size", "axis_width", "tick_width", "grid_width"):
                        widget.setRange(.01, 1000)
                    signal = widget.valueChanged
                else:
                    widget = ColorEdit() if "color" in key or key in ("marker_face", "marker_edge", "bar_edge") else QLineEdit()
                    signal = widget.editingFinished
                widget.setProperty("kind", "optional" if kind == "optional" else "array" if kind is list else "")
                widget.setObjectName(key)
                signal.connect(lambda *args, k=key: self._changed(k))
                self.fields[key] = widget
                form.addRow(tr(label), widget)
            area.setWidget(panel)
            self.addTab(area, tr(title))

    def _changed(self, key):
        if not self.loading:
            self.dirty.add(key)
            self.changed.emit()

    def load(self, values):
        self.loading = True
        for key, widget in self.fields.items():
            value = values.get(key)
            if isinstance(widget, QComboBox):
                widget.setCurrentText(str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(value or 0)
            else:
                widget.setText(", ".join(map(str, value)) if isinstance(value, list) else "" if value is None else str(value))
        self.dirty.clear()
        self.loading = False

    def values(self, changed_only=False):
        result = {}
        for key, widget in self.fields.items():
            if changed_only and key not in self.dirty:
                continue
            if isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                value = widget.value()
            else:
                value = widget.text().strip()
                if widget.property("kind") == "optional":
                    value = float(value) if value else None
                elif widget.property("kind") == "array":
                    value = [float(v) for v in value.replace("，", ",").split(",") if v.strip()]
            result[key] = value
        return result


LAYER_SECTIONS = [
    ("Background", [("layer_color", "繪圖區背景", str)]),
    ("Size", [("manual_position", "啟用自訂圖層位置", bool),
              ("left", "Left（頁面 %）", float), ("top", "Top（頁面 %）", float),
              ("width", "Width（頁面 %）", float), ("height", "Height（頁面 %）", float)]),
    ("Display", [("title", "圖標題", str), ("legend", "顯示圖例", bool),
                 ("axis_color", "軸線顏色", str), ("axis_width", "軸線寬度 pt", float),
                 ("top_axis", "顯示上軸", bool), ("right_axis", "顯示右軸", bool)]),
]

PLOT_SECTIONS = [
    ("Line", [("color", "顏色", str), ("line_width", "線寬 pt", float),
              ("line_style", "線型", ["-", "--", "-.", ":", "None"]),
              ("line_alpha", "曲線不透明度", float)]),
    ("Symbol", [("marker", "符號", ["None", "o", "s", "^", "v", "D", "x", "+", "*"]),
                ("marker_size", "符號大小 pt", float), ("marker_face", "符號填色（auto 沿用）", str),
                ("marker_edge", "符號邊色", str), ("marker_edge_width", "符號邊線寬 pt", float)]),
    ("Pattern", [("bar_edge", "長條邊線顏色", str), ("bar_hatch", "長條填紋（如 / 或 x）", str),
                 ("bar_alpha", "長條不透明度", float)]),
]

PAGE_SECTIONS = [
    ("Print/Dimensions", [("width_cm", "寬 cm", float), ("height_cm", "高 cm", float),
                          ("dpi", "輸出 DPI", int), ("font", "字型", str),
                          ("font_size", "基本字級 pt", float), ("line_width", "線寬 pt", float),
                          ("orientation", "頁面方向", ["custom", "portrait", "landscape"])]),
    ("Display", [("page_color", "頁面顏色", str)]),
]

AXIS_SECTIONS = [
    ("Scale", [("minimum", "From（留白自動）", "optional"), ("maximum", "To（留白自動）", "optional"),
               ("scale", "Type", ["linear", "log", "symlog"]), ("reverse", "Reverse", bool),
               ("major_step", "主刻度間隔（0＝自動）", float), ("major_count", "自動刻度數", int),
               ("minor_ticks", "顯示次刻度", bool), ("minor_divisions", "主刻度間細分數", int)]),
    ("Tick Labels", [("tick_labels", "顯示刻度標籤", bool),
                     ("format", "數值格式", ["auto", "fixed", "scientific", "plain"]),
                     ("decimals", "固定小數位數", int), ("rotation", "旋轉角度", float),
                     ("tick_size", "刻度字級", float)]),
    ("Title", [("label", "軸標題", str), ("label_size", "標題字級", float), ("label_pad", "標題與軸距離 pt", float)]),
    ("Grids", [("grid", "顯示主格線", bool), ("minor_grid", "顯示次格線", bool),
               ("grid_color", "格線顏色", str), ("grid_width", "格線寬度 pt", float),
               ("grid_style", "格線形式", ["-", "--", ":", "-."])]),
    ("Line and Ticks", [("visible", "顯示此座標軸", bool),
                        ("axis_color", "軸線顏色", str), ("axis_width", "軸線寬度 pt", float),
                        ("tick_direction", "刻度方向", ["in", "out", "inout"]),
                        ("major_length", "主刻度長度 pt", float), ("minor_length", "次刻度長度 pt", float),
                        ("tick_width", "刻度線寬 pt", float)]),
    ("Special Ticks", [("special_ticks", "指定刻度（逗號分隔）", list)]),
    ("Reference Lines", [("references", "參考線位置（逗號分隔）", list),
                         ("reference_color", "參考線顏色", str), ("reference_style", "參考線型", ["--", "-", ":", "-."])]),
]

AXIS_SIDES = ("bottom", "top", "left", "right")


def axis_direction(side):
    return "x" if side in ("x", "bottom", "top") else "y"


def side_settings(axes, side):
    """Read old Horizontal/Vertical settings without coupling opposite sides."""
    inherited = axes.get("x" if side == "bottom" else "y", {}) if side in ("bottom", "left") else {}
    return inherited | axes.get(side, {})


def axis_defaults(ax, side, settings, options):
    """Resolve inherited settings without freezing automatically calculated limits."""
    direction = axis_direction(side)
    values = {key: options[key] for key in ("minor_ticks", "minor_divisions", "decimals", "tick_size", "label_pad",
              "minor_grid", "grid_color", "grid_width", "grid_style", "axis_color", "axis_width", "tick_direction",
              "major_length", "minor_length", "tick_width", "reference_color", "reference_style")}
    for target, source in (("scale", direction+"scale"), ("reverse", "reverse_"+direction),
                           ("major_step", direction+"_major_step"), ("major_count", direction+"_major_count"),
                           ("format", direction+"_format"), ("rotation", direction+"_rotation"),
                           ("label_size", direction+"_label_size"), ("special_ticks", "special_"+direction+"_ticks"),
                           ("references", "reference_"+direction)):
        values[target] = options[source]
    primary = side in ("x", "y", "bottom", "left")
    source = getattr(ax, "_pl_side_axes", {}).get(side, ax)
    values.update(minimum=settings.get(direction+"min") if primary else None,
                  maximum=settings.get(direction+"max") if primary else None,
                  label=getattr(source, "get_"+direction+"label")() if primary or source is not ax else "",
                  grid=settings.get("grid", False) if primary else False,
                  visible=options.get(side+"_axis", True), tick_labels=primary)
    if not primary:
        values.update(references=[], minor_grid=False)
    return values


class AxisDialog(QDialog):
    """Four independently editable axis sides with optional multi-selection."""
    def __init__(self, parent, layer, values, overrides, callback, categorical=False):
        super().__init__(parent)
        self.setWindowTitle(tr("Axis Dialog — Layer {0}").format(layer))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(1000, 620)
        self.values_by_axis = copy.deepcopy(values)
        self.overrides = copy.deepcopy(overrides)
        self.callback = callback
        self.direction = "bottom"
        self.categorical = categorical
        outer = QVBoxLayout(self)
        row = QHBoxLayout()
        self.axes_list = QListWidget()
        self.axes_list.addItems([tr("Bottom — 下 X 軸"), tr("Top — 上 X 軸"),
                                 tr("Left — 左 Y 軸"), tr("Right — 右 Y 軸")])
        self.axes_list.setMinimumWidth(165)
        self.axes_list.setMaximumWidth(200)
        self.axes_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        row.addWidget(self.axes_list)
        self.editor = PropertyTabs(AXIS_SECTIONS)
        row.addWidget(self.editor, 1)
        outer.addLayout(row, 1)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        outer.addWidget(self.notice)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        outer.addWidget(self.buttons)
        self.axes_list.currentRowChanged.connect(self._select)
        self.axes_list.setCurrentRow(0)

    def _store(self):
        patch = self.editor.values(changed_only=True)
        selected = [AXIS_SIDES[self.axes_list.row(item)] for item in self.axes_list.selectedItems()]
        if patch:
            for direction in selected or [self.direction]:
                self.overrides.setdefault(direction, {}).update(patch)

    def _select(self, row):
        # Commit to the previous axis, even though Qt has already changed selection.
        if self.editor.fields and self.editor.dirty:
            self.overrides.setdefault(self.direction, {}).update(self.editor.values(True))
        self.direction = AXIS_SIDES[row]
        self.editor.load(self.values_by_axis[self.direction] | side_settings(self.overrides, self.direction))
        category = self.categorical and axis_direction(self.direction) == "x"
        for key in ("scale", "major_step", "major_count", "format", "special_ticks", "minimum", "maximum"):
            self.editor.fields[key].setEnabled(not category)

    def apply(self):
        try:
            self._store()
            self.callback(copy.deepcopy(self.overrides))
            self.editor.dirty.clear()
            self.notice.setText(tr("已套用。"))
            return True
        except Exception as exc:
            self.notice.setText(str(exc))
            return False

    def _accept(self):
        if self.apply():
            self.accept()
