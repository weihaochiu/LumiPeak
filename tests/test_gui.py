import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
import pytest

from plstudio.data import FitConfig, save_project
from plstudio.fitting import fit_spectrum
from plstudio.plotting import DEFAULT_STYLE
from plstudio.gui import MainWindow, TRENDS, OVERLAY
from tests.test_core import synthetic


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: pytest.fail(str(a[-1])))
    w = MainWindow()
    w.show()
    app.processEvents()
    yield w
    assert w.worker is None
    w.dirty = False
    w._maybe_save = lambda: True
    w.close()
    app.processEvents()


def populate(w):
    w.spectra = [synthetic(), synthetic(amplitude=15000)]
    w.spectra[1].name = "Second"
    w.current_id = w.spectra[0].id
    w._refresh_tree()
    w._load_controls()
    w._refresh_tables()
    w._draw()


def wait_worker(w, app):
    deadline = time.monotonic()+30
    while w.worker and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert w.worker is None
    assert not w.last_errors


def test_ui_edit_peaks_selection_batch_and_paper(window, app, tmp_path):
    w = window
    populate(w)
    # Clicking a QPushButton must not pass its checked=False as a numeric peak center.
    button = next(b for b in w.findChildren(QPushButton) if b.text() == "新增峰")
    button.click()
    assert len(w.current.config.peaks) == 2
    assert w.current.config.parameters["p2_center"]["value"] > 700
    w.delete_peak()
    assert len(w.current.config.peaks) == 1
    w.model_choice.setCurrentText("Voigt")
    w.replace_peak()
    assert w.current.config.peaks == ["Voigt"]
    w.model_choice.setCurrentText("Gaussian")
    w.replace_peak()
    second_id = w.spectra[1].id
    w.tree.setCurrentItem(w.tree.topLevelItem(1))
    app.processEvents()
    assert w.current_id == second_id
    w.tree.selectAll()
    w.start_fit("batch")
    assert w.worker is not None
    wait_worker(w, app)
    assert all(s.result and s.result["success"] for s in w.spectra)
    assert w.summary.rowCount() == 2
    assert w.peak_table.rowCount() == 1
    w.open_figure_template()
    app.processEvents()
    assert w.template_dialog.isVisible()
    assert w.mode.count() == 3
    w.template_dialog.close()
    assert w.residual_axes is not None
    w.grab().save(str(tmp_path/"ui.png"))


def test_ui_joint_fit(window, app):
    w = window
    populate(w)
    row = next(i for i in range(w.param_table.rowCount()) if w.param_table.item(i, 0).text() == "p1_center")
    w.param_table.item(row, 6).setCheckState(Qt.CheckState.Checked)
    w.tree.selectAll()
    w.start_fit("joint")
    wait_worker(w, app)
    assert w.spectra[0].result["joint"] is not None
    assert w.spectra[0].result["peaks"][0]["center"] == w.spectra[1].result["peaks"][0]["center"]


def test_ui_project_reload_and_coordinate_change(window, app, tmp_path):
    s = synthetic()
    s.result = fit_spectrum(s)
    s.config = FitConfig(**s.result["config"])
    path = tmp_path/"saved.plproj"
    save_project(path, [s], DEFAULT_STYLE)
    window.load_project_path(path)
    assert len(window.spectra) == 1
    assert window.summary.rowCount() == 1
    assert window.current.result["id"] == s.result["id"]
    window.domain.setCurrentText("eV")
    assert window.current.config.domain == "eV"
    assert window.current.result["config"]["domain"] == "nm"
    assert window.current.config.xmin is None
    window.preview_model()
    assert window.preview is not None
    assert max(window.preview[0]) < 2


def test_ui_condition_trends_edit_select_and_restore(window, app, tmp_path):
    populate(window)
    for s in window.spectra:
        s.result = fit_spectrum(s)
    window._refresh_tree()
    window.mode.setCurrentIndex(TRENDS)
    app.processEvents()
    assert window.right.currentIndex() == TRENDS
    assert window.tables.currentWidget() == window.trend_table
    assert window.trend_table.rowCount() == 8
    panel = window.trend_panel
    panel.condition_table.item(0, 2).setText("100")
    panel.condition_table.item(1, 2).setText("20")
    assert window.spectra[0].condition == "100"
    panel.xmode.setCurrentIndex(panel.xmode.findData("numeric"))
    app.processEvents()
    assert list(window.axes.lines[0].get_xdata()) == [20, 100]
    panel.view.setCurrentIndex(panel.view.findData("fwhm"))
    assert len(window.figure.axes) == 1
    assert window.trend_table.rowCount() == 2
    panel.condition_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    assert not window.spectra[1].trend_include
    assert not window.spectra[1].plot
    assert window.tree.topLevelItem(1).checkState(0) == Qt.CheckState.Unchecked
    assert window.trend_table.rowCount() == 1
    panel.xlabel.setText("Annealing temperature (C)")
    panel.xlabel.editingFinished.emit()
    path = tmp_path/"condition_ui.plproj"
    save_project(path, window.spectra, window._read_plot_inputs())
    window.load_project_path(path)
    assert window.trend_panel.xlabel.text() == "Annealing temperature (C)"
    assert window.trend_panel.view.currentData() == "fwhm"
    assert window.spectra[0].condition == "100"
    assert not window.spectra[1].trend_include
    window.mode.setCurrentIndex(0)
    assert window.right.currentIndex() == 0
    assert window.residual_axes is not None


