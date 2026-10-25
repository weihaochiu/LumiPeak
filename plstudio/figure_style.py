"""Shared 2-D figure formatting used by all PL plot types.

The controls follow Origin's page/layer/axis/plot/object hierarchy, while
remaining Matplotlib settings rather than Origin template files or LabTalk.
"""
from __future__ import annotations

from .i18n import tr

import string
from pathlib import Path

import numpy as np
from matplotlib import colormaps
from matplotlib.colors import is_color_like
from matplotlib.patches import Rectangle, Ellipse
from matplotlib.ticker import AutoMinorLocator, FormatStrFormatter, LogLocator, MaxNLocator, MultipleLocator, ScalarFormatter, NullLocator

DEFAULT_OPTIONS = {
    "page_color": "white", "layer_color": "white", "orientation": "custom",
    "layout_mode": "tight", "columns": 0, "left": .15, "right": .96, "bottom": .15, "top": .90,
    "hspace": .40, "wspace": .35, "share_x": False,
    "xscale": "linear", "yscale": "linear", "reverse_x": False, "reverse_y": False,
    "axis_color": "black", "axis_width": 1.0, "top_axis": True, "right_axis": True,
    "x_label_size": 11.0, "y_label_size": 11.0, "title_size": 11.0,
    "tick_size": 10.0, "font_weight": "normal", "text_color": "black", "label_pad": 5.0,
    "tick_direction": "in", "major_length": 4.0, "minor_length": 2.0, "tick_width": 1.0,
    "x_major_step": 0.0, "y_major_step": 0.0, "x_major_count": 6, "y_major_count": 6,
    "minor_ticks": False, "minor_divisions": 2, "x_rotation": 0.0, "y_rotation": 0.0,
    "x_format": "auto", "y_format": "auto", "decimals": 2,
    "special_x_ticks": [], "special_y_ticks": [],
    "minor_grid": False, "grid_color": "#c9d2dc", "grid_width": .6, "grid_style": "-", "grid_alpha": .4,
    "palette": "preserve", "line_style": "preserve", "line_alpha": 1.0,
    "marker": "preserve", "marker_size": 5.5, "marker_face": "auto", "marker_edge": "auto", "marker_edge_width": .8,
    "bar_edge": "black", "bar_hatch": "", "bar_alpha": .85,
    "legend_loc": "best", "legend_columns": 1, "legend_frame": False, "legend_alpha": 1.0,
    "legend_size": 9.0, "legend_title": "", "legend_outside": False, "legend_reverse": False,
    "legend_face": "white", "legend_edge": "#888888", "legend_spacing": .5,
    "error_width": 1.0, "error_capsize": 3.0,
    "panel_labels": False, "panel_label_style": "a", "panel_label_x": -.12, "panel_label_y": 1.06,
    "reference_x": [], "reference_y": [], "reference_color": "#888888", "reference_style": "--",
    "annotations": [], "shapes": [], "layers": {},
    "inset": False, "inset_layer": 1, "inset_box": [.58, .52, .36, .40],
    "inset_xlim": [], "inset_ylim": [], "inset_connectors": True,
    "transparent": False, "tight_export": False, "export_pad": .1, "jpeg_quality": 95,
}


