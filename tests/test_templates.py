import copy
import json

import numpy as np
import pytest
from matplotlib.figure import Figure
from PIL import Image

from plstudio.data import save_project, load_project
from plstudio.figure_style import DEFAULT_OPTIONS, figure_size, validate_options
from plstudio.fitting import fit_spectrum
from plstudio.gui import TRENDS, OVERLAY
from plstudio.overlay import draw_overlay, export_overlay
from plstudio.plotting import DEFAULT_STYLE
from plstudio.trends import DEFAULT_TRENDS, draw_trends
from tests.test_core import synthetic
from tests.test_gui import app, window, populate


@pytest.mark.parametrize("kind", ["dot", "line", "dot-line", "bar", "area"])
def test_trend_plot_types_with_same_data(kind):
    spectra = [synthetic(), synthetic(amplitude=10000)]
    for i, s in enumerate(spectra):
        s.name = str(i)
        s.result = fit_spectrum(s)
    axes, prepared = draw_trends(Figure(), spectra, {"view": "center", "plot_type": kind})
    ax = axes[0]
    assert len(prepared["rows"]) == 2
    if kind == "bar":
        assert len(ax.patches) == 2
        assert ax.patches[0].get_height() == spectra[0].result["peaks"][0]["center"]
    else:
        assert np.allclose(ax.lines[0].get_ydata(), [s.result["peaks"][0]["center"] for s in spectra])
        if kind == "dot":
            assert ax.lines[0].get_linestyle() == "None"
        elif kind in ("line", "area"):
            assert ax.lines[0].get_marker() == "None"
        if kind == "area":
            assert len(ax.collections) > 0


def test_advanced_figure_formatting_and_export(tmp_path):
    spectrum = synthetic()
    options = DEFAULT_OPTIONS | {"reverse_x": True, "minor_ticks": True, "x_major_step": 20,
        "legend_frame": True, "legend_columns": 2, "marker": "s", "reference_y": [1000],
        "panel_labels": True, "inset": True, "inset_xlim": [790, 820], "inset_ylim": [1000, 1800],
        "annotations": [{"layer": 1, "text": "PL", "xy": [.1, .8]}],
        "shapes": [{"layer": 1, "type": "rectangle", "xy": [.1, .1], "width": .1, "height": .1}],
        "layers": {"1": {"ylabel": "Custom counts"}}}
    settings = {"intensity": "raw", "figure_options": options, "font_size": 11,
                "width_cm": 15.24, "height_cm": 10.16, "dpi": 100}
    figure = Figure()
    ax, _ = draw_overlay(figure, [spectrum], settings)
    assert ax.xaxis_inverted()
    assert ax.get_ylabel() == "Custom counts"
    assert ax.lines[0].get_marker() == "s"
    assert ax.get_legend().get_frame_on()
    assert len(ax.child_axes) == 1
    assert any(t.get_text() == "PL" for t in ax.texts)
    assert any(t.get_text() == "(a)" for t in ax.texts)
    export_overlay(tmp_path/"styled.png", [spectrum], settings)
    with Image.open(tmp_path/"styled.png") as image:
        assert image.size == (600, 400)
    assert figure_size(settings | {"figure_options": {"orientation": "landscape"}}) == pytest.approx((6, 4))
    with pytest.raises(ValueError, match="正數"):
        validate_options({"axis_width": -1})


def test_template_preserves_categorical_condition_labels():
    spectra = [synthetic(), synthetic(amplitude=10000)]
    for name, s in zip(("Control", "Treatment"), spectra):
        s.condition = name
        s.result = fit_spectrum(s)
    axes, _ = draw_trends(Figure(), spectra, {"view": "center", "plot_type": "bar", "figure_options": {}})
    assert [text.get_text() for text in axes[0].get_xticklabels()] == ["Control", "Treatment"]


def test_per_kind_template_file_apply_and_project_roundtrip(window, app, tmp_path):
    populate(window)
    for s in window.spectra:
        s.result = fit_spectrum(s)
    window.mode.setCurrentIndex(OVERLAY)
    window.open_figure_template()
    dialog = window.template_dialog
    assert window.mode.count() == 3
    assert dialog.isVisible()
    assert dialog.active_kind == "overlay"
    dialog.widgets["line_width"].setValue(2.4)
    dialog.widgets["height_cm"].setValue(16)
    dialog.option_widgets["legend_columns"].setValue(2)
    dialog.kind.setCurrentIndex(dialog.kind.findData("trends"))
    assert dialog.active_kind == "trends"
    dialog.widgets["line_width"].setValue(1.2)
    dialog.specific_widgets["plot_type"].setCurrentText("bar")
    dialog.widgets["font_size"].setValue(12)
    dialog.apply(True)
    assert window._read_overlay_inputs()["line_width"] == 2.4
    assert window._read_overlay_inputs()["height_cm"] == 16
    assert window.trend_panel.plot_type.currentData() == "bar"
    assert window.trend_panel.settings()["line_width"] == 1.2
    assert window.trend_panel.settings()["font_size"] == 12
    # The source data and fitted results are not part of a style template.
    original_fit_id = window.spectra[0].result["id"]
    path = tmp_path/"settings.json"
    dialog.save_file(path)
    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["version"] == 2
    assert set(content["figures"]) == {"spectrum", "trends", "overlay"}
    dialog.specific_widgets["plot_type"].setCurrentText("line")
    dialog.apply(False)
    assert window.trend_panel.plot_type.currentData() == "line"
    dialog.load_file(path)
    assert window.trend_panel.plot_type.currentData() == "bar"
    assert window.spectra[0].result["id"] == original_fit_id
    project = tmp_path/"templated.plproj"
    save_project(project, window.spectra, window._read_plot_inputs())
    _, saved = load_project(project)
    assert saved["trends"]["plot_type"] == "bar"
    assert saved["overlay"]["figure_options"]["legend_columns"] == 2
    assert saved["overlay"]["line_width"] == 2.4
    legacy = tmp_path/"old.json"
    legacy.write_text(json.dumps({"type": "PLStudioPlotStyle", "version": 1,
                                  "settings": {"font_size": 14, "line_width": 3}}), encoding="utf-8")
    dialog.load_file(legacy)
    assert window.plot_settings["font_size"] == 14
    assert window._read_overlay_inputs()["line_width"] == 2.4
    dialog.close()


def test_main_trend_type_control(window, app):
    populate(window)
    for s in window.spectra:
        s.result = fit_spectrum(s)
    window.mode.setCurrentIndex(TRENDS)
    window.trend_panel.view.setCurrentIndex(window.trend_panel.view.findData("center"))
    window.trend_panel.plot_type.setCurrentIndex(window.trend_panel.plot_type.findData("bar"))
    assert len(window.axes.patches) == 2
    window.trend_panel.plot_type.setCurrentIndex(window.trend_panel.plot_type.findData("dot-line"))
    assert window.axes.lines[0].get_linestyle() == "-"
    assert window.axes.lines[0].get_marker() == "o"
