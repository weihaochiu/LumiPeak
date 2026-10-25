import copy

import numpy as np
import pytest
from matplotlib.figure import Figure
from PIL import Image

from plstudio.chart_group import FigureGroup, render_charts
from plstudio.exporting import export_image_set
from plstudio.fitting import fit_spectrum
from plstudio.gui import TRENDS, OVERLAY
from plstudio.plotting import DEFAULT_STYLE
from tests.test_core import synthetic
from tests.test_gui import app, window, populate
from tests.test_origin_format import select


def samples():
    spectra = [synthetic(), synthetic(center=815)]
    for i, s in enumerate(spectra):
        s.name = f"Sample {i+1}"
        s.result = fit_spectrum(s)
    return spectra


def test_adding_graphs_keeps_canvas_size_axes_and_typography(app):
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    spectra = samples()
    style = {"view": "overview", "metrics": ["height"], "width_cm": 12.7, "height_cm": 7.62,
             "font_size": 12, "dpi": 100, "figure_options": {}}
    primary = Figure()
    group = FigureGroup(FigureCanvasQTAgg(primary))
    group.resize(600, 400)
    group.show()
    charts, _ = render_charts(primary, "trends", spectra, style)
    group.set_charts(charts)
    app.processEvents()
    first_size = group.cards[0].canvas.size()
    first_inches = primary.get_size_inches().copy()
    primary.canvas.draw()
    first_bounds = primary.axes[0].get_position().bounds
    font = primary.axes[0].yaxis.label.get_fontsize()
    color = primary.axes[0].lines[0].get_color()
    style["metrics"] = ["height", "maximum_position", "fwhm", "area_in_range"]
    charts, _ = render_charts(primary, "trends", spectra, style)
    group.set_charts(charts)
    app.processEvents()
    assert len(group.cards) == 4
    assert all(card.canvas.size() == first_size for card in group.cards)
    for chart in charts:
        np.testing.assert_allclose(chart.figure.get_size_inches(), first_inches)
        assert len(chart.figure.axes) == 1
    primary.canvas.draw()
    assert primary.axes[0].get_position().bounds == pytest.approx(first_bounds)
    assert primary.axes[0].yaxis.label.get_fontsize() == font
    assert primary.axes[0].lines[0].get_color() == color
    group.resize(1000, 500)
    app.processEvents()
    assert all(card.canvas.size() == first_size for card in group.cards)
    group.close()


def test_main_ui_overlays_and_trends_use_independent_figures(window, app):
    populate(window)
    for sample in window.spectra:
        sample.result = fit_spectrum(sample)
    window.mode.setCurrentIndex(OVERLAY)
    assert len(window.chart_figures) == 2
    assert all(len(fig.axes) == 1 for fig in window.chart_figures)
    size = window.chart_group.cards[0].canvas.size()
    window.overlay_intensity.setCurrentIndex(window.overlay_intensity.findData("raw"))
    assert len(window.chart_figures) == 1
    assert window.chart_group.cards[0].canvas.size() == size
    window.mode.setCurrentIndex(TRENDS)
    assert len(window.chart_figures) == 4
    sizes = [card.canvas.size() for card in window.chart_group.cards]
    window.trend_panel.view.setCurrentIndex(window.trend_panel.view.findData("height"))
    assert len(window.chart_figures) == 1
    assert window.chart_group.cards[0].canvas.size() == sizes[-1]