def validate_options(options):
    unknown = set(options)-set(DEFAULT_OPTIONS)
    if unknown:
        raise ValueError(tr("不支援的 Figure 設定：")+", ".join(sorted(unknown)))
    merged = DEFAULT_OPTIONS | options
    for key, value in merged.items():
        if isinstance(value, (int, float)) and not np.isfinite(value):
            raise ValueError(tr("設定值必須是有限數值。"))
    for key, choices in {"xscale": ("linear", "log", "symlog"), "yscale": ("linear", "log", "symlog"),
                         "x_format": ("auto", "fixed", "scientific", "plain"),
                         "y_format": ("auto", "fixed", "scientific", "plain"),
                         "tick_direction": ("in", "out", "inout")}.items():
        if merged[key] not in choices:
            raise ValueError(tr("刻度格式設定無效。"))
    if not isinstance(merged["decimals"], int) or not 0 <= merged["decimals"] <= 15:
        raise ValueError(tr("刻度格式設定無效。"))
    for key in ("page_color", "layer_color", "axis_color", "text_color", "grid_color", "legend_face", "legend_edge", "reference_color", "bar_edge"):
        if not is_color_like(merged[key]):
            raise ValueError(tr('{0} 不是有效的顏色。').format(key, ''))
    for key in ("marker_face", "marker_edge"):
        if merged[key] != "auto" and not is_color_like(merged[key]):
            raise ValueError(tr('{0} 不是有效的顏色。').format(key, ''))
    for key in ("annotations", "shapes", "reference_x", "reference_y", "special_x_ticks", "special_y_ticks",
                "inset_box", "inset_xlim", "inset_ylim"):
        if not isinstance(merged[key], list):
            raise ValueError(tr('{0} 必須是 JSON 陣列。').format(key, ''))
    if not isinstance(merged["layers"], dict):
        raise ValueError(tr("圖層覆寫必須是 JSON 物件。"))
    validate_layers(merged["layers"])
    for key in ("axis_width", "x_label_size", "y_label_size", "title_size", "tick_size", "tick_width",
                "major_length", "minor_length", "marker_size", "legend_size", "grid_width", "error_width"):
        if not isinstance(merged[key], (int, float)) or not np.isfinite(merged[key]) or merged[key] <= 0:
            raise ValueError(tr('{0} 必須為有限正數。').format(key, ''))
    for key in ("minor_divisions", "x_major_count", "y_major_count", "legend_columns", "inset_layer"):
        if not isinstance(merged[key], int) or merged[key] < 1:
            raise ValueError(tr('{0} 必須為正整數。').format(key, ''))
    for key in ("line_alpha", "legend_alpha", "grid_alpha", "bar_alpha"):
        if not 0 <= merged[key] <= 1:
            raise ValueError(tr('{0} 必須介於 0 與 1。').format(key, ''))
    if not 1 <= merged["jpeg_quality"] <= 100:
        raise ValueError(tr("JPEG 品質必須介於 1 與 100。"))
    for key in ("reference_x", "reference_y", "special_x_ticks", "special_y_ticks", "inset_box", "inset_xlim", "inset_ylim"):
        if not all(isinstance(v, (int, float)) and np.isfinite(v) for v in merged[key]):
            raise ValueError(tr('{0} 必須包含有限數值。').format(key, ''))
    if not 0 <= merged["left"] < merged["right"] <= 1 or not 0 <= merged["bottom"] < merged["top"] <= 1:
        raise ValueError(tr("頁面邊界需滿足 0 ≤ 左 < 右 ≤ 1，0 ≤ 下 < 上 ≤ 1。"))
    if len(merged["inset_box"]) != 4 or min(merged["inset_box"][2:]) <= 0:
        raise ValueError(tr("Inset 位置需為 [left, bottom, width, height]，寬高需為正數。"))
    for key in ("inset_xlim", "inset_ylim"):
        value = merged[key]
        if value and (len(value) != 2 or value[0] >= value[1]):
            raise ValueError(tr('{0} 需為 [下限, 上限]。').format(key, ''))
    return merged


def layer_key(ax, index):
    return getattr(ax, "_pl_style_key", str(index))


def plot_items(ax):
    """Stable IDs survive spectrum renaming, filtering, and separate export."""
    items = [(getattr(line, "_pl_style_key", line.get_label()), line) for line in ax.lines
             if line.get_label() != "_nolegend_" and not getattr(line, "_pl_reference", False)]
    items.extend((getattr(c, "_pl_style_key", f"bar:{i}"), c) for i, c in enumerate(ax.containers)
                 if hasattr(c, "patches"))
    return items


