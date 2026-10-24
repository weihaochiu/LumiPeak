"""Qt controls for parameter-versus-condition plots."""
from __future__ import annotations

from .i18n import tr

import copy
import math

from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .trends import DEFAULT_TRENDS, METRICS, position_choices, trend_peak_context


def update_position_choices(checks, view, spectra, peak_number, include_failed=False, errorbars=None):
    """Keep main controls and the template editor consistent without signals."""
    blockers = [QSignalBlocker(view), *(QSignalBlocker(c) for c in checks.values())]
    enabled, label, tip = position_choices(spectra, peak_number, include_failed)
    check = checks["center"]
    check.setText(label)
    check.setToolTip(tip)
    check.setEnabled(enabled)
    index = view.findData("center")
    view.setItemText(index, label)
    view.setItemData(index, tip, Qt.ItemDataRole.ToolTipRole)
    view.model().item(index).setEnabled(enabled)
    if not enabled:
        if check.isChecked():
            check.setChecked(False)
            checks["maximum_position"].setChecked(True)
        if view.currentData() == "center":
            view.setCurrentIndex(view.findData("maximum_position"))
    multiple = any(count > 1 for model, count in trend_peak_context(spectra, peak_number, include_failed))
    label = tr("分峰面積比例（僅多峰擬合）")
    fraction = checks["area_fraction"]
    fraction.setText(label if multiple else tr("分峰面積比例（需至少兩個擬合峰，停用）"))
    fraction.setEnabled(multiple)
    fraction.setToolTip(tr("只比較多峰擬合中各峰佔總分峰面積的比例；單峰結果不納入此圖。"))
    index = view.findData("area_fraction")
    view.setItemText(index, fraction.text())
    view.setItemData(index, fraction.toolTip(), Qt.ItemDataRole.ToolTipRole)
    view.model().item(index).setEnabled(multiple)
    if not multiple:
        fraction.setChecked(False)
        if view.currentData() == "area_fraction":
            view.setCurrentIndex(view.findData("maximum_position"))
    if errorbars is not None:
        keys = ([view.currentData()] if view.currentData() != "overview" else
                [key for key, check in checks.items() if check.isChecked()])
        available = False
        for spectrum in spectra:
            result = spectrum.result
            if not spectrum.plot or result is None or (not result["success"] and not include_failed):
                continue
            peak = next((p for p in result["peaks"] if p["peak"] == peak_number), {})
            for key in keys:
                definition = METRICS[key]
                source = peak if definition[2] == "peak" else result["metrics"]
                error = source.get(definition[4]) if definition[4] else None
                if error is not None and math.isfinite(error) and error >= 0:
                    available = True
        errorbars.setEnabled(available)
        errorbars.setToolTip(tr("顯示已保存的參數標準誤。") if available else tr("目前所選指標沒有可用的參數標準誤，停用。"))


