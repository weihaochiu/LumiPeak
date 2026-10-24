from __future__ import annotations

from .i18n import tr

import copy
import csv
import io
import json
import os
import sys
import threading
import traceback
from dataclasses import asdict
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSignalBlocker
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QColorDialog,
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget,
    QTabBar, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QToolBar, QStyledItemDelegate,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import __version__
from .i18n import initialize_language, language, preferences, retranslate_widgets, saved_message, set_language
from .updates import UpdateChecker, repository
from .data import (FitConfig, Spectrum, clean_json, import_path, load_project,
                   save_project, transformed, write_json)
from .exporting import export_excel, export_opju, export_origin_bundle, export_trend_excel
from .fitting import (MODELS, FitCancelled, build_model, fit_joint, fit_spectrum,
                      parameter_config, peak_candidates)
from .plotting import COLORS, DEFAULT_STYLE, draw_spectra, export_figure
from .trends import DEFAULT_TRENDS, draw_trends, export_trend_set, export_trends
from .trend_ui import TrendPanel
from .overlay import DEFAULT_OVERLAY, draw_overlay, export_overlay_files
from .template_ui import FigureTemplateDialog

ANALYSIS, TRENDS, OVERLAY = 0, 1, 2
TEMPLATE_STYLE_KEYS = ("width_cm", "height_cm", "dpi", "font", "font_size", "line_width", "legend", "grid")


class SpectrumNameDelegate(QStyledItemDelegate):
    """Only the display-name column is editable; file identity stays intact."""

    def createEditor(self, parent, option, index):
        return super().createEditor(parent, option, index) if index.column() == 1 else None


def number(value):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return tr("是") if value else tr("否")
    if isinstance(value, (float, np.floating)):
        return f"{value:.7g}"
    return str(value)


def optional_float(text):
    return float(text.strip()) if text.strip() else None


class ResultsTable(QTableWidget):
    def __init__(self):
        super().__init__()
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)

    def fill(self, headers, rows):
        self.setSortingEnabled(False)
        self.clear()
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(number(value))
                if isinstance(value, (float, int)) and not isinstance(value, bool):
                    item.setData(Qt.ItemDataRole.DisplayRole, value)
                self.setItem(i, j, item)
        self.resizeColumnsToContents()
        for j in range(len(headers)):
            self.setColumnWidth(j, min(300, max(100, self.columnWidth(j))))
        self.setSortingEnabled(True)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            cells = self.selectedIndexes()
            if cells:
                top, bottom = min(c.row() for c in cells), max(c.row() for c in cells)
                left, right = min(c.column() for c in cells), max(c.column() for c in cells)
                selected = {(c.row(), c.column()) for c in cells}
                lines = ["\t".join(self.item(i, j).text() if (i, j) in selected and self.item(i, j) else ""
                                   for j in range(left, right+1)) for i in range(top, bottom+1)]
                QApplication.clipboard().setText("\n".join(lines))
            return
        super().keyPressEvent(event)