def test_page_sizes_apply_to_one_or_every_chart_and_export_separately(window, app, tmp_path):
    from plstudio.data import save_project, load_project
    populate(window)
    before = [(s.raw, s.y.copy()) for s in window.spectra]
    window.open_figure_template()
    dialog = window.template_dialog
    keys = [chart.key for chart in dialog.preview_charts]
    assert len(keys) == 2
    dialog.scope_layers[keys[1]] = {"axes": {"right": {"minimum": 5, "maximum": 500, "label": "Target right"}}}
    select(dialog, "chart", keys[0])
    for key, value in {"width_cm": 12.7, "height_cm": 7.62, "dpi": 100, "font_size": 15}.items():
        dialog.page_editor.fields[key].setValue(value)
    assert dialog.preview_charts[0].settings["width_cm"] == 12.7
    assert dialog.preview_charts[1].settings["width_cm"] == DEFAULT_STYLE["width_cm"]
    first_size = dialog.preview_group.cards[0].canvas.size()
    # Independently style one side, then apply the selected graph to the group.
    select(dialog, "layer", keys[0])
    dialog.open_axes("right")
    axis_dialog = dialog.axis_dialog
    axis_dialog.editor.fields["tick_size"].setValue(16)
    axis_dialog.editor.fields["tick_labels"].setChecked(True)
    axis_dialog.editor.fields["axis_color"].setText("purple")
    axis_dialog.editor.fields["axis_color"].editingFinished.emit()
    for field, value in (("minimum", "1"), ("maximum", "1000"), ("label", "Source right")):
        axis_dialog.editor.fields[field].setText(value)
        axis_dialog.editor.fields[field].editingFinished.emit()
    assert axis_dialog.apply()
    axis_dialog.close()
    dialog.apply_each_chart()
    assert "2" in dialog.notice.text()
    assert all(card.canvas.size() == first_size for card in dialog.preview_group.cards)
    for chart in dialog.preview_charts:
        right = chart.figure.axes[0]._pl_side_axes["right"]
        assert right.get_yticklabels()[0].get_fontsize() == 16
        assert right.get_yticklabels()[0].get_color() == "purple"
        assert chart.settings["dpi"] == 100
        assert chart.figure.axes[0].yaxis.label.get_fontsize() == 15
    target = dialog.preview_charts[1].figure.axes[0]._pl_side_axes["right"]
    assert target.get_ylim() == (5, 500) and target.get_ylabel() == "Target right"
    saved = window._read_plot_inputs()
    project = tmp_path/"per_chart.plproj"
    save_project(project, window.spectra, saved)
    _, restored = load_project(project)
    assert restored["chart_styles"] == saved["chart_styles"]
    paths, _ = export_image_set(tmp_path, window.spectra, saved)
    individual = [p for p in paths if p.name.startswith("PL_00")]
    assert len(individual) == 2
    for path in individual:
        with Image.open(path) as image:
            assert image.size == (500, 300)
    for sample, (raw, values) in zip(window.spectra, before):
        assert sample.raw == raw
        np.testing.assert_array_equal(sample.y, values)
    dialog.copy_axis_content.setChecked(True)
    dialog.apply_each_chart()
    target = dialog.preview_charts[1].figure.axes[0]._pl_side_axes["right"]
    assert target.get_ylim() == (1, 1000) and target.get_ylabel() == "Source right"
    dialog.close()


def test_batch_export_keeps_per_chart_dimensions_and_all_checked_metrics(tmp_path):
    spectra = samples()
    style = {"dpi": 100, "width_cm": 12.7, "height_cm": 10.16,
        "overlay": {"width_cm": 12.7, "height_cm": 10.16, "dpi": 100,
                    "chart_styles": {"overlay:normalized": {"width_cm": 15.24, "height_cm": 7.62}}},
        "trends": {"view": "height", "metrics": ["height", "maximum_position", "fwhm"],
                   "width_cm": 12.7, "height_cm": 10.16, "dpi": 100,
                   "chart_styles": {"trend:fwhm": {"width_cm": 7.62, "height_cm": 12.7}}}}
    paths, skipped = export_image_set(tmp_path, spectra, style)
    assert not skipped and len(paths) == 7
    expected = {"PL_overlay_normalized.png": (600, 300), "Peak_1_fwhm.png": (300, 500)}
    for path in paths:
        with Image.open(path) as image:
            assert image.size == expected.get(path.name, (500, 400))
    assert not (tmp_path/"PL_condition_trends.png").exists()


