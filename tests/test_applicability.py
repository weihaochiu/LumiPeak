import copy

import pytest
from matplotlib.figure import Figure
from PySide6.QtCore import Qt

from plstudio.fitting import fit_spectrum
from plstudio.gui import TRENDS
from plstudio.trend_ui import TrendPanel
from plstudio.plotting import draw_spectra
from plstudio.trends import prepare_trends, export_trend_set
from tests.test_core import synthetic
from tests.test_gui import app, window, populate


@pytest.mark.parametrize("model,enabled", [
    ("Gaussian", False), ("Lorentzian", False), ("Voigt", False),
    ("PseudoVoigt", False), ("SkewedGaussian", True), ("SkewedVoigt", True),
])
def test_position_choices_for_each_model(app, model, enabled):
    sample = synthetic()
    sample.config.peaks = [model]
    panel = TrendPanel()
    panel.set_spectra([sample])
    panel.load_settings({"metrics": ["center", "maximum_position"], "view": "center"})
    assert panel.metric_checks["center"].isEnabled() == enabled
    assert panel.view.model().item(panel.view.findData("center")).isEnabled() == enabled
    assert not panel.metric_checks["area_fraction"].isEnabled()
    if enabled:
        assert panel.settings()["view"] == "center"
        assert "非對稱" in panel.metric_checks["center"].text()
    else:
        assert panel.settings()["view"] == "maximum_position"
        assert panel.settings()["metrics"] == ["maximum_position"]
    panel.close()


def test_saved_result_peak_selection_failed_fit_and_mixed_models(app):
    sample = synthetic()
    sample.result = fit_spectrum(sample)
    sample.config.peaks = ["SkewedGaussian", "SkewedVoigt"]
    panel = TrendPanel()
    panel.set_spectra([sample])
    # Editing a working configuration cannot change what a saved fit means.
    assert not panel.metric_checks["center"].isEnabled()
    assert not panel.metric_checks["area_fraction"].isEnabled()
    second = copy.deepcopy(sample.result["peaks"][0])
    second.update(peak=2, model="SkewedVoigt")
    sample.result["peaks"].append(second)
    panel.peak.setValue(2)
    assert panel.metric_checks["center"].isEnabled()
    assert panel.metric_checks["area_fraction"].isEnabled()
    sample.result["success"] = False
    panel.set_spectra([sample])
    assert not panel.metric_checks["center"].isEnabled()
    panel.checks["include_failed"].setChecked(True)
    assert panel.metric_checks["center"].isEnabled()
    other = synthetic()
    other.config.peaks = ["SkewedGaussian"]
    sample.result["success"] = True
    panel.peak.setValue(1)
    panel.set_spectra([sample, other])
    assert "混用" in panel.metric_checks["center"].text()
    panel.condition_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    assert not panel.metric_checks["center"].isEnabled()
    panel.close()


def test_fraction_excludes_single_peak_in_mixed_trend_and_export(tmp_path):
    single = synthetic()
    single.result = fit_spectrum(single)
    multi = copy.deepcopy(single)
    multi.id, multi.name = "multi", "Two peaks"
    second = copy.deepcopy(multi.result["peaks"][0])
    second.update(peak=2, area_fraction=.4)
    multi.result["peaks"][0]["area_fraction"] = .6
    multi.result["peaks"].append(second)
    component = multi.result["components"]["p1_"]
    multi.result["components"]["p1_"] = [value * .6 for value in component]
    multi.result["components"]["p2_"] = [value * .4 for value in component]
    settings = {"view": "area_fraction", "metrics": ["area_fraction"], "dpi": 72}
    rows = prepare_trends([single, multi], settings)["rows"]
    assert not rows[0]["valid"] and rows[0]["value"] is None
    assert "單峰" in rows[0]["status"]
    assert rows[1]["valid"] and rows[1]["value"] == .6
    paths, skipped = export_trend_set(tmp_path, [single, multi], settings)
    assert len(paths) == 1 and not skipped
    ax, _ = draw_spectra(Figure(), [single, multi], {"components": True})
    labels = [line.get_label() for line in ax.lines]
    assert single.name + " p1" not in labels
    assert multi.name + " p1" in labels and multi.name + " p2" in labels


