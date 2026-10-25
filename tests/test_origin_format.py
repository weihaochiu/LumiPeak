"""Behavioral checks for object scope, axis independence, and saved exports."""
import copy
import json

import numpy as np
import pytest
from matplotlib.figure import Figure
from matplotlib.colors import to_hex
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItemIterator

from plstudio.figure_style import validate_options, plot_items
from plstudio.overlay import draw_overlay, export_overlay
from plstudio.plotting import draw_spectra
from plstudio.fitting import fit_spectrum
from plstudio.origin_format import AXIS_SIDES
from tests.test_core import synthetic
from tests.test_gui import app, window, populate


def select(dialog, level, layer, plot=""):
    iterator = QTreeWidgetItemIterator(dialog.object_tree)
    while iterator.value():
        item = iterator.value()
        if tuple(item.data(0, Qt.ItemDataRole.UserRole)) == (level, layer, plot):
            dialog.object_tree.setCurrentItem(item)
            return item
        iterator += 1
    raise AssertionError((level, layer, plot))


def test_plot_scope_survives_rename_filter_and_separate_export(tmp_path):
    first, second = synthetic(), synthetic()
    second.name = "Other"
    before = second.y.copy()
    options = {"layers": {"overlay:normalized": {"plots": {second.id+":raw": {
        "color": "red", "line_width": 3, "marker": "s"}}}}}
    settings = {"intensity": "both", "figure_options": options}
    fig = Figure()
    draw_overlay(fig, [first, second], settings)
    assert fig.axes[0].lines[1].get_color() != "red"
    assert fig.axes[1].lines[0].get_color() != "red"
    assert fig.axes[1].lines[1].get_color() == "red"
    first.plot = False
    second.name = "Renamed"
    normalized = settings | {"intensity": "normalized"}
    draw_overlay(fig, [first, second], normalized)
    line = fig.axes[0].lines[0]
    assert line.get_color() == "red" and line.get_linewidth() == 3
    assert line.get_label() == "Renamed"
    np.testing.assert_array_equal(second.y, before)
    export_overlay(tmp_path/"normalized.svg", [first, second], normalized)
    assert "#ff0000" in (tmp_path/"normalized.svg").read_text("utf-8")


def test_axes_keep_independent_scale_labels_ticks_and_grids():
    sample = synthetic()
    settings = {"intensity": "raw", "figure_options": {"layers": {"overlay:raw": {"axes": {
        "x": {"minimum": 750, "maximum": 850, "major_step": 25, "label": "Custom X", "reverse": True},
        "y": {"scale": "log", "minimum": 1, "maximum": 10000, "grid": True,
              "tick_size": 17, "label": "Custom Y", "references": [500]}}}}}}
    fig = Figure()
    draw_overlay(fig, [sample], settings)
    ax = fig.axes[0]
    assert ax.get_xlim() == (850, 750)
    assert ax.get_xscale() == "linear" and ax.get_yscale() == "log"
    assert ax.get_xlabel() == "Custom X" and ax.get_ylabel() == "Custom Y"
    assert ax.get_yticklabels()[0].get_fontsize() == 17
    assert not any(line.get_visible() for line in ax.get_xgridlines())
    assert any(line.get_visible() for line in ax.get_ygridlines())
    assert any(np.all(np.asarray(line.get_ydata()) == 500) for line in ax.lines)


def test_raw_and_fit_ids_remain_distinct_when_raw_hidden():
    sample = synthetic()
    sample.result = fit_spectrum(sample)
    settings = {"raw": False, "fit": True, "figure_options": {"layers": {"1": {"plots": {
        sample.id+":raw": {"color": "red"}, sample.id+":fit": {"color": "green"}}}}}}
    fig = Figure()
    draw_spectra(fig, [sample], settings)
    assert len(fig.axes[0].lines) == 1
    assert fig.axes[0].lines[0].get_color() == "green"


def test_overlay_layers_have_independent_axes_unless_linked():
    options = {"layers": {"overlay:raw": {"axes": {"x": {"minimum": 760, "maximum": 820}}}}}
    fig = Figure()
    draw_overlay(fig, [synthetic()], {"intensity": "both", "figure_options": options})
    assert fig.axes[0].get_xlim() == (760, 820)
    assert fig.axes[1].get_xlim() != (760, 820)
    draw_overlay(fig, [synthetic()], {"intensity": "both", "figure_options": options | {"share_x": True}})
    assert fig.axes[0].get_xlim() == fig.axes[1].get_xlim()