def test_individual_toolbar_export_uses_saved_dpi_and_size(window, app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    populate(window)
    window.mode.setCurrentIndex(OVERLAY)
    card = window.chart_group.cards[1]
    card.navigation.chart.settings.update(width_cm=12.7, height_cm=7.62, dpi=100)
    path = tmp_path/"toolbar.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(path), ""))
    before = card.canvas.size()
    card.navigation.save_figure()
    with Image.open(path) as image:
        assert image.size == (500, 300)
    assert card.canvas.size() == before


def test_optional_overlay_linking_works_across_independent_figures():
    charts, _ = render_charts(Figure(), "overlay", [synthetic()],
                              {"intensity": "both", "figure_options": {"share_x": True}})
    first, second = [chart.figure.axes[0] for chart in charts]
    first.set_xlim(760, 830)
    assert second.get_xlim() == (760, 830)
    assert charts[0].figure is not charts[1].figure


def test_individual_base_font_size_changes_rendered_labels(window, app):
    populate(window)
    window.open_figure_template()
    dialog = window.template_dialog
    key = dialog.preview_charts[0].key
    select(dialog, "chart", key)
    dialog.page_editor.fields["font_size"].setValue(15)
    first, second = dialog.preview_figures
    assert first.axes[0].yaxis.label.get_fontsize() == 15
    assert first.axes[0].get_xticklabels()[0].get_fontsize() == 15
    assert second.axes[0].yaxis.label.get_fontsize() != 15
    dialog.close()


def test_apply_every_chart_can_include_all_plot_types(window, app):
    populate(window)
    for sample in window.spectra:
        sample.result = fit_spectrum(sample)
    fit_ids = [s.result["id"] for s in window.spectra]
    window.open_figure_template()
    dialog = window.template_dialog
    source = dialog.preview_charts[0].key
    select(dialog, "chart", source)
    dialog.page_editor.fields["width_cm"].setValue(12.7)
    select(dialog, "plot", source, window.spectra[0].id+":raw")
    dialog.plot_editor.fields["line_width"].setValue(2.8)
    dialog.apply_scope.setCurrentIndex(dialog.apply_scope.findData("all"))
    dialog.apply_each_chart()
    assert "8" in dialog.notice.text()
    assert all(p["width_cm"] == 12.7 for p in window.plot_settings["chart_styles"].values())
    assert all(p["width_cm"] == 12.7 for p in window._read_overlay_inputs()["chart_styles"].values())
    assert len(window.trend_panel.settings()["chart_styles"]) == 4
    dialog.kind.setCurrentIndex(dialog.kind.findData("trends"))
    for chart in dialog.preview_charts:
        assert chart.settings["width_cm"] == 12.7
        assert chart.figure.axes[0].lines[0].get_linewidth() == 2.8
        assert chart.figure.axes[0].get_ylabel() != window.axes.get_ylabel()
    assert [s.result["id"] for s in window.spectra] == fit_ids
    dialog.close()


def test_legacy_panel_styles_follow_their_chart_into_separate_exports(tmp_path):
    from plstudio.overlay import export_overlay
    spectra = samples()
    settings = {"intensity": "both", "figure_options": {"layers": {
        "1": {"axes": {"left": {"label": "Legacy raw", "axis_color": "red"}}},
        "2": {"axes": {"left": {"label": "Legacy normalized", "axis_color": "green"}}}}}}
    charts, _ = render_charts(Figure(), "overlay", spectra, settings)
    assert charts[0].figure.axes[0].get_ylabel() == "Legacy raw"
    assert charts[1].figure.axes[0].get_ylabel() == "Legacy normalized"
    path = tmp_path/"normalized.svg"
    export_overlay(path, spectra, settings | {"intensity": "normalized"})
    text = path.read_text("utf-8")
    assert "Legacy normalized" in text and "Legacy raw" not in text