def validate_layers(layers):
    from .origin_format import AXIS_SECTIONS, PLOT_SECTIONS, AXIS_SIDES, axis_direction
    axis_keys = {key for _, fields in AXIS_SECTIONS for key, _, _ in fields}
    plot_keys = {key for _, fields in PLOT_SECTIONS for key, _, _ in fields} | {"visible"}
    for layer in layers.values():
        if not isinstance(layer, dict):
            raise ValueError(tr("圖層覆寫必須是 JSON 物件。"))
        if "options" in layer:
            if "layers" in layer["options"]:
                raise ValueError(tr("圖層不可包含巢狀圖層。"))
            validate_options(layer["options"])
        if "position" in layer:
            p = layer["position"]
            if (not isinstance(p, list) or len(p) != 4 or not all(isinstance(v, (int, float)) and np.isfinite(v) for v in p)
                    or min(p) < 0 or min(p[2:]) <= 0 or p[0]+p[2] > 1.000001 or p[1]+p[3] > 1.000001):
                raise ValueError(tr("圖層位置必須位於頁面內，且寬高大於零。"))
        for key in ("xlim", "ylim"):
            if key in layer:
                limits = layer[key]
                if len(limits) != 2 or not all(np.isfinite(v) for v in limits) or limits[0] >= limits[1]:
                    raise ValueError(tr("座標下限必須小於上限。"))
        for direction, axis in layer.get("axes", {}).items():
            if direction not in ("x", "y", *AXIS_SIDES) or not isinstance(axis, dict) or set(axis)-axis_keys:
                raise ValueError(tr("座標軸設定無效。"))
            for flag in ("visible", "tick_labels"):
                if flag in axis and not isinstance(axis[flag], bool):
                    raise ValueError(tr("座標軸設定無效。"))
            lo, hi = axis.get("minimum"), axis.get("maximum")
            if any(v is not None and (not isinstance(v, (int, float)) or not np.isfinite(v)) for v in (lo, hi)):
                raise ValueError(tr("座標範圍必須是有限值。"))
            if lo is not None and hi is not None and lo >= hi:
                raise ValueError(tr("座標下限必須小於上限。"))
            if axis.get("scale") not in (None, "linear", "log", "symlog") or axis.get("scale") == "log" and any(v is not None and v <= 0 for v in (lo, hi)):
                raise ValueError(tr("對數座標的顯示範圍必須大於零。"))
            translated = _axis_options(DEFAULT_OPTIONS, axis_direction(direction), axis)
            validate_options(translated | {"layers": {}})
            for key in ("major_step",):
                if key in axis and (not np.isfinite(axis[key]) or axis[key] < 0):
                    raise ValueError(tr("刻度間隔必須大於或等於零。"))
        for plot in layer.get("plots", {}).values():
            if not isinstance(plot, dict) or set(plot)-plot_keys:
                raise ValueError(tr("曲線設定無效。"))
            if "color" in plot and not is_color_like(plot["color"]):
                raise ValueError(tr("曲線顏色無效。"))
            if "line_width" in plot and (not np.isfinite(plot["line_width"]) or plot["line_width"] <= 0):
                raise ValueError(tr("線寬必須為正數。"))
            validate_options({k: v for k, v in plot.items() if k in DEFAULT_OPTIONS})


def _axis_options(base, direction, axis):
    options = dict(base)
    mapping = {"scale": direction+"scale", "reverse": "reverse_"+direction,
               "major_step": direction+"_major_step", "major_count": direction+"_major_count",
               "format": direction+"_format", "rotation": direction+"_rotation",
               "label_size": direction+"_label_size", "special_ticks": "special_"+direction+"_ticks",
               "references": "reference_"+direction}
    for key, value in axis.items():
        target = mapping.get(key, key)
        if target in DEFAULT_OPTIONS:
            options[target] = value
    return options