def test_template_and_main_share_applicability_and_legacy_migration(window, app, tmp_path):
    populate(window)
    window.open_figure_template()
    dialog = window.template_dialog
    for key in ("fit", "residual", "background", "components"):
        assert not dialog.specific_widgets[key].isEnabled()
    sample = window.spectra[0]
    sample.config.background = "none"
    sample.result = fit_spectrum(sample)
    window._refresh_tree()
    window._draw()
    assert dialog.specific_widgets["fit"].isEnabled()
    assert not dialog.specific_widgets["background"].isEnabled()
    assert not dialog.specific_widgets["components"].isEnabled()
    window.mode.setCurrentIndex(TRENDS)
    panel = window.trend_panel
    panel.load_settings({"metrics": ["center", "area_fraction", "fwhm"], "view": "area_fraction"})
    assert panel.settings()["view"] == "maximum_position"
    assert "center" not in panel.settings()["metrics"]
    assert "area_fraction" not in panel.settings()["metrics"]
    dialog.kind.setCurrentIndex(dialog.kind.findData("trends"))
    assert not dialog.metric_checks["center"].isEnabled()
    assert not dialog.metric_checks["area_fraction"].isEnabled()
    second = copy.deepcopy(sample.result["peaks"][0])
    second.update(peak=2, model="SkewedVoigt")
    sample.result["peaks"].append(second)
    window._refresh_tree()
    window._draw()
    assert panel.metric_checks["area_fraction"].isEnabled()
    assert dialog.metric_checks["area_fraction"].isEnabled()
    panel.peak.setValue(2)
    dialog.specific_widgets["peak"].setValue(2)
    assert panel.metric_checks["center"].isEnabled()
    assert dialog.metric_checks["center"].isEnabled()
    dialog.specific_widgets["view"].setCurrentIndex(dialog.specific_widgets["view"].findData("center"))
    assert dialog.specific_widgets["errorbars"].isEnabled()
    dialog.save_file(tmp_path / "choices.json")
    dialog.load_file(tmp_path / "choices.json")
    assert panel.settings()["view"] == "center"
    assert panel.peak.value() == 2
    dialog.close()


def test_template_style_dependencies(window, app):
    populate(window)
    window.open_figure_template()
    dialog = window.template_dialog
    assert not dialog.option_widgets["bar_hatch"].isEnabled()
    assert not dialog.option_widgets["inset_xlim"].isEnabled()
    dialog.option_widgets["inset"].setChecked(True)
    assert dialog.option_widgets["inset_xlim"].isEnabled()
    dialog.widgets["legend"].setChecked(False)
    assert not dialog.option_widgets["legend_loc"].isEnabled()
    dialog.kind.setCurrentIndex(dialog.kind.findData("trends"))
    dialog.specific_widgets["plot_type"].setCurrentText("bar")
    assert dialog.option_widgets["bar_hatch"].isEnabled()
    assert dialog.specific_widgets["bar_width"].isEnabled()
    assert not dialog.option_widgets["marker"].isEnabled()
    assert not dialog.option_widgets["x_format"].isEnabled()
    scale = dialog.option_widgets["xscale"]
    assert not scale.model().item(scale.findText("log")).isEnabled()
    dialog.specific_widgets["x_mode"].setCurrentText("numeric")
    assert scale.model().item(scale.findText("log")).isEnabled()
    assert dialog.option_widgets["x_format"].isEnabled()
    assert not dialog.specific_widgets["errorbars"].isEnabled()
    assert not dialog.content.labelForField(dialog.specific_widgets["errorbars"]).isEnabled()
    dialog.specific_widgets["plot_type"].setCurrentText("dot")
    assert not dialog.option_widgets["bar_hatch"].isEnabled()
    dialog.close()
