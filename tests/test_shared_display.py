from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit, QStyleOptionViewItem

from plstudio.data import save_project
from plstudio.fitting import fit_spectrum
from plstudio.gui import OVERLAY, TRENDS
from tests.test_core import synthetic
from tests.test_gui import app, window, populate


def legends(window):
    return [[text.get_text() for text in axis.get_legend().get_texts()]
            for axis in window.figure.axes]


def test_inline_name_edit_updates_both_figures_without_losing_fit_edits(window, app):
    populate(window)
    for sample in window.spectra:
        sample.result = fit_spectrum(sample)
    window._refresh_tree()
    originals = [(s.id, s.filename, s.raw, s.result["id"]) for s in window.spectra]
    window.param_table.item(0, 1).setText("12345")
    item = window.tree.topLevelItem(0)
    window.tree.editItem(item, 1)
    app.processEvents()
    editor = window.tree.findChild(QLineEdit)
    assert editor is not None
    editor.setText("  Control A  ")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()
    assert window.spectra[0].name == "Control A"
    assert window.name_edit.text() == "Control A"
    assert window.param_table.item(0, 1).text() == "12345"
    assert window.trend_panel.condition_table.item(0, 1).text() == "Control A"
    # Restore this uncommitted fitting edit before switching work pages.
    window._load_controls()
    window.mode.setCurrentIndex(OVERLAY)
    assert legends(window) == [["Control A", "Second"], ["Control A", "Second"]]
    window.mode.setCurrentIndex(TRENDS)
    assert [t.get_text() for t in window.axes.get_xticklabels()] == ["Control A", "Second"]
    assert [(s.id, s.filename, s.raw, s.result["id"]) for s in window.spectra] == originals
    assert window.dirty


def test_shared_name_field_noncurrent_row_and_explicit_condition(window, app):
    populate(window)
    for sample in window.spectra:
        sample.result = fit_spectrum(sample)
    window.spectra[1].condition = "100"
    window._refresh_tree()
    window.tree.topLevelItem(1).setText(1, "Treatment B")
    assert window.spectra[1].name == "Treatment B"
    assert window.spectra[0].name != "Treatment B"
    assert window.spectra[1].condition == "100"
    window.name_edit.setText("Reference")
    window.name_edit.editingFinished.emit()
    assert window.tree.topLevelItem(0).text(1) == "Reference"
    window.mode.setCurrentIndex(OVERLAY)
    assert legends(window)[0] == ["Reference", "Treatment B"]
    window.mode.setCurrentIndex(TRENDS)
    assert [t.get_text() for t in window.axes.get_xticklabels()] == ["Reference", "100"]
    window.tree.topLevelItem(0).setText(1, "  ")
    assert window.tree.topLevelItem(0).text(1) == "Reference"
    assert window.spectra[0].name == "Reference"
    assert window.name_edit.text() == "Reference"
    delegate = window.tree.itemDelegate()
    for column in (0, 2):
        assert delegate.createEditor(window.tree, QStyleOptionViewItem(), window.tree.model().index(0, column)) is None


def test_left_selection_and_order_apply_to_both_figures_and_project(window, app, tmp_path):
    populate(window)
    third = synthetic(center=810)
    third.name = "Third"
    window.spectra.append(third)
    for sample in window.spectra:
        sample.result = fit_spectrum(sample)
    window.current_id = third.id
    window._refresh_tree()
    window._load_controls()
    window.mode.setCurrentIndex(OVERLAY)
    window.tree.topLevelItem(1).setCheckState(0, Qt.CheckState.Unchecked)
    window.move_current(-1)
    assert [s.name for s in window.spectra] == ["sample", "Third", "Second"]
    assert legends(window) == [["sample", "Third"], ["sample", "Third"]]
    window.tree.topLevelItem(2).setCheckState(0, Qt.CheckState.Checked)
    assert legends(window) == [["sample", "Third", "Second"], ["sample", "Third", "Second"]]
    window.mode.setCurrentIndex(TRENDS)
    assert [t.get_text() for t in window.axes.get_xticklabels()] == ["sample", "Third", "Second"]
    window.tree.topLevelItem(0).setCheckState(0, Qt.CheckState.Unchecked)
    assert [t.get_text() for t in window.axes.get_xticklabels()] == ["Third", "Second"]
    path = tmp_path / "shared_display.plproj"
    save_project(path, window.spectra, window._read_plot_inputs())
    window.load_project_path(path)
    assert [s.name for s in window.spectra] == ["sample", "Third", "Second"]
    assert not window.spectra[0].plot
    window.mode.setCurrentIndex(OVERLAY)
    assert legends(window) == [["Third", "Second"], ["Third", "Second"]]
    for sample, value in zip(window.spectra, ("30", "20", "10")):
        sample.condition = value
    window.trend_panel.xmode.setCurrentIndex(window.trend_panel.xmode.findData("numeric"))
    window.mode.setCurrentIndex(TRENDS)
    assert list(window.axes.lines[0].get_xdata()) == [10, 20]