def _apply_axis_details(ax, direction, axis, local, settings, categorical, side=None):
    opts = _axis_options(local, direction, axis)
    lo, hi = axis.get("minimum"), axis.get("maximum")
    if lo is not None or hi is not None:
        getattr(ax, "set_"+direction+"lim")(lo, hi)
    _format_axis(ax, direction, opts, categorical)
    if "label" in axis:
        getattr(ax, "set_"+direction+"label")(axis["label"])
    label = getattr(ax, direction+"axis").label
    label.set_fontsize(opts[direction+"_label_size"])
    label.set_color(axis.get("axis_color", local["text_color"]))
    label.set_fontfamily([settings.get("font", "Arial"), "Microsoft JhengHei"])
    label.set_fontweight(local["font_weight"])
    getattr(ax, direction+"axis").labelpad = opts["label_pad"]
    for spine_side in ([side] if side else (("bottom", "top") if direction == "x" else ("left", "right"))):
        ax.spines[spine_side].set_color(opts["axis_color"])
        ax.spines[spine_side].set_linewidth(opts["axis_width"])
    ax.tick_params(axis=direction, which="major", labelsize=opts["tick_size"], colors=opts["axis_color"],
                   direction=opts["tick_direction"], length=opts["major_length"], width=opts["tick_width"])
    ax.tick_params(axis=direction, which="minor", colors=opts["axis_color"], direction=opts["tick_direction"],
                   length=opts["minor_length"], width=opts["tick_width"])
    if side:
        visible = axis.get("visible", local.get(side+"_axis", True))
        ax.spines[side].set_visible(visible)
        kwargs = {side: visible}
        # Preserve residual panels' intentionally hidden bottom tick labels
        # unless this side has an explicit Show setting.
        if "tick_labels" in axis or side in ("top", "right") or not visible:
            kwargs["label"+side] = visible and axis.get("tick_labels", side in ("bottom", "left"))
        ax.tick_params(axis=direction, which="both", **kwargs)
        label.set_visible(visible)
    for text in getattr(ax, "get_"+direction+"ticklabels")():
        text.set_fontfamily([settings.get("font", "Arial"), "Microsoft JhengHei"])
        text.set_fontweight(local["font_weight"])
    ax.grid(False, axis=direction, which="both")
    for which, enabled in (("major", axis.get("grid", settings.get("grid", False))), ("minor", opts["minor_grid"])):
        if enabled:
            ax.grid(True, axis=direction, which=which, color=opts["grid_color"],
                    linewidth=opts["grid_width"], linestyle=opts["grid_style"], alpha=opts["grid_alpha"])
    for value in opts["reference_"+direction]:
        line = (ax.axvline if direction == "x" else ax.axhline)(value, color=opts["reference_color"], linestyle=opts["reference_style"])
        line._pl_reference = True


def _apply_four_axes(ax, axes, local, settings, categorical):
    """Use child axes for independent top/right scales without adding data layers.

    The child axes contain only rulers, grids and reference lines. Their data
    limits never alter the parent data transform or the opposite ruler.
    """
    from .origin_format import side_settings
    for child in list(ax.child_axes):
        if getattr(child, "_pl_axis_side", None):
            child.remove()
    ax._pl_side_axes = {"bottom": ax, "left": ax}
    for side, direction in (("bottom", "x"), ("left", "y")):
        _apply_axis_details(ax, direction, side_settings(axes, side), local, settings,
                            categorical if direction == "x" else False, side=side)
    for side, opposite, direction in (("top", "bottom", "x"), ("right", "left", "y")):
        if side not in axes and opposite not in axes:
            continue
        child = ax.inset_axes([0, 0, 1, 1], transform=ax.transAxes, zorder=4)
        child._pl_axis_side = side
        child._pl_owner_axis = ax
        child.patch.set_visible(False)
        child.set_navigate(False)
        child.set_xlim(sorted(ax.get_xlim()))
        child.set_ylim(sorted(ax.get_ylim()))
        child.xaxis.set_visible(direction == "x")
        child.yaxis.set_visible(direction == "y")
        for spine_side, spine in child.spines.items():
            spine.set_visible(spine_side == side)
        # Hide the parent's mirrored ticks and spine to avoid double drawing.
        ax.spines[side].set_visible(False)
        ax.tick_params(axis=direction, which="both", **{side: False, "label"+side: False})
        axis = getattr(child, direction+"axis")
        axis.set_ticks_position(side)
        axis.set_label_position(side)
        if direction == "x" and categorical:
            ticks = ax.get_xticks()
            child.set_xticks(ticks, ax.xaxis.get_major_formatter().format_ticks(ticks))
        # Inherit visual defaults, but do not duplicate the primary grids or
        # reference lines on the independent ruler.
        secondary = local | {"reference_x": [], "reference_y": [], "minor_grid": False}
        _apply_axis_details(child, direction, side_settings(axes, side), secondary,
                            settings | {"grid": False}, categorical if direction == "x" else False, side=side)
        child.set_visible(ax.get_visible())
        ax._pl_side_axes[side] = child