def test_object_edit_apply_cancel_template_and_axis_validation(window, app, tmp_path):
    populate(window)
    window.open_figure_template()
    dialog = window.template_dialog
    sample = window.spectra[1]
    sample_key = "spectrum:"+sample.id
    first_key = "spectrum:"+window.spectra[0].id
    select(dialog, "plot", sample_key, sample.id+":raw")
    dialog.plot_editor.fields["line_width"].setValue(4.5)
    dialog.plot_editor.fields["color"].setText("#ff00ff")
    dialog.plot_editor.fields["color"].editingFinished.emit()
    chart = next(c for c in dialog.preview_charts if c.key == sample_key)
    assert chart.figure.axes[0].lines[0].get_linewidth() == 4.5
    assert dialog.figure.axes[0].lines[0].get_linewidth() != 4.5
    assert not window.plot_settings.get("figure_options", {}).get("layers")
    select(dialog, "layer", first_key)
    dialog.layer_editor.fields["title"].setText("Only this layer")
    dialog.layer_editor.fields["title"].editingFinished.emit()
    dialog.layer_editor.fields["manual_position"].setChecked(True)
    for key, value in {"left": 20, "top": 10, "width": 70, "height": 70}.items():
        dialog.layer_editor.fields[key].setValue(value)
    assert dialog.read_settings()["figure_options"]["layers"][first_key]["position"] == pytest.approx([.2, .2, .7, .7])
    dialog.open_axes()
    axis = dialog.axis_dialog
    axis.editor.fields["minimum"].setText("850")
    axis.editor.fields["maximum"].setText("750")
    axis.editor.fields["minimum"].editingFinished.emit()
    axis.editor.fields["maximum"].editingFinished.emit()
    assert axis.apply() is False
    assert not dialog.scope_layers[first_key].get("axes")
    axis.editor.fields["minimum"].setText("750")
    axis.editor.fields["maximum"].setText("850")
    axis.editor.fields["minimum"].editingFinished.emit()
    axis.editor.fields["maximum"].editingFinished.emit()
    assert axis.apply()
    axis.close()
    dialog.apply()
    saved = copy.deepcopy(window.plot_settings["figure_options"])
    assert saved["layers"][sample_key]["plots"][sample.id+":raw"]["color"] == "#ff00ff"
    path = tmp_path/"format.json"
    dialog.save_file(path)
    assert json.loads(path.read_text("utf-8"))["figures"]["spectrum"]["figure_options"] == saved
    select(dialog, "plot", sample_key, sample.id+":raw")
    dialog.plot_editor.fields["line_width"].setValue(7)
    dialog.close()
    window.open_figure_template()
    assert dialog.read_settings()["figure_options"] == saved
    assert dialog.figure.axes[0].get_title() == "Only this layer"
    dialog.close()


@pytest.mark.parametrize("patch", [
    {"position": [0, 0, 2, 1]}, {"axes": {"x": {"minimum": float("nan")}}},
    {"axes": {"y": {"scale": "log", "minimum": 0}}},
    {"plots": {"id": {"line_width": -2}}}, {"plots": {"id": {"color": "bad-color"}}},
])
def test_reject_invalid_scoped_settings(patch):
    with pytest.raises(ValueError):
        validate_options({"layers": {"1": patch}})


def four_sides():
    return {
        "bottom": {"minimum": 730, "maximum": 880, "major_step": 30,
                   "label": "Bottom wavelength", "axis_color": "blue", "tick_size": 9,
                   "axis_width": 1, "tick_labels": True},
        "top": {"minimum": 10, "maximum": 20, "reverse": True, "major_step": 2,
                "label": "Top independent X", "axis_color": "red", "tick_size": 12,
                "axis_width": 2, "tick_labels": True, "format": "fixed", "decimals": 1},
        "left": {"minimum": 0, "maximum": 2000, "major_step": 400,
                 "label": "Left counts", "axis_color": "green", "tick_size": 10,
                 "axis_width": 1.5, "tick_labels": True, "grid": True},
        "right": {"minimum": 1, "maximum": 1000, "scale": "log",
                  "label": "Right independent Y", "axis_color": "purple", "tick_size": 14,
                  "axis_width": 3, "tick_labels": True, "minor_ticks": True},
    }