class TrendPanel(QScrollArea):
    changed = Signal()
    conditions_changed = Signal()
    export_image = Signal()
    export_all = Signal()
    export_data = Signal()

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.loading = False
        self.spectra = []
        content = QWidget()
        layout = QVBoxLayout(content)
        self.setWidget(content)

        section = self._group(tr("1  Condition 與參與資料"), layout)
        hint = QLabel(tr("使用者定義名稱統一在左側編輯，PL 疊圖與趨勢圖共用。\n雙擊 Condition 填名稱或數值；留白使用左側名稱。\n顯示勾選與左側同步。"))
        hint.setWordWrap(True)
        section.addWidget(hint)
        self.condition_table = QTableWidget(0, 4)
        self.condition_table.setHorizontalHeaderLabels([tr("顯示"), tr("共用名稱"), "Condition", tr("狀態")])
        self.condition_table.setAlternatingRowColors(True)
        self.condition_table.setMinimumHeight(205)
        for i, width in enumerate((40, 85, 105, 80)):
            self.condition_table.setColumnWidth(i, width)
        self.condition_table.horizontalHeader().setStretchLastSection(True)
        self.condition_table.itemChanged.connect(self._condition_edited)
        section.addWidget(self.condition_table)
        row = QHBoxLayout()
        self._button(tr("全選"), lambda: self._select_all(True), row)
        self._button(tr("清除"), lambda: self._select_all(False), row)
        section.addLayout(row)

        section = self._group(tr("2  座標與分峰"), layout)
        form = QFormLayout()
        self.peak = QSpinBox()
        self.peak.setRange(1, 12)
        self.peak.valueChanged.connect(self._changed)
        form.addRow(tr("分析 Peak 編號"), self.peak)
        self.xmode = QComboBox()
        for label, value in ((tr("類別（樣品／製程名稱）"), "category"), (tr("數值（功率／濃度／溫度）"), "numeric"),
                             (tr("自動判斷"), "auto")):
            self.xmode.addItem(label, value)
        self.xmode.currentIndexChanged.connect(self._changed)
        form.addRow(tr("Condition 類型"), self.xmode)
        self.xlabel = QLineEdit("Condition")
        self.xlabel.setPlaceholderText(tr("例如 Annealing temperature (°C)"))
        self.xlabel.editingFinished.connect(self._changed)
        form.addRow(tr("X 軸名稱與單位"), self.xlabel)
        self.view = QComboBox()
        self.view.addItem(tr("總覽：同時顯示勾選指標"), "overview")
        for key, definition in METRICS.items():
            self.view.addItem(tr(definition[0]), key)
        self.view.currentIndexChanged.connect(self._changed)
        form.addRow(tr("顯示方式"), self.view)
        self.plot_type = QComboBox()
        for label, value in ((tr("Dot（點圖）"), "dot"), (tr("Line（折線）"), "line"),
                             (tr("Dot-Line（點與線）"), "dot-line"), (tr("Bar（長條圖）"), "bar"), (tr("Area（填色面積圖）"), "area")):
            self.plot_type.addItem(label, value)
        self.plot_type.currentIndexChanged.connect(self._changed)
        form.addRow(tr("圖型"), self.plot_type)
        section.addLayout(form)
        hint = QLabel(tr("Peak 編號依各次擬合定義；比較前請確認為同一個物理峰。\n對稱峰只選峰頂位置；含非對稱峰時才開放模型中心。"))
        hint.setWordWrap(True)
        section.addWidget(hint)

        section = self._group(tr("3  總覽指標"), layout)
        self.metric_checks = {}
        for key, definition in METRICS.items():
            check = QCheckBox(tr(definition[0]))
            check.toggled.connect(self._changed)
            self.metric_checks[key] = check
            section.addWidget(check)
        self._button(tr("快速恢復：峰頂位置 + FWHM + 面積 + 強度"), self.default_metrics, section)

        section = self._group(tr("4  圖形與輸出"), layout)
        self.checks = {}
        for key, text in (("sort_numeric", tr("數值 Condition 由小到大排列")),
                          ("errorbars", tr("顯示已有的參數標準誤")),
                          ("annotate", tr("標示各點資料名稱")), ("include_failed", tr("納入未收斂結果"))):
            check = QCheckBox(text)
            check.toggled.connect(self._changed)
            self.checks[key] = check
            section.addWidget(check)
        hint = QLabel(tr("誤差棒只使用結果已有的模型中心／面積參數標準誤；\n不推算 FWHM 或峰頂位置誤差。"))
        hint.setWordWrap(True)
        section.addWidget(hint)
        form = QFormLayout()
        self.numbers = {}
        for key, label, lo, hi in (("width_cm", tr("圖寬 cm"), 5, 60), ("height_cm", tr("圖高 cm"), 5, 80),
                                  ("font_size", tr("字級 pt"), 5, 30)):
            widget = QDoubleSpinBox()
            widget.setRange(lo, hi)
            widget.setDecimals(1)
            widget.valueChanged.connect(self._changed)
            self.numbers[key] = widget
            form.addRow(label, widget)
        self.dpi = QSpinBox()
        self.dpi.setRange(72, 1200)
        self.dpi.setSingleStep(50)
        self.dpi.valueChanged.connect(self._changed)
        form.addRow("DPI", self.dpi)
        self.format = QComboBox()
        self.format.addItems(["png", "jpg", "pdf", "svg"])
        form.addRow(tr("分別匯出格式"), self.format)
        section.addLayout(form)
        self._button(tr("匯出目前趨勢圖"), self.export_image.emit, section, True)
        self._button(tr("勾選指標分別匯出成多張圖"), self.export_all.emit, section)
        self._button(tr("匯出趨勢數值 Excel"), self.export_data.emit, section)
        layout.addStretch()
        self.load_settings(DEFAULT_TRENDS)

    def _group(self, title, layout):
        group = QGroupBox(title)
        layout.addWidget(group)
        return QVBoxLayout(group)

    def _button(self, text, callback, layout, primary=False):
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(lambda checked=False: callback())
        layout.addWidget(button)

    def _changed(self):
        if not self.loading:
            self.refresh_position_choices()
            self.changed.emit()

    def refresh_position_choices(self):
        update_position_choices(self.metric_checks, self.view, self.spectra,
                                self.peak.value(), self.checks["include_failed"].isChecked(), self.checks["errorbars"])

    def settings(self):
        self.refresh_position_choices()
        return {**getattr(self, "extra_style", {}), "metrics": [key for key, widget in self.metric_checks.items() if widget.isChecked()],
                "view": self.view.currentData(), "peak": self.peak.value(),
                "x_mode": self.xmode.currentData(), "xlabel": self.xlabel.text(),
                "dpi": self.dpi.value(),
                "plot_type": self.plot_type.currentData(), "connect": self.plot_type.currentData() in ("line", "dot-line", "area"),
                **{key: widget.isChecked() for key, widget in self.checks.items()},
                **{key: widget.value() for key, widget in self.numbers.items()}}

    def load_settings(self, settings):
        if "plot_type" not in settings and settings.get("connect"):
            settings = settings | {"plot_type": "dot-line"}
        settings = DEFAULT_TRENDS | settings
        self.extra_style = {k: v for k, v in settings.items()
                            if k not in {"metrics", "view", "peak", "x_mode", "xlabel", "dpi", "plot_type", "connect",
                                         *self.checks, *self.numbers}}
        self.loading = True
        self.view.setCurrentIndex(max(0, self.view.findData(settings["view"])))
        self.peak.setValue(int(settings["peak"]))
        self.plot_type.setCurrentIndex(max(0, self.plot_type.findData(settings["plot_type"])))
        self.xmode.setCurrentIndex(max(0, self.xmode.findData(settings["x_mode"])))
        self.xlabel.setText(settings["xlabel"])
        self.dpi.setValue(int(settings["dpi"]))
        for key, widget in self.metric_checks.items():
            widget.setChecked(key in settings["metrics"])
        for key, widget in self.checks.items():
            widget.setChecked(bool(settings[key]))
        for key, widget in self.numbers.items():
            widget.setValue(float(settings[key]))
        self.loading = False

        self.refresh_position_choices()

    def set_spectra(self, spectra):
        self.spectra = spectra
        self.loading = True
        self.condition_table.setRowCount(len(spectra))
        for i, s in enumerate(spectra):
            check = QTableWidgetItem()
            check.setFlags((check.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable)
            check.setCheckState(Qt.CheckState.Checked if s.plot else Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, s.id)
            self.condition_table.setItem(i, 0, check)
            name = QTableWidgetItem(s.name)
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name.setToolTip(s.filename)
            self.condition_table.setItem(i, 1, name)
            condition = QTableWidgetItem(s.condition)
            condition.setToolTip(tr('留白時使用：{1}').format('', s.name))
            self.condition_table.setItem(i, 2, condition)
            status = tr("未擬合") if s.result is None else (tr("完成") if s.result["success"] else tr("未收斂"))
            state = QTableWidgetItem(status)
            state.setFlags(state.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.condition_table.setItem(i, 3, state)
        self.loading = False
        self.refresh_position_choices()

    def _condition_edited(self, item):
        if self.loading or item.column() not in (0, 2):
            return
        identity = self.condition_table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        spectrum = next((s for s in self.spectra if s.id == identity), None)
        if spectrum is None:
            return
        if item.column() == 0:
            spectrum.plot = item.checkState() == Qt.CheckState.Checked
            spectrum.trend_include = spectrum.plot
        else:
            spectrum.condition = item.text().strip()
        self.refresh_position_choices()
        self.conditions_changed.emit()

    def _select_all(self, include):
        for s in self.spectra:
            s.plot = s.trend_include = include
        self.set_spectra(self.spectra)
        self.conditions_changed.emit()

    def default_metrics(self):
        self.loading = True
        for key, check in self.metric_checks.items():
            check.setChecked(key in DEFAULT_TRENDS["metrics"])
        self.view.setCurrentIndex(0)
        self.loading = False
        self.changed.emit()