def _apply_plot_details(ax, overrides):
    for key, artist in plot_items(ax):
        patch = overrides.get(key, {})
        if hasattr(artist, "patches"):
            for bar in artist.patches:
                for name, prop in (("color", "facecolor"), ("bar_edge", "edgecolor"), ("bar_hatch", "hatch"),
                                   ("bar_alpha", "alpha"), ("visible", "visible")):
                    if name in patch:
                        getattr(bar, "set_"+prop)(patch[name])
        else:
            for name, prop in (("color", "color"), ("line_width", "linewidth"), ("line_style", "linestyle"),
                               ("line_alpha", "alpha"), ("marker", "marker"), ("marker_size", "markersize"),
                               ("marker_face", "markerfacecolor"), ("marker_edge", "markeredgecolor"),
                               ("marker_edge_width", "markeredgewidth"), ("visible", "visible")):
                if name in patch and patch[name] not in ("auto", "preserve"):
                    getattr(artist, "set_"+prop)(patch[name])


def figure_size(settings):
    width, height = float(settings["width_cm"]), float(settings["height_cm"])
    for value in (width, height, settings["dpi"]):
        if not np.isfinite(value) or value <= 0:
            raise ValueError(tr("圖寬、高與 DPI 必須為正數。"))
    options = validate_options(settings.get("figure_options", {}))
    if options["orientation"] == "landscape":
        width, height = max(width, height), min(width, height)
    elif options["orientation"] == "portrait":
        width, height = min(width, height), max(width, height)
    return width/2.54, height/2.54


def _format_axis(ax, which, options, categorical=False):
    axis = getattr(ax, which+"axis")
    scale = options[which+"scale"]
    if categorical and scale != "linear":
        raise ValueError(tr("類別 Condition 軸僅支援線性排列；數值軸才可選對數尺度。"))
    # Setting the scale recreates locators/formatters. Categorical Condition
    # axes already have fixed positions and labels, which must be preserved.
    if not categorical:
        getattr(ax, "set_"+which+"scale")(scale)
    limits = getattr(ax, "get_"+which+"lim")()
    if scale == "log" and min(limits) <= 0:
        raise ValueError(tr("對數座標的顯示範圍必須大於零。"))
    if not categorical:
        special = options["special_"+which+"_ticks"]
        step = options[which+"_major_step"]
        if special:
            getattr(ax, "set_"+which+"ticks")(special)
        elif scale == "linear":
            axis.set_major_locator(MultipleLocator(step) if step > 0 else MaxNLocator(options[which+"_major_count"]))
        if options["minor_ticks"]:
            axis.set_minor_locator(LogLocator(base=10, subs="auto") if scale == "log" else AutoMinorLocator(options["minor_divisions"]))
        else:
            axis.set_minor_locator(NullLocator())
        fmt = options[which+"_format"]
        if fmt == "fixed":
            axis.set_major_formatter(FormatStrFormatter(f"%.{options['decimals']}f"))
        elif fmt == "scientific":
            formatter = ScalarFormatter(useMathText=True, useOffset=False)
            formatter.set_powerlimits((0, 0))
            axis.set_major_formatter(formatter)
        elif fmt == "plain":
            formatter = ScalarFormatter(useOffset=False)
            formatter.set_scientific(False)
            axis.set_major_formatter(formatter)
    reverse = options["reverse_"+which]
    if getattr(ax, which+"axis_inverted")() != reverse:
        getattr(ax, "invert_"+which+"axis")()
    ax.tick_params(axis=which, labelrotation=options[which+"_rotation"])