def test_all_four_axis_scales_and_styles_are_independent_and_exported(tmp_path):
    from plstudio.plotting import export_figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    sample = synthetic()
    original = sample.y.copy()
    settings = {"fit": False, "figure_options": {"layers": {"1": {"axes": four_sides()}}},
                "width_cm": 18, "height_cm": 13, "dpi": 100}
    fig = Figure()
    FigureCanvasAgg(fig)
    draw_spectra(fig, [sample], settings)
    fig.canvas.draw()
    ax = fig.axes[0]
    rulers = ax._pl_side_axes
    assert len(fig.axes) == 1 and len(ax.child_axes) == 2
    assert ax.get_xlim() == (730, 880) and ax.get_ylim() == (0, 2000)
    assert rulers["top"].get_xlim() == (20, 10)
    assert rulers["right"].get_ylim() == (1, 1000)
    assert ax.get_yscale() == "linear" and rulers["right"].get_yscale() == "log"
    for side, values in four_sides().items():
        ruler = rulers[side]
        direction = "x" if side in ("bottom", "top") else "y"
        axis = getattr(ruler, direction+"axis")
        assert axis.label.get_text() == values["label"]
        assert to_hex(ruler.spines[side].get_edgecolor()) == to_hex(values["axis_color"])
        assert ruler.spines[side].get_linewidth() == values["axis_width"]
        texts = axis.get_ticklabels()
        assert texts and texts[0].get_fontsize() == values["tick_size"]
        assert to_hex(texts[0].get_color()) == to_hex(values["axis_color"])
    np.testing.assert_array_equal(sample.y, original)
    export_figure(tmp_path/"four_axes.svg", [sample], settings)
    svg = (tmp_path/"four_axes.svg").read_text("utf-8")
    assert all(values["label"] in svg for values in four_sides().values())
    # Drawing afresh replaces the rulers instead of adding data layers or copies.
    draw_spectra(fig, [sample], settings)
    assert len(fig.axes) == 1 and len(fig.axes[0].child_axes) == 2


def test_side_visibility_and_labels_do_not_hide_opposite_axes():
    from plstudio.plotting import draw_spectra
    config = four_sides()
    config["bottom"]["tick_labels"] = False
    config["right"]["visible"] = False
    fig = Figure()
    draw_spectra(fig, [synthetic()], {"figure_options": {"layers": {"1": {"axes": config}}}})
    ax = fig.axes[0]
    assert not ax.get_xticklabels()
    assert ax._pl_side_axes["top"].get_xticklabels()
    assert ax.spines["left"].get_visible()
    assert not ax._pl_side_axes["right"].spines["right"].get_visible()
    assert not ax._pl_side_axes["right"].yaxis.label.get_visible()


def test_four_sides_ui_apply_template_project_and_cancel(window, app, tmp_path):
    from plstudio.data import save_project, load_project
    populate(window)
    window.open_figure_template()
    dialog = window.template_dialog
    chart_key = "spectrum:"+window.spectra[0].id
    select(dialog, "layer", chart_key)
    dialog.open_axes("right")
    axis_dialog = dialog.axis_dialog
    assert axis_dialog.axes_list.count() == 4
    assert axis_dialog.direction == "right"
    for row, side in enumerate(AXIS_SIDES):
        axis_dialog.axes_list.setCurrentRow(row)
        for key, value in four_sides()[side].items():
            widget = axis_dialog.editor.fields[key]
            if hasattr(widget, "setChecked"):
                widget.setChecked(value)
            elif hasattr(widget, "setValue"):
                widget.setValue(value)
            elif hasattr(widget, "setCurrentText"):
                widget.setCurrentText(value)
            else:
                widget.setText(str(value))
                widget.editingFinished.emit()
    assert axis_dialog.apply()
    axis_dialog.close()
    assert dialog.apply()
    saved = copy.deepcopy(window.plot_settings["figure_options"])
    axes = saved["layers"][chart_key]["axes"]
    assert set(axes) == set(AXIS_SIDES)
    for side, values in four_sides().items():
        resolved = axis_dialog.values_by_axis[side] | axes[side]
        assert all(resolved.get(key) == value for key, value in values.items())
    path = tmp_path/"four_sides.json"
    dialog.save_file(path)
    dialog.load_file(path)
    assert window.plot_settings["figure_options"] == saved
    project = tmp_path/"four_sides.plproj"
    save_project(project, window.spectra, window._read_plot_inputs())
    _, restored = load_project(project)
    assert restored["figure_options"] == saved
    dialog.open_axes("top")
    axis_dialog = dialog.axis_dialog
    axis_dialog.editor.fields["label"].setText("Discard me")
    axis_dialog.editor.fields["label"].editingFinished.emit()
    axis_dialog.reject()
    assert dialog.read_settings()["figure_options"] == saved
    dialog.close()


def test_old_axis_settings_are_read_and_side_overrides_win():
    fig = Figure()
    legacy = {"x": {"minimum": 740, "maximum": 870, "label": "Old X"},
              "y": {"minimum": 1, "maximum": 2000, "label": "Old Y"},
              "top": {"minimum": 1, "maximum": 2, "label": "New top", "tick_labels": True},
              "left": {"label": "New left"}}
    draw_spectra(fig, [synthetic()], {"figure_options": {"layers": {"1": {"axes": legacy}}}})
    ax = fig.axes[0]
    assert ax.get_xlim() == (740, 870) and ax.get_xlabel() == "Old X"
    assert ax.get_ylim() == (1, 2000) and ax.get_ylabel() == "New left"
    assert ax._pl_side_axes["top"].get_xlim() == (1, 2)