def test_ui_invalid_condition_clears_previous_trend_table(window, app):
    populate(window)
    for s in window.spectra:
        s.result = fit_spectrum(s)
    window._refresh_tree()
    window.mode.setCurrentIndex(TRENDS)
    assert window.trend_table.rowCount() == 8
    window.trend_panel.xmode.setCurrentIndex(window.trend_panel.xmode.findData("numeric"))
    assert window.trend_table.columnCount() == 1
    assert "有限數字" in window.chart_info.text()


def test_left_uncheck_immediately_removes_c3_from_trend(window, app):
    populate(window)
    window.spectra[1].name = "C3"
    for s in window.spectra:
        s.result = fit_spectrum(s)
    window._refresh_tree()
    window.mode.setCurrentIndex(TRENDS)
    assert window.trend_table.rowCount() == 8
    window.tree.topLevelItem(1).setCheckState(0, Qt.CheckState.Unchecked)
    assert window.trend_table.rowCount() == 4
    assert window.trend_panel.condition_table.item(1, 0).checkState() == Qt.CheckState.Unchecked
    assert len(window.axes.lines[0].get_xdata()) == 1
    assert all(window.trend_table.item(i, 1).text() != "C3" for i in range(window.trend_table.rowCount()))
    # Changing the right-hand checkbox must update the shared left-hand checkbox.
    window.trend_panel.condition_table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert window.tree.topLevelItem(1).checkState(0) == Qt.CheckState.Checked
    assert window.trend_table.rowCount() == 8
    window._check_all(False)
    assert window.trend_table.rowCount() == 0
    window._check_all(True)
    assert window.trend_table.rowCount() == 8


def test_ui_wavelength_overlay_switch_and_project_restore(window, app, tmp_path):
    import numpy as np
    populate(window)
    window.spectra[1].name = "C3"
    window.spectra[0].config = FitConfig(domain="eV", normalization="max")
    window.spectra[0].result = fit_spectrum(window.spectra[0])
    window._load_controls()
    window._refresh_tree()
    window.mode.setCurrentIndex(OVERLAY)
    assert window.right.currentIndex() == OVERLAY
    assert window.overlay_intensity.currentData() == "both"
    assert len(window.figure.axes) == 2
    assert window.overlay_export.currentData() == "separate"
    assert len(window.axes.lines) == 2
    assert window.axes.get_xlabel() == "Wavelength (nm)"
    assert np.array_equal(window.axes.lines[0].get_ydata(), window.spectra[0].y)
    assert all(np.max(line.get_ydata()) == pytest.approx(1) for line in window.residual_axes.lines)
    window.overlay_export.setCurrentIndex(window.overlay_export.findData("raw"))
    assert window._read_overlay_inputs()["export_mode"] == "raw"
    assert len(window.figure.axes) == 2  # Export choice doesn't change the preview.
    window.overlay_intensity.setCurrentIndex(window.overlay_intensity.findData("normalized"))
    assert all(np.max(line.get_ydata()) == pytest.approx(1) for line in window.axes.lines)
    assert window.spectra[0].result["config"]["domain"] == "eV"
    window.tree.topLevelItem(1).setCheckState(0, Qt.CheckState.Unchecked)
    assert len(window.axes.lines) == 1
    assert "C3" not in window.axes.get_legend_handles_labels()[1]
    path = tmp_path/"overlay_ui.plproj"
    save_project(path, window.spectra, window._read_plot_inputs())
    window.load_project_path(path)
    assert window.overlay_intensity.currentData() == "normalized"
    assert window.overlay_export.currentData() == "raw"
    assert not window.spectra[1].plot and not window.spectra[1].trend_include
    assert len(window.axes.lines) == 1


@pytest.mark.skipif(not Path(r"D:\檔案交換資料夾\PL.zip").exists(), reason="Reference archive unavailable")
def test_real_data_ui(window, app):
    w = window
    w.import_paths([r"D:\檔案交換資料夾\PL.zip"])
    assert len(w.spectra) == 6
    w.tree.selectAll()
    w.start_fit("batch")
    wait_worker(w, app)
    assert all(s.result["success"] for s in w.spectra)