def apply_figure_style(figure, settings):
    """Apply all shared formatting after data have been drawn, preserving their values."""
    if "figure_options" not in settings:
        return  # Old projects preserve their established rendering.
    options = validate_options(settings["figure_options"])
    figure.set_facecolor(options["page_color"])
    axes = list(figure.axes)
    for index, ax in enumerate(axes, 1):
        overrides = options["layers"].get(layer_key(ax, index), options["layers"].get(str(index), {}))
        local = options | overrides.get("options", {})
        ax.set_visible(overrides.get("visible", True))
        ax.set_facecolor(local["layer_color"])
        if "position" in overrides:
            ax.set_position(overrides["position"])
        for key in ("xlabel", "ylabel", "title", "xlim", "ylim"):
            if key in overrides:
                getattr(ax, "set_"+key)(overrides[key])
        if settings.get("ylabel") and len(axes) == 1:
            ax.set_ylabel(settings["ylabel"])
        if settings.get("ymin") is not None or settings.get("ymax") is not None:
            if len(axes) == 1:
                ax.set_ylim(settings.get("ymin"), settings.get("ymax"))
        categorical = bool(getattr(ax, "_pl_categorical", False))
        if settings.get("xmin") is not None or settings.get("xmax") is not None:
            ax.set_xlim(settings.get("xmin"), settings.get("xmax"))
        _format_axis(ax, "x", local, categorical)
        _format_axis(ax, "y", local)
        for spine in ax.spines.values():
            spine.set_color(local["axis_color"])
            spine.set_linewidth(local["axis_width"])
        ax.spines["top"].set_visible(local["top_axis"])
        ax.spines["right"].set_visible(local["right_axis"])
        ax.tick_params(which="major", direction=local["tick_direction"], length=local["major_length"],
                       width=local["tick_width"], colors=local["axis_color"], labelsize=local["tick_size"],
                       top=local["top_axis"], right=local["right_axis"])
        ax.tick_params(which="minor", direction=local["tick_direction"], length=local["minor_length"],
                       width=local["tick_width"], colors=local["axis_color"],
                       top=local["top_axis"], right=local["right_axis"])
        for text, size in ((ax.xaxis.label, local["x_label_size"]), (ax.yaxis.label, local["y_label_size"]),
                           (ax.title, local["title_size"])):
            text.set_fontsize(size)
            text.set_fontweight(local["font_weight"])
            text.set_color(local["text_color"])
        ax.xaxis.labelpad = ax.yaxis.labelpad = local["label_pad"]
        for text in [*ax.get_xticklabels(), *ax.get_yticklabels(), ax.xaxis.label, ax.yaxis.label, ax.title]:
            text.set_fontfamily([settings.get("font", "Arial"), "Microsoft JhengHei"])
        ax.grid(False, which="both")
        if settings.get("grid", False):
            ax.grid(True, which="major", color=local["grid_color"], linewidth=local["grid_width"],
                    linestyle=local["grid_style"], alpha=local["grid_alpha"])
        if local["minor_grid"]:
            ax.grid(True, which="minor", color=local["grid_color"], linewidth=local["grid_width"]*.7,
                    linestyle=local["grid_style"], alpha=local["grid_alpha"]*.7)
        palette = colormaps.get_cmap(local["palette"]) if local["palette"] != "preserve" else None
        # Exclude errorbar cap artists from global series styling.
        series = [line for line in ax.lines if line.get_label() != "_nolegend_"]
        for j, line in enumerate(series):
            line.set_linewidth(settings.get("line_width", line.get_linewidth()))
            line.set_alpha(local["line_alpha"])
            if palette is not None:
                line.set_color(palette(j % palette.N))
            if local["line_style"] != "preserve":
                line.set_linestyle(local["line_style"])
            if local["marker"] != "preserve":
                line.set_marker(local["marker"])
            line.set_markersize(local["marker_size"])
            line.set_markeredgewidth(local["marker_edge_width"])
            for kind in ("face", "edge"):
                color = local["marker_"+kind]
                if color != "auto":
                    getattr(line, "set_marker"+kind+"color")(color)
        for container in ax.containers:
            if hasattr(container, "has_yerr"):
                _, caps, bars = container.lines
                for cap in caps:
                    cap.set_markersize(2*local["error_capsize"])
                    cap.set_markeredgewidth(local["error_width"])
                for bar in bars:
                    bar.set_linewidth(local["error_width"])
            elif hasattr(container, "patches"):
                for j, patch in enumerate(container.patches):
                    patch.set_edgecolor(local["bar_edge"])
                    patch.set_hatch(local["bar_hatch"])
                    patch.set_alpha(local["bar_alpha"])
                    if palette is not None:
                        patch.set_facecolor(palette(j % palette.N))
        _apply_plot_details(ax, overrides.get("plots", {}))
        _apply_four_axes(ax, overrides.get("axes", {}), local, settings, categorical)
        handles, labels = ax.get_legend_handles_labels()
        old = ax.get_legend()
        if old:
            old.remove()
        if overrides.get("legend", settings.get("legend", True)) and handles:
            if local["legend_reverse"]:
                handles, labels = handles[::-1], labels[::-1]
            kwargs = {"loc": local["legend_loc"], "ncol": local["legend_columns"],
                      "frameon": local["legend_frame"], "framealpha": local["legend_alpha"],
                      "facecolor": local["legend_face"], "edgecolor": local["legend_edge"],
                      "labelspacing": local["legend_spacing"], "title": local["legend_title"],
                      "prop": {"family": settings.get("font", "Arial"), "size": local["legend_size"]}}
            if local["legend_outside"]:
                kwargs.update(loc="upper left", bbox_to_anchor=(1.02, 1))
            ax.legend(handles, labels, **kwargs)
        if local["panel_labels"]:
            label = (str(index) if local["panel_label_style"] == "1" else
                     (string.ascii_uppercase if local["panel_label_style"] == "A" else string.ascii_lowercase)[(index-1)%26])
            ax.text(local["panel_label_x"], local["panel_label_y"], f"({label})", transform=ax.transAxes,
                    fontsize=local["title_size"], fontweight="bold", va="bottom")
        for entry in local["annotations"]:
            if int(entry.get("layer", 1)) != index:
                continue
            xy = entry.get("xy", [.05, .95])
            transform = ax.transData if entry.get("coords") == "data" else ax.transAxes
            if "to" in entry:
                ax.annotate(entry.get("text", ""), xy=entry["to"], xytext=xy,
                            xycoords="data" if entry.get("coords") == "data" else "axes fraction",
                            arrowprops={"arrowstyle": "->", "color": entry.get("color", "black")},
                            color=entry.get("color", "black"), fontsize=entry.get("size", local["title_size"]))
            else:
                ax.text(*xy, entry.get("text", ""), transform=transform, color=entry.get("color", "black"),
                        fontsize=entry.get("size", local["title_size"]), fontfamily=settings.get("font", "Arial"))
        for shape in local["shapes"]:
            if int(shape.get("layer", 1)) != index:
                continue
            transform = ax.transData if shape.get("coords") == "data" else ax.transAxes
            kind = Rectangle if shape.get("type", "rectangle") == "rectangle" else Ellipse
            patch = kind(shape.get("xy", [.2, .2]), shape.get("width", .2), shape.get("height", .2),
                         transform=transform, facecolor=shape.get("face", "none"), edgecolor=shape.get("edge", "black"),
                         alpha=shape.get("alpha", .5), linewidth=shape.get("width_pt", 1))
            ax.add_patch(patch)
        if local["inset"] and local["inset_layer"] == index:
            inset = ax.inset_axes(local["inset_box"])
            for line in series:
                inset.plot(line.get_xdata(), line.get_ydata(), color=line.get_color(),
                           linestyle=line.get_linestyle(), linewidth=line.get_linewidth())
            if local["inset_xlim"]:
                inset.set_xlim(local["inset_xlim"])
            if local["inset_ylim"]:
                inset.set_ylim(local["inset_ylim"])
            inset.tick_params(labelsize=max(5, local["tick_size"]-2), direction="in")
            if local["inset_connectors"]:
                ax.indicate_inset_zoom(inset, edgecolor=local["axis_color"])
    manual = options["layout_mode"] == "manual" or any("position" in v for v in options["layers"].values())
    if manual:
        figure.set_layout_engine(None)
        if not any("position" in v for v in options["layers"].values()):
            figure.subplots_adjust(left=options["left"], right=options["right"], bottom=options["bottom"],
                                   top=options["top"], hspace=options["hspace"], wspace=options["wspace"])
    else:
        figure.set_layout_engine("tight", pad=1.3, h_pad=options["hspace"]*3, w_pad=options["wspace"]*3)


def save_figure(figure, path, settings):
    options = validate_options(settings.get("figure_options", {}))
    kwargs = {"dpi": settings["dpi"], "facecolor": options["page_color"],
              "transparent": options["transparent"], "pad_inches": options["export_pad"]}
    if options["tight_export"]:
        kwargs["bbox_inches"] = "tight"
    if Path(path).suffix.lower() in (".jpg", ".jpeg"):
        kwargs["transparent"] = False
        kwargs["pil_kwargs"] = {"quality": options["jpeg_quality"]}
    figure.savefig(path, **kwargs)