class FitWorker(QThread):
    completed = Signal(str, object)
    progress = Signal(str)
    failed = Signal(str)

    def __init__(self, spectra, configs, joint=False):
        super().__init__()
        self.spectra = copy.deepcopy(spectra)
        self.configs = copy.deepcopy(configs)
        self.joint = joint
        self.cancel = threading.Event()

    def run(self):
        try:
            if self.joint:
                self.progress.emit(tr('聯合擬合 {1} 條光譜…').format('', len(self.spectra), ''))
                results = fit_joint(self.spectra, self.configs, self.configs[0].shared, self.cancel)
                for spectrum, result in zip(self.spectra, results):
                    self.completed.emit(spectrum.id, result)
            else:
                for i, (spectrum, config) in enumerate(zip(self.spectra, self.configs), 1):
                    if self.cancel.is_set():
                        break
                    self.progress.emit(tr('擬合 {1}/{3}：{5}').format('', i, '', len(self.spectra), '', spectrum.name))
                    try:
                        self.completed.emit(spectrum.id, fit_spectrum(spectrum, config, self.cancel))
                    except FitCancelled:
                        raise
                    except Exception as exc:
                        self.failed.emit(f"{spectrum.filename}：{exc}")
        except FitCancelled:
            self.progress.emit(tr("擬合已取消；先前完成的結果已保留。"))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.spectra: list[Spectrum] = []
        self.current_id = None
        self.project_path = None
        self.dirty = False
        self.loading = False
        self.worker = None
        self.last_errors = []
        self.preview = None
        self.add_on_click = False
        self.update_checker = UpdateChecker(self)
        self.update_checker.checked.connect(self._update_checked)
        self.update_checker.failed.connect(self._update_failed)
        self.update_manual = False
        self.shutting_down = False
        self.plot_settings = copy.deepcopy(DEFAULT_STYLE)
        self.setWindowTitle("PL Studio — Steady-state photoluminescence")
        self.resize(1600, 960)
        self.setMinimumSize(1120, 720)
        self.setAcceptDrops(True)
        self._build_toolbar()
        self._build_layout()
        self._style()
        self._build_settings()
        retranslate_widgets(self)
        self._update_title()
        self._draw()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave)
        self.autosave_timer.start(60000)
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._startup_update)
        self.update_timer.start(1500)

    def _build_settings(self):
        menu = self.menuBar().addMenu(tr("設定"))
        languages = menu.addMenu("語言 / Language")
        for label, value in (("繁體中文", "zh_TW"), ("English", "en")):
            action = languages.addAction(label)
            action.triggered.connect(lambda checked=False, value=value: self.change_language(value))
        self.auto_update_action = menu.addAction(tr("啟動時檢查更新"))
        self.auto_update_action.setCheckable(True)
        self.auto_update_action.setChecked(preferences().value("updates/enabled", True, type=bool))
        self.auto_update_action.toggled.connect(lambda value: preferences().setValue("updates/enabled", value))
        menu.addAction(tr("立即檢查更新"), lambda: self.check_updates(manual=True))
        menu.addAction(tr("關於 PL Studio"), self.about)

    def change_language(self, value):
        if value == language():
            return
        # Keep pending parameter edits in their existing widgets. Translating
        # presentation text must not commit, reset or validate scientific input.
        set_language(value)
        retranslate_widgets(self)
        self._refresh_tree()
        self.original_filename.setText(tr("原始檔：") + self.current.filename
            if self.current else tr("尚未選取資料"))
        self._refresh_tables()
        self._update_title()
        self._draw()
        self.statusBar().showMessage(tr("介面語言已切換。"), 5000)

    def about(self):
        QMessageBox.information(self, tr("關於 PL Studio"),
            f"PL Studio {__version__}\n\n" + tr("繁體中文與英文介面，可在設定選單切換。")
            + "\n" + (f"https://github.com/{repository()}" if repository() else tr("尚未設定 GitHub 更新來源。")))

    def _startup_update(self):
        if self.auto_update_action.isChecked() and repository():
            self.check_updates()

    def check_updates(self, manual=False):
        if self.update_checker.reply is not None:
            return
        if not repository():
            if manual:
                QMessageBox.information(self, tr("檢查更新"), tr("尚未設定 GitHub 更新來源。"))
            return
        self.update_manual = manual
        self.update_checker.start()

    def _update_failed(self, detail):
        if self.shutting_down:
            return
        if self.update_manual:
            QMessageBox.information(self, tr("檢查更新"),
                tr("目前無法檢查更新，請稍後再試。軟體仍可正常使用。") + "\n\n" + detail)

    def _update_checked(self, release):
        if self.shutting_down:
            return
        if release is None:
            if self.update_manual:
                QMessageBox.information(self, tr("檢查更新"), tr("目前已是最新版本。"))
            return
        if not self.update_manual and preferences().value("updates/skipped", "") == release.version:
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle(tr("發現新版本"))
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(tr("目前版本：{0}\n最新版本：{1}").format(__version__, release.version))
        dialog.setInformativeText(tr("下載安裝檔後，請儲存專案並關閉軟體，再執行安裝。"))
        if release.notes:
            dialog.setDetailedText(release.notes)
        download = dialog.addButton(tr("下載更新"), QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton(tr("稍後提醒"), QMessageBox.ButtonRole.RejectRole)
        skip = dialog.addButton(tr("略過此版本"), QMessageBox.ButtonRole.ActionRole)
        dialog.exec()
        if dialog.clickedButton() is download:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(release.download_url))
        elif dialog.clickedButton() is skip:
            preferences().setValue("updates/skipped", release.version)

    @property
    def current(self):
        return next((s for s in self.spectra if s.id == self.current_id), None)

    def _style(self):
        QApplication.instance().setStyle("Fusion")
        # Register a local CJK font explicitly: the offscreen Qt backend may not
        # enumerate Windows fonts, even though the normal desktop backend does.
        for filename in ("msjh.ttc", "msyh.ttc", "mingliu.ttc"):
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
            if font_path.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    self.ui_font = families[0]
                    QApplication.instance().setFont(QFont(self.ui_font, 9))
                    break
        else:
            self.ui_font = "Microsoft JhengHei"
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f4f7fa; color: #20354a; font-family: 'UI_FONT'; font-size: 12px; }
            QToolBar#mainToolBar { background: #173b5a; spacing: 8px; padding: 7px; border: none; }
            QToolBar#mainToolBar QToolButton { background: transparent; color: white; padding: 7px 9px; border-radius: 4px; }
            QToolBar#mainToolBar QToolButton:hover { background: #2b5575; }
            QGroupBox { border: 1px solid #d6e0e9; border-radius: 6px; margin-top: 14px; padding: 10px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
            QPushButton { background: white; border: 1px solid #c9d6e2; border-radius: 4px; padding: 6px 9px; }
            QPushButton:hover { background: #e4eef7; border-color: #759dbb; }
            QPushButton:disabled { color: #9caab5; }
            QPushButton#primary { background: #1868b2; color: white; border: none; font-weight: bold; padding: 10px; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit { background: white; border: 1px solid #ccd7e1; border-radius: 3px; padding: 4px; }
            QTreeWidget, QTableWidget { background: white; alternate-background-color: #f0f5fa; border: 1px solid #d5dfe8; selection-background-color: #d6e8f8; selection-color: #173b5a; }
            QHeaderView::section { background: #e8eff5; color: #29465f; padding: 6px; border: none; border-right: 1px solid #d2dee8; }
            QTabBar::tab { padding: 9px 18px; background: #e6edf4; border: none; }
            QTabBar::tab:selected { background: white; color: #1868b2; border-bottom: 3px solid #1868b2; }
            QStatusBar { background: #e6edf4; }
        """.replace("UI_FONT", self.ui_font))

    def _action(self, label, slot, shortcut=None):
        action = QAction(label, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        self.toolbar.addAction(action)
        return action

    def _build_toolbar(self):
        self.toolbar = QToolBar(tr("專案與匯出"))
        self.toolbar.setObjectName("mainToolBar")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        self._action(tr("新增專案"), self.new_project, "Ctrl+N")
        self._action(tr("開啟專案"), self.open_project, "Ctrl+O")
        self._action(tr("儲存"), self.save, "Ctrl+S")
        self._action(tr("另存新檔"), lambda: self.save(True), "Ctrl+Shift+S")
        self.toolbar.addSeparator()
        self._action(tr("匯入 TXT / ZIP"), self.import_files, "Ctrl+I")
        self.toolbar.addSeparator()
        self._action("Figure Template", self.open_figure_template, "Ctrl+T")
        self._action(tr("匯出圖片"), self.export_image)
        self._action(tr("匯出 Excel"), self.export_xlsx)
        self._action(tr("Origin 資料包"), self.export_origin).setToolTip(tr("匯出資料及基本圖形腳本；目前不轉換 Figure Template 樣式。"))
        self._action("Origin .opju", self.export_origin_project).setToolTip(tr("需 Origin 授權；目前只建立資料與基本曲線，未同步 Figure Template。"))
        self.toolbar.addSeparator()
        self._action(tr("使用說明"), self.help)

    def _button(self, text, slot, layout, primary=False):
        button = QPushButton(text)
        button.clicked.connect(lambda checked=False: slot())
        if primary:
            button.setObjectName("primary")
        layout.addWidget(button)
        return button

    def _build_layout(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)
        self.left = QWidget()
        left = QVBoxLayout(self.left)
        heading = QLabel(tr("光譜資料"))
        heading.setStyleSheet("font-size: 18px; font-weight: bold; padding: 5px;")
        left.addWidget(heading)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("搜尋檔名或顯示名稱"))
        self.search.textChanged.connect(self._filter)
        left.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("作圖"), tr("使用者定義名稱"), tr("狀態")])
        self.tree.setItemDelegate(SpectrumNameDelegate(self.tree))
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setColumnWidth(0, 42)
        self.tree.setColumnWidth(1, 150)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemChanged.connect(self._spectrum_item_changed)
        left.addWidget(self.tree, 1)
        hint = QLabel(tr("雙擊名稱或按 F2 編輯；PL 疊圖與趨勢圖共用。\nCtrl / Shift 多選；勾選同步控制兩種比較圖。"))
        hint.setWordWrap(True)
        left.addWidget(hint)
        row = QHBoxLayout()
        self._button(tr("全選作圖"), lambda: self._check_all(True), row)
        self._button(tr("清除作圖"), lambda: self._check_all(False), row)
        left.addLayout(row)
        row = QHBoxLayout()
        self._button(tr("上移"), lambda: self.move_current(-1), row)
        self._button(tr("下移"), lambda: self.move_current(1), row)
        left.addLayout(row)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("輸入名稱後按 Enter"))
        self.name_edit.setToolTip(tr("套用到 PL 疊圖圖例、趨勢資料名稱與標註；Condition 留白時也作為 X 軸名稱。"))
        self.name_edit.editingFinished.connect(self.rename_current)
        label = QLabel(tr("使用者定義名稱（兩種比較圖共用）"))
        label.setWordWrap(True)
        left.addWidget(label)
        left.addWidget(self.name_edit)
        self.original_filename = QLabel()
        self.original_filename.setWordWrap(True)
        self.original_filename.setTextFormat(Qt.TextFormat.PlainText)
        self.original_filename.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        left.addWidget(self.original_filename)
        self._button(tr("從專案移除選取資料"), self.remove_selected, left)
        splitter.addWidget(self.left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(3, 8, 3, 0)
        self.mode = QTabBar()
        self.mode.addTab(tr("光譜分析"))
        self.mode.addTab(tr("參數趨勢圖"))
        self.mode.addTab(tr("PL 疊圖"))
        self.mode.currentChanged.connect(self._mode_changed)
        center_layout.addWidget(self.mode)
        vertical = QSplitter(Qt.Orientation.Vertical)
        chart = QWidget()
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        self.chart_info = QLabel(tr("尚未匯入資料"))
        self.chart_info.setWordWrap(True)
        self.chart_info.setStyleSheet("color: #55718a; padding: 5px 8px;")
        chart_layout.addWidget(self.chart_info)
        self.figure = Figure(figsize=(8, 5), facecolor="white")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.navigation = NavigationToolbar2QT(self.canvas, self)
        chart_layout.addWidget(self.navigation)
        chart_layout.addWidget(self.canvas, 1)
        self.canvas.mpl_connect("button_press_event", self._canvas_click)
        vertical.addWidget(chart)
        self.tables = QTabWidget()
        self.summary = ResultsTable()
        self.peak_table = ResultsTable()
        self.detail_table = ResultsTable()
        self.metadata_table = ResultsTable()
        self.history_table = ResultsTable()
        self.trend_table = ResultsTable()
        for widget, label in [(self.summary, tr("結果總覽")), (self.peak_table, tr("分峰結果")),
                              (self.detail_table, tr("參數與誤差")), (self.metadata_table, tr("量測資訊")),
                              (self.history_table, tr("擬合紀錄")), (self.trend_table, tr("趨勢數值"))]:
            self.tables.addTab(widget, label)
        self.summary.cellClicked.connect(self._summary_clicked)
        self.history_table.cellDoubleClicked.connect(self._restore_history)
        vertical.addWidget(self.tables)
        vertical.setSizes([570, 230])
        center_layout.addWidget(vertical, 1)
        splitter.addWidget(center)

        self.right = QStackedWidget()
        self.right.addWidget(self._analysis_controls())
        self.trend_panel = TrendPanel()
        self.trend_panel.changed.connect(self._trend_changed)
        self.trend_panel.conditions_changed.connect(self._conditions_changed)
        self.trend_panel.export_image.connect(self.export_trend_image)
        self.trend_panel.export_all.connect(self.export_all_trend_images)
        self.trend_panel.export_data.connect(self.export_trend_data)
        self.right.addWidget(self.trend_panel)
        self.right.addWidget(self._overlay_controls())
        self._build_template_dialog()
        splitter.addWidget(self.right)
        splitter.setSizes([270, 900, 430])
        splitter.setStretchFactor(1, 1)
        self.cancel_button = QPushButton(tr("取消擬合"))
        self.cancel_button.clicked.connect(self.cancel_fit)
        self.cancel_button.setEnabled(False)
        self.statusBar().addPermanentWidget(self.cancel_button)
        self.statusBar().showMessage(tr("匯入 TXT 或 ZIP 開始分析；原始資料會保存在專案內。"))

    def _scroll(self):
        area = QScrollArea()
        area.setWidgetResizable(True)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        area.setWidget(widget)
        return area, layout

    def _group(self, title, parent_layout):
        group = QGroupBox(title)
        parent_layout.addWidget(group)
        return QVBoxLayout(group)

    def _analysis_controls(self):
        area, layout = self._scroll()
        section = self._group(tr("1  資料與擬合範圍"), layout)
        form = QFormLayout()
        self.domain = QComboBox()
        self.domain.addItems(["nm", "eV"])
        self.domain.currentTextChanged.connect(self._domain_changed)
        self.jacobian = QCheckBox(tr("每 nm → 每 eV：Jacobian"))
        self.jacobian.setToolTip(tr("僅適用於強度已定義為每 nm 的光譜密度。Counts/pixel 不會自動當成每 nm。"))
        self.jacobian.toggled.connect(self._coordinate_changed)
        self.normalization = QComboBox()
        self.normalization.addItems(["none", "max", "area"])
        self.normalization.currentTextChanged.connect(self._coordinate_changed)
        self.xmin, self.xmax = QLineEdit(), QLineEdit()
        self.xmin.setPlaceholderText(tr("留白＝全範圍"))
        self.xmax.setPlaceholderText(tr("留白＝全範圍"))
        form.addRow(tr("擬合座標"), self.domain)
        form.addRow(tr("密度轉換"), self.jacobian)
        form.addRow(tr("擬合歸一化"), self.normalization)
        form.addRow(tr("區間起點"), self.xmin)
        form.addRow(tr("區間終點"), self.xmax)
        self.mask_edit = QLineEdit()
        self.mask_edit.setPlaceholderText(tr("例如 750:755; 850:852"))
        form.addRow(tr("排除區間"), self.mask_edit)
        section.addLayout(form)
        section.addWidget(QLabel(tr("在主圖按住 Shift 拖曳，可選擬合區間。")))
        row = QHBoxLayout()
        self._button(tr("套用區間"), self.apply_range, row)
        self._button(tr("全範圍"), self.full_range, row)
        section.addLayout(row)

        section = self._group(tr("2  背景與分峰"), layout)
        form = QFormLayout()
        self.background = QComboBox()
        self.background.addItems(["constant", "linear", "none"])
        self.background.currentTextChanged.connect(self._background_changed)
        self.model_choice = QComboBox()
        self.model_choice.addItems(list(MODELS))
        form.addRow(tr("背景模型"), self.background)
        form.addRow(tr("新增峰形"), self.model_choice)
        self.prominence = QDoubleSpinBox()
        self.prominence.setRange(0.01, 0.9)
        self.prominence.setSingleStep(0.01)
        self.prominence.setValue(0.06)
        form.addRow(tr("找峰相對顯著度"), self.prominence)
        section.addLayout(form)
        self.peak_list = QTreeWidget()
        self.peak_list.setRootIsDecorated(False)
        self.peak_list.setHeaderLabels([tr("分峰"), tr("模型")])
        self.peak_list.setMaximumHeight(135)
        section.addWidget(self.peak_list)
        row = QHBoxLayout()
        self._button(tr("新增峰"), self.add_peak, row)
        self._button(tr("移除峰"), self.delete_peak, row)
        section.addLayout(row)
        row = QHBoxLayout()
        self._button(tr("點圖加峰"), self.arm_add_peak, row)
        self._button(tr("自動找峰"), self.auto_peaks, row)
        section.addLayout(row)
        self._button(tr("以所選峰形替換選取分峰"), self.replace_peak, section)

        section = self._group(tr("3  參數約束"), layout)
        hint = QLabel(tr("雙擊編輯；空白界限＝無限。\n面積＝amplitude；sigma / gamma 為模型寬度。\n關係式例：p2_center = p1_center + 5（右欄只填右式）"))
        hint.setWordWrap(True)
        section.addWidget(hint)
        self.param_table = QTableWidget()
        self.param_table.setColumnCount(7)
        self.param_table.setHorizontalHeaderLabels([tr("參數"), tr("初始值"), tr("下限"), tr("上限"), tr("固定"), tr("關係式"), tr("共用")])
        self.param_table.setMinimumHeight(220)
        self.param_table.setAlternatingRowColors(True)
        for i, width in enumerate([125, 90, 75, 75, 45, 150, 45]):
            self.param_table.setColumnWidth(i, width)
        self.param_table.itemChanged.connect(lambda: self.mark_dirty() if not self.loading else None)
        section.addWidget(self.param_table)
        row = QHBoxLayout()
        self._button(tr("預覽初始模型"), self.preview_model, row)
        self._button(tr("重設初始值"), self.reset_parameters, row)
        section.addLayout(row)

        section = self._group(tr("4  執行擬合"), layout)
        form = QFormLayout()
        self.starts = QSpinBox()
        self.starts.setRange(1, 10)
        self.starts.setValue(3)
        form.addRow(tr("初始值重試次數"), self.starts)
        section.addLayout(form)
        self._button(tr("擬合目前光譜"), lambda: self.start_fit("single"), section, True)
        self._button(tr("批次擬合選取光譜"), lambda: self.start_fit("batch"), section)
        self._button(tr("聯合擬合選取光譜（使用共用欄）"), lambda: self.start_fit("joint"), section)
        self._button(tr("套用目前設定至選取光譜"), self.apply_to_selected, section)
        section.addWidget(QLabel(tr("批次使用各資料的設定；聯合使用目前設定。")))
        section = self._group(tr("樣品／量測備註"), layout)
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(100)
        self.notes.setPlaceholderText(tr("可填樣品結構、激發波長／功率、樣品溫度等。"))
        self.notes.textChanged.connect(lambda: self.mark_dirty() if not self.loading else None)
        section.addWidget(self.notes)
        layout.addStretch()
        return area

    def _paper_controls(self):
        area, layout = self._scroll()
        self.plot_inputs = {}
        section = self._group(tr("圖形內容"), layout)
        self.template_content_group = section.parentWidget()
        for key, label in [("raw", tr("原始資料")), ("fit", tr("總擬合線")), ("components", tr("各分峰")),
                           ("background", tr("背景")), ("residual", tr("殘差面板")), ("legend", tr("圖例")),
                           ("grid", tr("格線")), ("logy", tr("Y 軸對數")), ("normalize", tr("作圖歸一化（不改擬合）"))]:
            check = QCheckBox(label)
            check.setChecked(bool(self.plot_settings[key]))
            check.toggled.connect(self._paper_changed)
            self.plot_inputs[key] = check
            section.addWidget(check)
        section = self._group(tr("尺寸與樣式"), layout)
        form = QFormLayout()
        for key, label in [("width_cm", tr("寬度 cm")), ("height_cm", tr("高度 cm")), ("dpi", tr("解析度 DPI")),
                           ("font", tr("字型")), ("font_size", tr("字級 pt")), ("line_width", tr("線寬 pt")),
                           ("offset", tr("各線垂直間距")), ("title", tr("圖標題")),
                           ("xlabel", tr("X 軸標籤")), ("ylabel", tr("Y 軸標籤")),
                           ("xmin", tr("X 下限")), ("xmax", tr("X 上限")), ("ymin", tr("Y 下限")), ("ymax", tr("Y 上限"))]:
            value = self.plot_settings[key]
            edit = QLineEdit("" if value is None else str(value))
            edit.editingFinished.connect(self._paper_changed)
            self.plot_inputs[key] = edit
            form.addRow(label, edit)
        section.addLayout(form)
        self._button(tr("套用到預覽對象"), lambda: self.apply_figure_template(False), section, True)
        self._button(tr("套用通用樣式到所有圖形"), lambda: self.apply_figure_template(True), section)
        section = self._group(tr("單條線設定"), layout)
        self.style_spectrum = QComboBox()
        section.addWidget(self.style_spectrum)
        self._button(tr("選擇線條顏色"), self.choose_color, section)
        self.linestyle = QComboBox()
        self.linestyle.addItems(["-", "--", "-.", ":"])
        section.addWidget(self.linestyle)
        self._button(tr("套用線型"), self.apply_linestyle, section)
        section = self._group(tr("期刊模板"), layout)
        row = QHBoxLayout()
        self._button(tr("儲存模板"), self.save_template, row)
        self._button(tr("載入模板"), self.load_template, row)
        section.addLayout(row)
        label = QLabel(tr("第一版提供可調整與儲存的樣式模板。\n收到期刊範例後，可據此製作專用模板。"))
        label.setWordWrap(True)
        section.addWidget(label)
        self._button(tr("匯出此預覽圖形"), self.export_template_preview, layout, True)
        layout.addStretch()
        return area

    def _build_template_dialog(self):
        # Retain the original style fields as a compatibility bridge for old
        # projects. The visible editor is the per-figure template dialog.
        self._legacy_style_controls = self._paper_controls()
        self._legacy_style_controls.setParent(self)
        self._legacy_style_controls.hide()
        self.template_dialog = FigureTemplateDialog(self, self._render_template_preview)
        self.template_dialog.applied.connect(self._apply_template_bundle)

    def open_figure_template(self):
        target = {ANALYSIS: "spectrum", TRENDS: "trends", OVERLAY: "overlay"}[self.mode.currentIndex()]
        if not self.template_dialog.isVisible():
            self.template_dialog.set_bundle({
                "spectrum": {k: copy.deepcopy(v) for k, v in self.plot_settings.items() if k not in ("trends", "overlay")},
                "trends": self.trend_panel.settings(), "overlay": self._read_overlay_inputs()}, target)
        self.template_dialog.show()
        self.template_dialog.raise_()
        self.template_dialog.activateWindow()

    def _template_payload(self):
        return self.template_dialog.active_kind, self.template_dialog.read_settings()

    def _draw_template_preview(self):
        self.template_dialog.preview()

    def _render_template_preview(self, figure, target, settings):
        if target == "trends":
            draw_trends(figure, self.spectra, settings, settings.get("font", self.ui_font))
        elif target == "overlay":
            draw_overlay(figure, self.spectra, settings)
        else:
            draw_spectra(figure, [s for s in self.spectra if s.plot], settings)

    def apply_figure_template(self, all_targets=False):
        self.template_dialog.apply(all_targets)

    def _apply_template_bundle(self, bundle):
        current = self._read_plot_inputs()
        if "spectrum" in bundle:
            current.update({k: copy.deepcopy(v) for k, v in bundle["spectrum"].items()
                            if k in DEFAULT_STYLE or k == "figure_options"})
        for target in ("trends", "overlay"):
            if target in bundle:
                current[target] = copy.deepcopy(bundle[target])
        self.plot_settings = current
        self._load_plot_inputs()
        self.mark_dirty()
        self._draw()
        self.statusBar().showMessage(tr("Figure Template 已套用；三種圖型的設定分別保存。"))

    def export_template_preview(self):
        try:
            target, settings = self._template_payload()
            path, _ = QFileDialog.getSaveFileName(self.template_dialog, tr("匯出 Figure Template 預覽"), "PL_figure.png",
                "PNG (*.png);;JPEG (*.jpg);;PDF (*.pdf);;SVG (*.svg)")
            if path:
                if target == "trends":
                    export_trends(path, self.spectra, settings, settings["font"])
                elif target == "overlay":
                    from .overlay import export_overlay
                    export_overlay(path, self.spectra, settings)
                else:
                    export_figure(path, [s for s in self.spectra if s.plot], settings)
                self.statusBar().showMessage(tr('圖形已匯出：{1}').format('', path))
        except Exception as exc:
            self._error(exc)

    def mark_dirty(self):
        if self.loading:
            return
        self.dirty = True
        self._update_title()

    def _overlay_controls(self):
        area, layout = self._scroll()
        self.overlay_widgets = {}
        section = self._group(tr("選取光譜疊圖"), layout)
        note = QLabel(tr("使用左側勾選的所有光譜；取消勾選會立即移除。\nX 軸固定為波長 nm，使用完整原始資料。"))
        note.setWordWrap(True)
        section.addWidget(note)
        form = QFormLayout()
        self.overlay_intensity = QComboBox()
        self.overlay_intensity.addItem(tr("原始值 Intensity（Counts）"), "raw")
        self.overlay_intensity.addItem("Normalized intensity（I / Imax）", "normalized")
        self.overlay_intensity.addItem(tr("兩者同時顯示（原始值 + Normalized）"), "both")
        self.overlay_intensity.setCurrentIndex(self.overlay_intensity.findData(DEFAULT_OVERLAY["intensity"]))
        self.overlay_intensity.currentIndexChanged.connect(self._overlay_changed)
        form.addRow(tr("預覽顯示"), self.overlay_intensity)
        self.overlay_widgets["intensity"] = self.overlay_intensity
        section.addLayout(form)
        note = QLabel(tr("原始值保留儀器 Counts；Normalized 將每條光譜除以其完整量測範圍的最大值，峰值為 1，不自動扣背景。\n此頁顯示與擬合採用的座標／歸一化分開。"))
        note.setWordWrap(True)
        section.addWidget(note)
        section = self._group(tr("顯示與輸出"), layout)
        form = QFormLayout()
        for key, label, low, high in (("width_cm", tr("圖寬 cm"), 5, 60), ("height_cm", tr("圖高 cm"), 5, 80),
                                      ("font_size", tr("字級 pt"), 5, 30), ("line_width", tr("線寬 pt"), .1, 10)):
            widget = QDoubleSpinBox()
            widget.setRange(low, high)
            widget.setDecimals(1)
            widget.setValue(DEFAULT_OVERLAY[key])
            widget.valueChanged.connect(self._overlay_changed)
            self.overlay_widgets[key] = widget
            form.addRow(label, widget)
        dpi = QSpinBox()
        dpi.setRange(72, 1200)
        dpi.setValue(DEFAULT_OVERLAY["dpi"])
        dpi.valueChanged.connect(self._overlay_changed)
        self.overlay_widgets["dpi"] = dpi
        form.addRow("DPI", dpi)
        for key, label in (("title", tr("標題")), ("xmin", tr("波長下限 nm")), ("xmax", tr("波長上限 nm"))):
            widget = QLineEdit()
            widget.setPlaceholderText(tr("留白使用完整範圍") if key != "title" else "")
            widget.editingFinished.connect(self._overlay_changed)
            self.overlay_widgets[key] = widget
            form.addRow(label, widget)
        section.addLayout(form)
        for key, label in (("legend", tr("顯示圖例（使用自訂名稱）")), ("grid", tr("顯示格線"))):
            widget = QCheckBox(label)
            widget.setChecked(DEFAULT_OVERLAY[key])
            widget.toggled.connect(self._overlay_changed)
            self.overlay_widgets[key] = widget
            section.addWidget(widget)
        self._button(tr("更新疊圖"), self._overlay_changed, section, True)
        section = self._group(tr("圖檔輸出選擇"), layout)
        form = QFormLayout()
        self.overlay_export = QComboBox()
        for label, value in ((tr("原始值 + Normalized，分別兩個圖檔"), "separate"),
                             (tr("只輸出原始 Intensity"), "raw"), (tr("只輸出 Normalized intensity"), "normalized"),
                             (tr("兩者合成同一張圖"), "both"), (tr("依目前預覽顯示"), "current")):
            self.overlay_export.addItem(label, value)
        self.overlay_export.currentIndexChanged.connect(self._overlay_changed)
        self.overlay_widgets["export_mode"] = self.overlay_export
        form.addRow(tr("輸出內容"), self.overlay_export)
        section.addLayout(form)
        section.addWidget(QLabel(tr("分別輸出時，檔名自動加上 _intensity 與 _normalized。")))
        self._button(tr("匯出疊圖 PNG / JPG / PDF / SVG"), self.export_overlay_image, layout, True)
        layout.addStretch()
        return area

    def _read_overlay_inputs(self):
        settings = copy.deepcopy(getattr(self, "overlay_extra", {}))
        for key, widget in self.overlay_widgets.items():
            if isinstance(widget, QComboBox):
                value = widget.currentData()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                value = widget.value()
            elif key in ("xmin", "xmax"):
                value = optional_float(widget.text())
                if value is not None and (not np.isfinite(value) or value <= 0):
                    raise ValueError(tr("疊圖波長範圍必須為有限正數。"))
            else:
                value = widget.text()
            settings[key] = value
        if settings["xmin"] is not None and settings["xmax"] is not None and settings["xmin"] >= settings["xmax"]:
            raise ValueError(tr("疊圖波長下限必須小於上限。"))
        return settings

    def _load_overlay_inputs(self):
        settings = DEFAULT_OVERLAY | self.plot_settings.get("overlay", {})
        self.overlay_extra = {k: copy.deepcopy(v) for k, v in settings.items() if k not in self.overlay_widgets}
        self.loading = True
        for key, widget in self.overlay_widgets.items():
            value = settings[key]
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(max(0, widget.findData(value)))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(value)
            else:
                widget.setText("" if value is None else str(value))
        self.loading = False

    def _overlay_changed(self):
        if self.loading or not hasattr(self, "overlay_widgets"):
            return
        try:
            self.plot_settings["overlay"] = self._read_overlay_inputs()
            self.mark_dirty()
            if self.mode.currentIndex() == OVERLAY:
                self._draw()
        except Exception as exc:
            self.statusBar().showMessage(str(exc))

    def export_overlay_image(self):
        try:
            settings = self._read_overlay_inputs()
            if not any(s.plot for s in self.spectra):
                raise ValueError(tr("請先在左側勾選要疊圖的光譜。"))
            path, _ = QFileDialog.getSaveFileName(self, tr("匯出選取光譜疊圖"), "PL_overlay.png",
                "PNG (*.png);;JPEG (*.jpg);;PDF (*.pdf);;SVG (*.svg)")
            if path:
                paths = export_overlay_files(path, self.spectra, settings)
                self.statusBar().showMessage(tr("PL 疊圖已匯出：")+"；".join(str(p) for p in paths))
        except Exception as exc:
            self._error(exc)

    def _update_title(self):
        name = Path(self.project_path).stem if self.project_path else tr("未命名專案")
        self.setWindowTitle(f"PL Studio {__version__}  |  {name}{' ●' if self.dirty else ''}")

    def _error(self, exc):
        QMessageBox.warning(self, tr("操作未完成"), str(exc))
        self.statusBar().showMessage(str(exc).splitlines()[0])

    def _selected(self):
        ids = {item.data(0, Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()}
        return [s for s in self.spectra if s.id in ids]

    def _refresh_tree(self):
        self.loading = True
        selected = {s.id for s in self._selected()}
        self.tree.clear()
        counts = {}
        for s in self.spectra:
            s.trend_include = s.plot
            counts[s.digest] = counts.get(s.digest, 0)+1
        for s in self.spectra:
            status = tr("未擬合") if not s.result else (tr("完成") if s.result["success"] else tr("未收斂"))
            if s.result and s.result["warnings"]:
                status += " ⚠"
            if counts[s.digest] > 1:
                status += tr(" / 重複")
            item = QTreeWidgetItem(["", s.name, status])
            item.setData(0, Qt.ItemDataRole.UserRole, s.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
            item.setCheckState(0, Qt.CheckState.Checked if s.plot else Qt.CheckState.Unchecked)
            item.setToolTip(1, tr("雙擊或按 F2 編輯共用名稱\n原始檔：")+s.filename+"\nSHA256: "+s.digest)
            if s.result:
                item.setToolTip(2, "\n".join(saved_message(w) for w in s.result["warnings"])
                    or saved_message(s.result["message"]))
            self.tree.addTopLevelItem(item)
            if s.id in selected or s.id == self.current_id:
                item.setSelected(True)
        self.style_spectrum.clear()
        for s in self.spectra:
            self.style_spectrum.addItem(s.name, s.id)
        self.loading = False
        if hasattr(self, "trend_panel"):
            self.trend_panel.set_spectra(self.spectra)
        self._filter()

    def _filter(self):
        query = self.search.text().casefold()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            s = next(s for s in self.spectra if s.id == item.data(0, Qt.ItemDataRole.UserRole))
            item.setHidden(query not in (s.name+" "+s.filename).casefold())

    def move_current(self, step):
        if not self.current:
            return
        index = self.spectra.index(self.current)
        target = index+step
        if 0 <= target < len(self.spectra):
            self.spectra[index], self.spectra[target] = self.spectra[target], self.spectra[index]
            self.mark_dirty()
            self._refresh_tree()
            self._refresh_tables()
            self._draw()

    def _spectrum_item_changed(self, item, column):
        if self.loading:
            return
        if column == 1:
            identity = item.data(0, Qt.ItemDataRole.UserRole)
            spectrum = next((s for s in self.spectra if s.id == identity), None)
            if spectrum is not None:
                self._rename_spectrum(spectrum, item.text(1))
        else:
            self._plot_check_changed(item, column)

    def _plot_check_changed(self, item, column):
        if self.loading or column != 0:
            return
        s = next(s for s in self.spectra if s.id == item.data(0, Qt.ItemDataRole.UserRole))
        s.plot = item.checkState(0) == Qt.CheckState.Checked
        s.trend_include = s.plot
        self.trend_panel.set_spectra(self.spectra)
        self.mark_dirty()
        if self.mode.currentIndex() in (TRENDS, OVERLAY):
            self._draw()

    def _check_all(self, checked):
        for s in self.spectra:
            s.plot = s.trend_include = checked
        self.mark_dirty()
        self._refresh_tree()
        self._draw()

    def _selection_changed(self):
        if self.loading:
            return
        item = self.tree.currentItem()
        if item is None:
            return
        new_id = item.data(0, Qt.ItemDataRole.UserRole)
        if new_id == self.current_id:
            return
        try:
            self._commit()
        except Exception as exc:
            self._error(exc)
            self._refresh_tree()
            return
        self.current_id = new_id
        self.preview = None
        self._load_controls()
        self._refresh_tables()
        self._draw()

    def _commit(self):
        s = self.current
        if s is None:
            return
        config = copy.deepcopy(s.config)
        config.domain = self.domain.currentText()
        config.jacobian = self.jacobian.isChecked() and config.domain == "eV"
        config.normalization = self.normalization.currentText()
        config.xmin, config.xmax = optional_float(self.xmin.text()), optional_float(self.xmax.text())
        config.excluded = []
        for segment in self.mask_edit.text().split(";"):
            if segment.strip():
                pair = segment.split(":")
                if len(pair) != 2:
                    raise ValueError(tr("排除區間格式為 起點:終點；多段以半形分號分開。"))
                config.excluded.append([float(pair[0]), float(pair[1])])
        config.background = self.background.currentText()
        config.starts = self.starts.value()
        config.parameters, config.shared = {}, []
        for row in range(self.param_table.rowCount()):
            name = self.param_table.item(row, 0).text()
            value = float(self.param_table.item(row, 1).text())
            lo = optional_float(self.param_table.item(row, 2).text())
            hi = optional_float(self.param_table.item(row, 3).text())
            fixed = self.param_table.item(row, 4).checkState() == Qt.CheckState.Checked
            expr = self.param_table.item(row, 5).text().strip()
            config.parameters[name] = {"value": value, "min": lo, "max": hi,
                                       "vary": not fixed, "expr": expr}
            if self.param_table.item(row, 6).checkState() == Qt.CheckState.Checked:
                config.shared.append(name)
        # Validate before changing the current spectrum.
        build_model(s, config)
        changed = clean_json(asdict(config)) != clean_json(asdict(s.config)) or self.notes.toPlainText() != s.notes
        s.config, s.notes = config, self.notes.toPlainText()
        if changed:
            self.mark_dirty()

    def _load_controls(self):
        self.loading = True
        s = self.current
        config = s.config if s else FitConfig()
        self.domain.setCurrentText(config.domain)
        self.jacobian.setChecked(config.jacobian)
        self.jacobian.setEnabled(config.domain == "eV")
        self.normalization.setCurrentText(config.normalization)
        self.xmin.setText("" if config.xmin is None else str(config.xmin))
        self.xmax.setText("" if config.xmax is None else str(config.xmax))
        self.mask_edit.setText("; ".join(f"{a}:{b}" for a, b in config.excluded))
        self.background.setCurrentText(config.background)
        self.starts.setValue(config.starts)
        self.name_edit.setText(s.name if s else "")
        self.name_edit.setEnabled(s is not None)
        self.original_filename.setText(tr("原始檔：") + s.filename if s else tr("尚未選取資料"))
        self.original_filename.setToolTip(s.filename if s else "")
        self.notes.setPlainText(s.notes if s else "")
        self.peak_list.clear()
        for i, model in enumerate(config.peaks, 1):
            self.peak_list.addTopLevelItem(QTreeWidgetItem([f"Peak {i}", model]))
        self.param_table.setRowCount(0)
        if s:
            try:
                _, params, _, _ = build_model(s, config)
                editable = parameter_config(params)
                self.param_table.setRowCount(len(editable))
                for row, (name, p) in enumerate(editable.items()):
                    values = [name, repr(float(p['value'])),
                              "" if not np.isfinite(p["min"]) else repr(float(p['min'])),
                              "" if not np.isfinite(p["max"]) else repr(float(p['max'])),
                              "", p["expr"], ""]
                    for col, value in enumerate(values):
                        item = QTableWidgetItem(value)
                        if col == 0:
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        if col in (4, 6):
                            item.setFlags((item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable)
                            checked = (not p["vary"] and not p["expr"]) if col == 4 else name in config.shared
                            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                        self.param_table.setItem(row, col, item)
            except Exception as exc:
                self.statusBar().showMessage(str(exc))
        self.loading = False

    def rename_current(self):
        if self.current and not self.loading:
            self._rename_spectrum(self.current, self.name_edit.text())

    def _rename_spectrum(self, spectrum, text):
        name = text.strip()
        if not name:
            name = spectrum.name
            self.statusBar().showMessage(tr("名稱不可留白；已保留原名稱。"))
        changed = name != spectrum.name
        spectrum.name = name
        # Keep the active editor, selection and pending fit-parameter edits.
        blocker = QSignalBlocker(self.tree)
        for row in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(row)
            if item.data(0, Qt.ItemDataRole.UserRole) == spectrum.id:
                item.setText(1, name)
                break
        del blocker
        if spectrum.id == self.current_id:
            self.name_edit.setText(name)
        for index in range(self.style_spectrum.count()):
            if self.style_spectrum.itemData(index) == spectrum.id:
                self.style_spectrum.setItemText(index, name)
                break
        if changed:
            self.mark_dirty()
            self.trend_panel.set_spectra(self.spectra)
            self._refresh_tables()
            self._filter()
            self._draw()

    def _domain_changed(self):
        if self.loading or not self.current:
            return
        config = self.current.config
        config.domain = self.domain.currentText()
        config.xmin = config.xmax = None
        config.excluded, config.parameters = [], {}
        if config.domain == "nm":
            config.jacobian = False
        self.preview = None
        self.mark_dirty()
        self._load_controls()
        self._draw()

    def _coordinate_changed(self):
        if self.loading or not self.current:
            return
        self.current.config.normalization = self.normalization.currentText()
        self.current.config.jacobian = self.jacobian.isChecked()
        self.current.config.parameters = {}
        self.preview = None
        self.mark_dirty()
        self._load_controls()
        self._draw()

    def _background_changed(self):
        if self.loading or not self.current:
            return
        try:
            self._commit()
            self.current.config.parameters = {k: v for k, v in self.current.config.parameters.items() if not k.startswith("b_")}
            self._load_controls()
            self.mark_dirty()
        except Exception as exc:
            self._error(exc)

    def apply_range(self):
        try:
            self._commit()
            self.preview = None
            self._draw()
        except Exception as exc:
            self._error(exc)

    def full_range(self):
        self.xmin.clear()
        self.xmax.clear()
        self.mask_edit.clear()
        self.apply_range()

    def _span_selected(self, lo, hi):
        if not self.current or self.worker or self.mode.currentIndex() != 0:
            return
        self.xmin.setText(f"{lo:.10g}")
        self.xmax.setText(f"{hi:.10g}")
        self.apply_range()

    def add_peak(self, center=None):
        if not self.current:
            return
        try:
            self._commit()
            config = self.current.config
            if len(config.peaks) >= 12:
                raise ValueError(tr("最多支援 12 個分峰。"))
            config.peaks.append(self.model_choice.currentText())
            _, params, _, _ = build_model(self.current, config)
            new_name = f"p{len(config.peaks)}_center"
            if center is not None:
                params[new_name].value = center
            config.parameters = parameter_config(params)
            self.mark_dirty()
            self._load_controls()
        except Exception as exc:
            self._error(exc)

    def delete_peak(self):
        if not self.current:
            return
        try:
            self._commit()
            config = self.current.config
            item = self.peak_list.currentItem()
            i = self.peak_list.indexOfTopLevelItem(item) if item else len(config.peaks)-1
            if len(config.peaks) <= 1:
                raise ValueError(tr("至少保留一個分峰。"))
            del config.peaks[i]
            # Expressions reference numbered peaks, so reinitialize after removal.
            config.parameters, config.shared = {}, []
            self.mark_dirty()
            self._load_controls()
        except Exception as exc:
            self._error(exc)

    def replace_peak(self):
        if not self.current:
            return
        try:
            self._commit()
            item = self.peak_list.currentItem()
            index = self.peak_list.indexOfTopLevelItem(item) if item else 0
            self.current.config.peaks[index] = self.model_choice.currentText()
            self.current.config.parameters, self.current.config.shared = {}, []
            self.preview = None
            self.mark_dirty()
            self._load_controls()
            self.statusBar().showMessage(tr("峰形已替換，初始值與參數關係已重設；既有結果保留於下方。"))
        except Exception as exc:
            self._error(exc)

    def arm_add_peak(self):
        if self.current:
            self.add_on_click = True
            self.statusBar().showMessage(tr("在主圖上點選新分峰中心。"))

    def _canvas_click(self, event):
        if (self.add_on_click and self.mode.currentIndex() == 0 and event.inaxes == self.axes
                and event.xdata is not None and not self.worker):
            self.add_on_click = False
            self.add_peak(float(event.xdata))

    def auto_peaks(self):
        if not self.current:
            return
        try:
            self._commit()
            config = self.current.config
            centers = peak_candidates(self.current, config, self.prominence.value())
            config.peaks = [self.model_choice.currentText()]*len(centers)
            config.parameters, config.shared = {}, []
            _, params, _, _ = build_model(self.current, config)
            for i, center in enumerate(centers, 1):
                params[f"p{i}_center"].value = center
            config.parameters = parameter_config(params)
            self.mark_dirty()
            self._load_controls()
            self.preview_model()
            self.statusBar().showMessage(tr('找到 {1} 個候選峰；請檢查是否合理。找峰平滑未套用到擬合資料。').format('', len(centers), ''))
        except Exception as exc:
            self._error(exc)

    def reset_parameters(self):
        if self.current:
            self.current.config.parameters, self.current.config.shared = {}, []
            self.mark_dirty()
            self._load_controls()

    def preview_model(self):
        if not self.current:
            return
        try:
            self._commit()
            model, params, x, _ = build_model(self.current, self.current.config)
            self.preview = (x, model.eval(params, x=x))
            self._draw()
        except Exception as exc:
            self._error(exc)

    def apply_to_selected(self):
        if not self.current:
            return
        try:
            self._commit()
            spectra = self._selected()
            for spectrum in spectra:
                build_model(spectrum, self.current.config)
            for spectrum in spectra:
                spectrum.config = copy.deepcopy(self.current.config)
            self.mark_dirty()
            self.statusBar().showMessage(tr('已套用設定至 {1} 條資料；既有結果仍保存原擬合設定。').format('', len(spectra), ''))
        except Exception as exc:
            self._error(exc)

    def start_fit(self, mode):
        if self.worker or not self.current:
            return
        try:
            self._commit()
            spectra = [self.current] if mode == "single" else self._selected()
            if not spectra:
                raise ValueError(tr("請先選取光譜。"))
            if mode == "joint":
                if len(spectra) < 2:
                    raise ValueError(tr("聯合擬合至少選取兩條光譜。"))
                if not self.current.config.shared:
                    raise ValueError(tr("請在參數表的「共用」欄勾選至少一個參數。"))
                configs = [copy.deepcopy(self.current.config) for _ in spectra]
            else:
                configs = [copy.deepcopy(s.config) for s in spectra]
            for spectrum, config in zip(spectra, configs):
                build_model(spectrum, config)
            self.last_errors = []
            self.preview = None
            self.worker = FitWorker(spectra, configs, mode == "joint")
            self.worker.completed.connect(self._fit_received)
            self.worker.progress.connect(self.statusBar().showMessage)
            self.worker.failed.connect(self.last_errors.append)
            self.worker.finished.connect(self._fit_finished)
            self.right.setEnabled(False)
            self.left.setEnabled(False)
            self.toolbar.setEnabled(False)
            self.mode.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.worker.start()
        except Exception as exc:
            self._error(exc)

    def _fit_received(self, identity, result):
        spectrum = next(s for s in self.spectra if s.id == identity)
        if spectrum.result:
            spectrum.history.append(spectrum.result)
        spectrum.result = result
        spectrum.config = FitConfig(**result["config"])
        self.mark_dirty()
        self._refresh_tree()
        self._refresh_tables()
        self._draw()

    def _fit_finished(self):
        cancelled = self.worker.cancel.is_set()
        self.worker.deleteLater()
        self.worker = None
        self.right.setEnabled(True)
        self.left.setEnabled(True)
        self.toolbar.setEnabled(True)
        self.mode.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._load_controls()
        if self.last_errors:
            self._error(tr("部分擬合未完成：\n")+"\n".join(self.last_errors))
        else:
            self.statusBar().showMessage(tr("擬合已取消。") if cancelled else tr("擬合完成；請檢查殘差、參數誤差與警示。"))

    def cancel_fit(self):
        if self.worker:
            self.worker.cancel.set()
            self.statusBar().showMessage(tr("正在取消擬合…"))

    def _refresh_tables(self):
        rows = []
        for s in self.spectra:
            r = s.result
            if r:
                p = r["peaks"][0]
                m = r["metrics"]
                rows.append([s.name, s.filename, tr("完成") if r["success"] else tr("未收斂"),
                             "+".join(r["config"]["peaks"]), r["config"]["domain"],
                             p["maximum_position"], p["fwhm"], p["area_in_range"], m["rmse"],
                             m["r2"], m["aic"], m["bic"], "; ".join(saved_message(w) for w in r["warnings"]), s.id,
                             s.condition.strip() or s.name, p["height"]])
            else:
                rows.append([s.name, s.filename, tr("未擬合"), "", "", None, None, None, None, None, None, None, "", s.id,
                             s.condition.strip() or s.name, None])
        self.summary.fill([tr("顯示名稱"), tr("原始檔名"), tr("狀態"), tr("模型"), tr("X 單位"), tr("Peak 1 峰頂位置"), "Peak 1 FWHM",
                           tr("Peak 1 區間面積"), "RMSE", "R²", "AIC", "BIC", tr("警示"), "ID", "Condition",
                           tr("Peak 1 intensity（扣背景）")], rows)
        self.summary.setColumnHidden(13, True)
        s = self.current
        result = s.result if s else None
        peaks = result["peaks"] if result else []
        self.peak_table.fill([tr("分峰"), tr("模型"), tr("中心參數"), tr("中心標準誤"), tr("峰頂位置"), tr("Peak intensity（扣背景峰高）"), "FWHM", tr("模型總面積"), tr("區間面積"), tr("面積比例")],
            [[p[k] for k in ("peak", "model", "center", "center_stderr", "maximum_position", "height", "fwhm", "amplitude", "area_in_range", "area_fraction")] for p in peaks])
        parameters = result["parameters"] if result else []
        self.detail_table.fill([tr("參數"), tr("結果值"), tr("標準誤"), tr("下限"), tr("上限"), tr("固定"), tr("關係式"), tr("接近界限")],
            [[p[k] for k in ("parameter", "value", "stderr", "min", "max", "fixed", "expr", "at_bound")] for p in parameters])
        meta = list(s.metadata) if s else []
        if s:
            meta = [["Original filename", s.filename], ["SHA256", s.digest],
                    ["Acquired points", len(s.x)], ["Wavelength range (nm)", f"{s.x.min():.5f} – {s.x.max():.5f}"],
                    ["User notes", s.notes], *meta]
        if result:
            meta += [["Fit coordinate", result["config"]["domain"]],
                     ["Fit normalization", result["config"]["normalization"]],
                     ["Fit timestamp UTC", result["timestamp"]],
                     ["Error assumption", result["error_assumption"]],
                     ["Measured area (background subtracted)", result["metrics"]["measured_area_background_subtracted"]],
                     ["Centroid (positive signal after background)", result["metrics"]["centroid_positive_background_subtracted"]]]
            if result["joint"]:
                meta += [["Joint "+k, v] for k, v in result["joint"]["metrics"].items()]
        self.metadata_table.fill([tr("欄位"), tr("內容")], meta)
        records = ([result] if result else []) + (list(reversed(s.history)) if s else [])
        self.history_table.fill([tr("版本"), tr("時間 UTC"), tr("模型"), "RMSE", tr("成功"), "ID"],
            [[tr("目前") if i == 0 and result else tr("歷史"), r["timestamp"], "+".join(r["config"]["peaks"]),
              r["metrics"]["rmse"], r["success"], r["id"]] for i, r in enumerate(records)])
        self.history_table.setColumnHidden(5, True)

    def _summary_clicked(self, row, column):
        identity = self.summary.item(row, 13).text()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == identity:
                self.tree.setCurrentItem(item)
                break

    def _restore_history(self, row, column):
        if self.worker or not self.current:
            return
        identity = self.history_table.item(row, 5).text()
        s = self.current
        record = next((r for r in s.history if r["id"] == identity), None)
        if record:
            s.history.remove(record)
            if s.result:
                s.history.append(s.result)
            s.result = record
            s.config = FitConfig(**record["config"])
            self.mark_dirty()
            self._load_controls()
            self._refresh_tables()
            self._refresh_tree()
            self._draw()

    def _mode_changed(self, index):
        if not hasattr(self, "right"):
            return
        try:
            self._commit()
        except Exception as exc:
            self._error(exc)
        self.right.setCurrentIndex(index)
        if index == TRENDS:
            self.tables.setCurrentWidget(self.trend_table)
        elif self.tables.currentWidget() == self.trend_table:
            self.tables.setCurrentWidget(self.summary)
        self._draw()

    def _trend_changed(self):
        if self.loading:
            return
        self.plot_settings["trends"] = self.trend_panel.settings()
        self.mark_dirty()
        if self.mode.currentIndex() == TRENDS:
            self._draw()

    def _conditions_changed(self):
        self.mark_dirty()
        self.loading = True
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            spectrum = next(s for s in self.spectra if s.id == item.data(0, Qt.ItemDataRole.UserRole))
            spectrum.trend_include = spectrum.plot
            item.setCheckState(0, Qt.CheckState.Checked if spectrum.plot else Qt.CheckState.Unchecked)
        self.loading = False
        self._refresh_tables()
        if self.mode.currentIndex() in (TRENDS, OVERLAY):
            self._draw()

    def _draw_trends(self):
        settings = self.trend_panel.settings()
        axes, prepared = draw_trends(self.figure, self.spectra, settings, settings.get("font", self.ui_font))
        self.axes, self.residual_axes = axes[0], None
        valid_ids = {r["spectrum_id"] for r in prepared["rows"] if r["valid"]}
        text = (tr('Condition vs 擬合結果 | 納入 {1} / {3} 條光譜 | 每條光譜一個點；結果依保存的擬合版本。').format('', len(valid_ids), '', prepared['spectrum_count'], ''))
        if prepared["messages"]:
            text += "\n"+"；".join(prepared["messages"][:2])
            if len(prepared["messages"]) > 2:
                text += tr('；另 {1} 則提示，請查看下方狀態欄。').format('', len(prepared['messages'])-2, '')
        self.chart_info.setText(text)
        self.chart_info.setToolTip("\n".join(prepared["messages"]))
        self.trend_table.fill(["Condition", tr("資料"), tr("指標"), "Peak", tr("數值"), tr("標準誤"), tr("單位"), tr("狀態"), tr("原始檔名")],
                              [[r[k] for k in ("condition", "name", "metric_label", "peak", "value", "stderr",
                                               "unit", "status", "filename")] for r in prepared["rows"]])
        self.canvas.draw_idle()

    def export_trend_image(self):
        try:
            settings = self.trend_panel.settings()
            path, _ = QFileDialog.getSaveFileName(self, tr("匯出目前參數趨勢圖"), "PL_condition_trends.png",
                "PNG (*.png);;JPEG (*.jpg);;PDF (*.pdf);;SVG (*.svg)")
            if path:
                export_trends(path, self.spectra, settings, settings.get("font", self.ui_font))
                self.statusBar().showMessage(tr('趨勢圖已匯出：{1}').format('', path))
        except Exception as exc:
            self._error(exc)

    def export_all_trend_images(self):
        try:
            directory = QFileDialog.getExistingDirectory(self, tr("選擇多張趨勢圖輸出資料夾"))
            if directory:
                paths, skipped = export_trend_set(directory, self.spectra, self.trend_panel.settings(),
                                                   self.trend_panel.format.currentText(), self.trend_panel.settings().get("font", self.ui_font))
                text = tr('已分別匯出 {1} 張趨勢圖。').format('', len(paths), '')
                if skipped:
                    text += tr(" 無有效數值，已略過：")+", ".join(skipped)
                self.statusBar().showMessage(text)
        except Exception as exc:
            self._error(exc)

    def export_trend_data(self):
        try:
            path, _ = QFileDialog.getSaveFileName(self, tr("匯出勾選指標的趨勢數值"), "PL_trend_data.xlsx", "Excel (*.xlsx)")
            if path:
                export_trend_excel(path, self.spectra, self.trend_panel.settings())
                self.statusBar().showMessage(tr('趨勢數值與狀態已匯出：{1}').format('', path))
        except Exception as exc:
            self._error(exc)

    def _draw(self):
        if not hasattr(self, "canvas"):
            return
        self.trend_panel.refresh_position_choices()
        if self.template_dialog.isVisible():
            self.template_dialog.preview()
        try:
            if hasattr(self, "span"):
                self.span.disconnect_events()
            self.figure.set_layout_engine(None)
            if self.mode.currentIndex() == TRENDS:
                self._draw_trends()
                return
            if self.mode.currentIndex() == OVERLAY:
                settings = self._read_overlay_inputs()
                self.axes, self.residual_axes = draw_overlay(self.figure, self.spectra, settings)
                count = sum(s.plot for s in self.spectra)
                label = {"raw": tr("原始 Intensity（Counts）"), "normalized": "Normalized intensity（I / Imax）",
                         "both": tr("原始 Intensity + Normalized intensity")}[settings["intensity"]]
                self.chart_info.setText(tr('已選 {1} 條 PL 光譜 | X：波長 nm | Y：{3} | 左側勾選同步控制所有比較圖。').format('', count, '', label, ''))
                self.canvas.draw_idle()
                return
            analysis = self.mode.currentIndex() == 0
            if analysis and self.current:
                result = self.current.result
                self.chart_info.setText(
                    tr('{0}  |  工作座標：{2}  |  ').format(self.current.name, '', self.current.config.domain, '') +
                    (tr('顯示上次擬合結果（{1}）；修改設定後請重新擬合。').format('', result['config']['domain'], '')
                     if result else tr("尚未擬合；Shift 拖曳選區。")))
            else:
                self.chart_info.setText(tr("論文圖預覽：使用左側勾選資料；擬合線依各結果保存的座標與處理設定顯示。"))
            spectra = ([self.current] if self.current else []) if analysis else [s for s in self.spectra if s.plot]
            style = copy.deepcopy(self.plot_settings)
            if analysis:
                style.update(raw=True, fit=True, residual=True, normalize=False, offset=0,
                             title="", xlabel="", ylabel="", xmin=None, xmax=None, ymin=None, ymax=None,
                             logy=False, components=True, background=True, font="Arial", font_size=10)
                # Show the CURRENT working coordinates, while keeping fitted results immutable.
                if self.current:
                    spectrum = copy.copy(self.current)
                    if spectrum.result:
                        old = FitConfig(**spectrum.result["config"])
                        if (old.domain, old.jacobian, old.normalization) != (
                                spectrum.config.domain, spectrum.config.jacobian, spectrum.config.normalization):
                            spectrum.result = None
                    spectra = [spectrum]
            self.axes, self.residual_axes = draw_spectra(self.figure, spectra, style, analysis, self.preview)
            if analysis and self.current:
                cfg = self.current.config
                if cfg.xmin is not None:
                    self.axes.axvline(cfg.xmin, color="#d29b25", ls=":", lw=1)
                if cfg.xmax is not None:
                    self.axes.axvline(cfg.xmax, color="#d29b25", ls=":", lw=1)
                for lo, hi in cfg.excluded:
                    self.axes.axvspan(lo, hi, color="#e9a48e", alpha=0.18)
                self.span = SpanSelector(self.axes, self._span_selected, "horizontal", useblit=True,
                                         props={"alpha": 0.15, "facecolor": "#1868b2"},
                                         button=1, state_modifier_keys={"clear": "escape", "move": " ",
                                                                      "square": "shift", "center": "control"})
                # Activate only during Shift: ordinary left drag stays available for navigation.
                self.span.set_active(False)
                if not hasattr(self, "_key_connected"):
                    self.canvas.mpl_connect("key_press_event", self._plot_key_press)
                    self.canvas.mpl_connect("key_release_event", self._plot_key_release)
                    self._key_connected = True
            self.canvas.draw_idle()
        except Exception as exc:
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            is_trend = self.mode.currentIndex() == TRENDS
            if is_trend:
                self.chart_info.setText(tr("趨勢圖設定需調整：")+str(exc))
                self.trend_table.fill([tr("狀態")], [[str(exc)]])
            ax.text(.5, .5, ("Parameter trend unavailable: check Condition and metric settings" if is_trend
                             else "Plot unavailable: check coordinate and normalization settings"),
                    ha="center", va="center", transform=ax.transAxes, wrap=True)
            self.canvas.draw_idle()
            self.statusBar().showMessage(str(exc))

    def _plot_key_press(self, event):
        if event.key == "shift" and hasattr(self, "span") and self.mode.currentIndex() == 0:
            self.span.set_active(True)

    def _plot_key_release(self, event):
        if event.key == "shift" and hasattr(self, "span"):
            self.span.set_active(False)

    def _read_plot_inputs(self):
        style = copy.deepcopy(self.plot_settings)
        numeric = {"width_cm", "height_cm", "dpi", "font_size", "line_width", "offset"}
        limits = {"xmin", "xmax", "ymin", "ymax"}
        for key, widget in self.plot_inputs.items():
            if isinstance(widget, QCheckBox):
                style[key] = widget.isChecked()
            elif key in numeric:
                style[key] = float(widget.text())
                if not np.isfinite(style[key]) or (key != "offset" and style[key] <= 0):
                    raise ValueError(tr('{0} 的數值無效。').format(key, ''))
            elif key in limits:
                style[key] = optional_float(widget.text())
                if style[key] is not None and not np.isfinite(style[key]):
                    raise ValueError(tr("座標範圍必須是有限值。"))
            else:
                style[key] = widget.text()
        for lo, hi in (("xmin", "xmax"), ("ymin", "ymax")):
            if style[lo] is not None and style[hi] is not None and style[lo] >= style[hi]:
                raise ValueError(tr("作圖範圍下限必須小於上限。"))
        if hasattr(self, "trend_panel"):
            style["trends"] = self.trend_panel.settings()
        if hasattr(self, "overlay_widgets"):
            style["overlay"] = self._read_overlay_inputs()
        return style

    def _paper_changed(self):
        if self.loading:
            return
        try:
            self.plot_settings = self._read_plot_inputs()
            self.mark_dirty()
            if self.mode.currentIndex() == ANALYSIS:
                self._draw()
        except Exception as exc:
            self.statusBar().showMessage(str(exc))

    def _load_plot_inputs(self):
        self.loading = True
        for key, widget in self.plot_inputs.items():
            value = self.plot_settings[key]
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            else:
                widget.setText("" if value is None else str(value))
        self.loading = False
        self.trend_panel.load_settings(self.plot_settings.get("trends", DEFAULT_TRENDS))
        self._load_overlay_inputs()

    def choose_color(self):
        identity = self.style_spectrum.currentData()
        if identity:
            color = QColorDialog.getColor(QColor("#1868b2"), self, tr("選擇線條顏色"))
            if color.isValid():
                self.plot_settings["styles"].setdefault(identity, {})["color"] = color.name()
                self.mark_dirty()
                self._draw()

    def apply_linestyle(self):
        identity = self.style_spectrum.currentData()
        if identity:
            self.plot_settings["styles"].setdefault(identity, {})["linestyle"] = self.linestyle.currentText()
            self.mark_dirty()
            self._draw()

    def save_template(self):
        try:
            self.plot_settings = self._read_plot_inputs()
            path, _ = QFileDialog.getSaveFileName(self, tr("儲存作圖模板"), "PL_style.json", "JSON (*.json)")
            if path:
                template = {k: v for k, v in self.plot_settings.items() if k not in ("styles", "trends", "overlay")}
                write_json(path, {"type": "PLStudioPlotStyle", "version": 1, "settings": template})
        except Exception as exc:
            self._error(exc)

    def load_template(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("載入作圖模板"), "", "JSON (*.json)")
        if path:
            try:
                content = json.loads(Path(path).read_text(encoding="utf-8"))
                if content.get("type") != "PLStudioPlotStyle":
                    raise ValueError(tr("不是 PL Studio 作圖模板。"))
                self.plot_settings.update({k: v for k, v in content["settings"].items() if k in DEFAULT_STYLE and k != "styles"})
                self._load_plot_inputs()
                self.plot_settings = self._read_plot_inputs()
                self.mark_dirty()
                self._draw()
            except Exception as exc:
                self._error(exc)

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr("匯入原始資料"), "",
                                               tr("光譜資料 (*.txt *.csv *.dat *.tsv *.zip);;全部檔案 (*)"))
        self.import_paths(paths)

    def import_paths(self, paths):
        if self.worker:
            return
        errors, added = [], []
        for path in paths:
            try:
                spectra, problems = import_path(path)
                added.extend(spectra)
                errors.extend(problems)
            except Exception as exc:
                errors.append(f"{Path(path).name}：{exc}")
        duplicates = []
        existing = {s.digest: s.filename for s in self.spectra}
        for s in added:
            if s.digest in existing:
                duplicates.append(tr('{0} 與 {2} 完全相同').format(s.filename, '', existing[s.digest], ''))
            existing[s.digest] = s.filename
        self.spectra.extend(added)
        if added:
            if self.current_id is None:
                self.current_id = added[0].id
            self.mark_dirty()
            self._refresh_tree()
            self._load_controls()
            self._refresh_tables()
            self._draw()
        self.statusBar().showMessage(tr('已匯入 {1} 條光譜；{3} 個重複內容提示。').format('', len(added), '', len(duplicates), ''))
        if duplicates or errors:
            QMessageBox.information(self, tr("匯入檢查"), "\n".join([
                *([tr("重複資料已保留並標示："), *duplicates] if duplicates else []),
                *([tr("未匯入："), *errors] if errors else [])]))

    def remove_selected(self):
        selected = self._selected()
        if not selected:
            return
        if QMessageBox.question(self, tr("移除資料"), tr('從專案移除 {1} 條資料？原始來源檔案不會被刪除。').format('', len(selected), '')) != QMessageBox.StandardButton.Yes:
            return
        ids = {s.id for s in selected}
        self.spectra = [s for s in self.spectra if s.id not in ids]
        if self.current_id in ids:
            self.current_id = self.spectra[0].id if self.spectra else None
        self.preview = None
        self.mark_dirty()
        self._refresh_tree()
        self._load_controls()
        self._refresh_tables()
        self._draw()

    def _maybe_save(self):
        try:
            self._commit()
            style = self._read_plot_inputs()
            if style != self.plot_settings:
                self.plot_settings = style
                self.mark_dirty()
        except Exception as exc:
            self._error(exc)
            return False
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, tr("尚未儲存"), tr("是否儲存目前專案？"),
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def new_project(self):
        if self.worker or not self._maybe_save():
            return
        self.spectra, self.current_id, self.project_path = [], None, None
        self.plot_settings = copy.deepcopy(DEFAULT_STYLE)
        self.preview = None
        self.dirty = False
        self._refresh_tree()
        self._load_controls()
        self._load_plot_inputs()
        self._refresh_tables()
        self._update_title()
        self._draw()

    def open_project(self):
        if self.worker or not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("開啟專案或復原檔"), "", tr("PL 專案 (*.plproj *.recovery)"))
        if path:
            self.load_project_path(path)

    def load_project_path(self, path):
        try:
            spectra, settings = load_project(path)
            self.spectra, self.plot_settings = spectra, copy.deepcopy(DEFAULT_STYLE) | settings
            self.current_id = spectra[0].id if spectra else None
            self.project_path = str(path) if not str(path).endswith(".recovery") else None
            self.preview, self.dirty = None, False
            self._refresh_tree()
            self._load_controls()
            self._load_plot_inputs()
            self._refresh_tables()
            self._update_title()
            self._draw()
        except Exception as exc:
            self._error(exc)

    def save(self, save_as=False):
        if self.worker:
            return False
        try:
            self._commit()
            self.plot_settings = self._read_plot_inputs()
            path = self.project_path
            if save_as or not path:
                path, _ = QFileDialog.getSaveFileName(self, tr("儲存完整專案"), path or "PL_project.plproj", tr("PL 專案 (*.plproj)"))
            if not path:
                return False
            if not path.lower().endswith(".plproj"):
                path += ".plproj"
            save_project(path, self.spectra, self.plot_settings)
            self.project_path, self.dirty = path, False
            self._update_title()
            self.statusBar().showMessage(tr("專案已儲存，包含原始資料、擬合紀錄與作圖設定。"))
            return True
        except Exception as exc:
            self._error(exc)
            return False

    def _autosave(self):
        if self.dirty and self.spectra and not self.worker:
            try:
                self._commit()
                recovery = (Path(self.project_path).with_suffix(".plproj.recovery") if self.project_path
                            else self._recovery_path())
                save_project(recovery, self.spectra, self._read_plot_inputs())
            except Exception as exc:
                self.statusBar().showMessage(tr('自動復原檔未儲存：{1}').format('', exc))

    @staticmethod
    def _recovery_path():
        from PySide6.QtCore import QStandardPaths
        folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "PL_unsaved.recovery"

    def _export_scope(self):
        if not self.spectra:
            raise ValueError(tr("請先匯入資料。"))
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("匯出資料範圍"))
        layout = QVBoxLayout(dialog)
        choice = QComboBox()
        choice.addItems([tr("全部資料"), tr("左側選取資料"), tr("作圖勾選資料"), tr("目前光譜")])
        layout.addWidget(choice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return []
        sets = [self.spectra, self._selected(), [s for s in self.spectra if s.plot],
                [self.current] if self.current else []]
        selected = sets[choice.currentIndex()]
        if not selected:
            raise ValueError(tr("選擇範圍內沒有資料。"))
        return selected

    def export_image(self):
        if self.mode.currentIndex() == TRENDS:
            self.export_trend_image()
            return
        if self.mode.currentIndex() == OVERLAY:
            self.export_overlay_image()
            return
        try:
            self._commit()
            style = self._read_plot_inputs()
            selected = [s for s in self.spectra if s.plot]
            if not selected:
                raise ValueError(tr("請先在左側勾選要作圖的資料。"))
            path, _ = QFileDialog.getSaveFileName(self, tr("匯出論文作圖"), "PL_figure.png",
                "PNG (*.png);;JPEG (*.jpg);;PDF (*.pdf);;SVG (*.svg)")
            if path:
                export_figure(path, selected, style)
                self.plot_settings = style
                self.mark_dirty()
                self.statusBar().showMessage(tr('圖形已匯出：{1}').format('', path))
        except Exception as exc:
            self._error(exc)

    def export_xlsx(self):
        try:
            self._commit()
            selected = self._export_scope()
            if not selected:
                return
            path, _ = QFileDialog.getSaveFileName(self, tr("匯出 Excel 結果"), "PL_results.xlsx", "Excel (*.xlsx)")
            if path:
                export_excel(path, selected)
                self.statusBar().showMessage(tr('Excel 已匯出：{1}').format('', path))
        except Exception as exc:
            self._error(exc)

    def export_origin(self):
        try:
            self._commit()
            selected = self._export_scope()
            if not selected:
                return
            path, _ = QFileDialog.getSaveFileName(self, tr("匯出 Origin 資料包"), "PL_Origin.zip", "ZIP (*.zip)")
            if path:
                export_origin_bundle(path, selected)
                self.statusBar().showMessage(tr("Origin 資料包已匯出：CSV、結果與 .opju 腳本；Figure Template 樣式目前未轉換。"))
        except Exception as exc:
            self._error(exc)

    def export_origin_project(self):
        try:
            self._commit()
            selected = self._export_scope()
            if not selected:
                return
            path, _ = QFileDialog.getSaveFileName(self, tr("匯出 Origin 專案（需 Origin）"), "PL_results.opju", "Origin (*.opju)")
            if path:
                export_opju(path, selected)
                self.statusBar().showMessage(tr('Origin 資料與基本曲線已匯出：{1}；Figure Template 樣式尚未轉換。').format('', path, ''))
        except Exception as exc:
            self._error(exc)

    def help(self):
        QMessageBox.information(self, tr("PL Studio 使用說明"), "\n".join([
            tr("1. 匯入雙欄 TXT / CSV / ZIP；檔尾儀器資訊會保留。"),
            tr("2. 選擇光譜，設定座標、範圍、峰形、初始值與約束。"),
            tr("3. Shift + 滑鼠拖曳選區；「點圖加峰」後點選峰位。"),
            tr("4. 批次使用各光譜設定；可先「套用目前設定至選取光譜」。"),
            tr("5. 聯合擬合使用目前設定，將「共用」欄參數綁定。"),
            tr("6. 在結果表使用 Ctrl+C 複製；雙擊歷史紀錄可還原。"),
            tr("7. 左側勾選同步控制論文作圖、參數趨勢圖與 PL 疊圖，右側勾選也會同步。"),
            tr("PL 疊圖：X 固定波長 nm；Y 可選原始 Counts 或各線 I/Imax，使用原始資料。"),
            tr("8. Excel / Origin 可另選匯出範圍。"),
            tr("參數趨勢圖：填入每條光譜的 Condition，勾選資料及峰位／FWHM／面積等指標。"),
            tr("Condition 可用類別名稱或數值；不做平均，同 Condition 的多條光譜仍各為一點。"),
            tr("趨勢圖可總覽、切換單圖、分別匯出圖片及匯出數值 Excel；設定隨專案保存。"),
            tr("9. 專案包含原始資料；每分鐘建立 *.recovery 復原檔。"),
            "",
            tr("目前為未加權最小平方法；標準誤採局部協方差估計。"),
            tr("Counts 不代表光子數；Jacobian 僅適用於每 nm 光譜密度。"),
            tr("單條未校正 PL 不會輸出壽命、缺陷密度、PLQY 或 QFLS。"),
            tr("峰形分解結果使用 Peak 編號，物理歸屬需另有量測依據。"),
            tr("Origin .opju 需相容的 originpro 與已授權 Origin；CSV 資料包可獨立匯出。"),
        ]))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.worker:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.worker:
            self.import_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.worker:
            self.cancel_fit()
            self.statusBar().showMessage(tr("已要求取消，擬合停止後即可關閉視窗。"))
            event.ignore()
            return
        if self._maybe_save():
            self.shutting_down = True
            self.update_timer.stop()
            self.update_checker.cancel()
            event.accept()
        else:
            event.ignore()


def launch():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("PL Studio")
    app.setOrganizationName("PLStudio")
    initialize_language()
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        paths = sys.argv[1:]
        if len(paths) == 1 and Path(paths[0]).suffix.lower() in (".plproj", ".recovery"):
            QTimer.singleShot(100, lambda: window.load_project_path(paths[0]))
        else:
            QTimer.singleShot(100, lambda: window.import_paths(paths))
    return app.exec()
