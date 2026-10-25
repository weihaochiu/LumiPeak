from __future__ import annotations

from .i18n import tr

import textwrap

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .data import FitConfig, intensity_label, transformed
from .figure_style import apply_figure_style, figure_size, save_figure
from .chart_settings import chart_settings

DEFAULT_STYLE = {"width_cm": 16.0, "height_cm": 11.0, "dpi": 300,
                 "font": "Arial", "font_size": 11.0, "line_width": 1.6,
                 "raw": True, "fit": True, "components": False, "background": False,
                 "residual": False, "legend": True, "grid": False, "logy": False,
                 "normalize": False, "offset": 0.0, "title": "", "xlabel": "", "ylabel": "",
                 "xmin": None, "xmax": None, "ymin": None, "ymax": None,
                 "styles": {}, "chart_styles": {}}
COLORS = ["#1868b2", "#e76f51", "#238b75", "#9163b6", "#d39b20", "#d14b78", "#557384"]


def draw_spectra(figure: Figure, spectra, settings=None, analysis=False, preview=None):
    style = DEFAULT_STYLE | (settings or {})
    figure.clear()
    residual = analysis or style["residual"]
    if residual:
        grid = figure.add_gridspec(2, 1, height_ratios=(4, 1), hspace=0.08)
        ax = figure.add_subplot(grid[0])
        rax = figure.add_subplot(grid[1], sharex=ax)
        ax.tick_params(labelbottom=False)
        rax.axhline(0, color="#8b97a8", lw=0.8)
        rax.lines[-1]._pl_reference = True
        rax.set_ylabel("Residual")
    else:
        ax, rax = figure.add_subplot(111), None
    if len(spectra) == 1:
        ax._pl_style_key = "spectrum:"+spectra[0].id
        if rax is not None:
            rax._pl_style_key = "spectrum:"+spectra[0].id+":residual"
    configs = [FitConfig(**s.result["config"]) if s.result else s.config for s in spectra]
    signatures = {(c.domain, c.jacobian, c.normalization) for c in configs}
    if len(signatures) > 1:
        raise ValueError(tr("所選光譜的擬合座標／Jacobian／歸一化不同，請先統一設定後再疊圖。"))
    for i, (spectrum, config) in enumerate(zip(spectra, configs)):
        x, y = transformed(spectrum, config, crop=False)
        line_style = style["styles"].get(spectrum.id, {})
        color = line_style.get("color", COLORS[i % len(COLORS)])
        ls = line_style.get("linestyle", "-")
        scale = float(np.max(y)) if style["normalize"] else 1.0
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError(tr('{0} 的最大強度必須大於零才能歸一化。').format(spectrum.name, ''))
        offset = i*style["offset"]
        has_fit = spectrum.result is not None
        if style["raw"] or analysis:
            ax.plot(x, y/scale+offset, color=color, lw=style["line_width"]*(0.65 if analysis else 1),
                    alpha=0.62 if analysis and has_fit else 1.0,
                    ls=ls, label=spectrum.name+" (raw)" if analysis and has_fit else spectrum.name)
            ax.lines[-1]._pl_style_key = spectrum.id+":raw"
        if has_fit:
            result = spectrum.result
            xx = np.asarray(result["x"])
            # Insert NaNs at masked intervals so a line never bridges excluded data.
            def masked(values):
                values = np.asarray(values, dtype=float).copy()
                for lo, hi in config.excluded:
                    at = np.searchsorted(xx, hi, side="right")
                    if 0 < at < len(xx):
                        values[at] = np.nan
                return values
            if style["fit"] or analysis:
                ax.plot(xx, masked(result["fitted"])/scale+offset, color=color,
                        lw=style["line_width"], ls="-" if analysis else ls,
                        label=spectrum.name+" (fit)" if style["raw"] or analysis else spectrum.name)
                ax.lines[-1]._pl_style_key = spectrum.id+":fit"
            if style["components"] and len(result["peaks"]) > 1:
                for key, values in result["components"].items():
                    if key.startswith("p"):
                        ax.plot(xx, masked(values)/scale+offset, color=color, ls="--", lw=1,
                                alpha=0.75, label=f"{spectrum.name} {key.rstrip('_')}")
                        ax.lines[-1]._pl_style_key = spectrum.id+":"+key.rstrip("_")
            if style["background"] and "b_" in result["components"]:
                ax.plot(xx, masked(result["components"]["b_"])/scale+offset,
                        color=color, lw=1, ls=":", label=spectrum.name+" background")
                ax.lines[-1]._pl_style_key = spectrum.id+":background"
            if rax is not None:
                rax.plot(xx, masked(result["residual"])/scale, color=color, lw=0.8)
                rax.lines[-1]._pl_style_key = spectrum.id+":residual"
        if preview is not None and analysis:
            xx, yy = preview
            ax.plot(xx, yy, color="#b13265", ls="--", lw=1.3, label="Initial model")
    config = configs[0] if configs else FitConfig()
    xlabel = style["xlabel"] or ("Wavelength (nm)" if config.domain == "nm" else "Photon energy (eV)")
    ylabel = style["ylabel"] or ("Normalized PL (a.u.)" if style["normalize"] else intensity_label(config))
    if style["offset"]:
        ylabel += " + offset"
    ax.set_ylabel(ylabel)
    (rax or ax).set_xlabel(xlabel)
    ax.set_title(style["title"], pad=12)
    if style["logy"]:
        ax.set_yscale("log")
    for axis in (ax, rax):
        if axis is None:
            continue
        axis.tick_params(direction="in", top=True, right=True)
        if style["grid"]:
            axis.grid(True, alpha=0.15)
        else:
            axis.grid(False)
        for label in [axis.xaxis.label, axis.yaxis.label, axis.title, *axis.get_xticklabels(), *axis.get_yticklabels()]:
            label.set_fontfamily(style["font"])
            label.set_fontsize(style["font_size"])
        for spine in axis.spines.values():
            spine.set_linewidth(1)
    for lo, hi, method in (("xmin", "xmax", ax.set_xlim), ("ymin", "ymax", ax.set_ylim)):
        if style[lo] is not None or style[hi] is not None:
            method(style[lo], style[hi])
    if style["legend"] and ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, prop={"family": style["font"], "size": style["font_size"]*0.85})
    figure.subplots_adjust(left=0.15, right=0.96, bottom=0.15, top=0.90)
    if not spectra:
        ax.text(0.5, 0.5, "Import spectra to begin", transform=ax.transAxes,
                ha="center", va="center", color="#8894a3", fontsize=14)
    apply_figure_style(figure, style)
    return ax, rax


def _add_fit_summary(figure, ax, spectrum, style):
    """Place saved fit values in the least occupied part of an individual plot."""
    lines = textwrap.wrap(spectrum.name, width=40) or [spectrum.name]
    result = spectrum.result
    if result:
        unit = result["config"]["domain"]

        def value(number, precision=".2f"):
            return format(number, precision) if number is not None and np.isfinite(number) else "N/A"

        for peak in result["peaks"]:
            if len(result["peaks"]) > 1:
                lines.append(f"Peak {peak['peak']}")
            position_error = peak.get("maximum_position_stderr")
            width_error = peak.get("fwhm_stderr")
            # Older projects retain the lmfit parameter errors even though the
            # derived peak-error fields were not stored in their peak table.
            if peak["model"] not in ("SkewedGaussian", "SkewedVoigt"):
                if "maximum_position_stderr" not in peak:
                    position_error = peak.get("center_stderr")
                if "fwhm_stderr" not in peak and peak.get("fwhm") is not None:
                    width_error = next((p["stderr"] for p in result["parameters"]
                                        if p["parameter"] == f"p{peak['peak']}_fwhm"), None)
            lines.append(f"xc = {value(peak.get('maximum_position'))} ± {value(position_error)} {unit}")
            lines.append(f"w = {value(peak.get('fwhm'))} ± {value(width_error)} {unit}")
        lines.append(f"R2 = {value(result['metrics'].get('r2'), '.3f')}")
        if not result["success"]:
            lines.append("Fit not converged")
    else:
        lines.append("Not fitted")

    previous_canvas = figure.canvas
    canvas = FigureCanvasAgg(figure)
    canvas.draw()  # Resolve layout, automatic legend position and text dimensions.
    renderer = canvas.get_renderer()
    if hasattr(previous_canvas, "get_renderer"):
        figure.set_canvas(previous_canvas)
    obstacles = [text.get_window_extent(renderer) for text in ax.texts if text.get_visible()]
    if ax.get_legend() is not None:
        obstacles.append(ax.get_legend().get_window_extent(renderer))
    obstacles.extend(child.get_window_extent(renderer) for child in ax.child_axes if not getattr(child, "_pl_axis_side", None))
    label = ax.text(.03, .97, "\n".join(lines), transform=ax.transAxes,
                    ha="left", va="top", fontfamily=style["font"],
                    fontsize=style["font_size"] * .85, parse_math=False,
                    color=ax.yaxis.label.get_color(), zorder=10,
                    bbox={"facecolor": ax.get_facecolor(), "edgecolor": "none", "alpha": .9, "pad": 4})
    # Keep long names and multi-peak summaries inside the plotting area.
    while label.get_fontsize() > 6:
        box = label.get_window_extent(renderer)
        if box.width <= ax.bbox.width * .94 and box.height <= ax.bbox.height * .94:
            break
        label.set_fontsize(max(6, label.get_fontsize() - .5))
    curves = [line.get_transform().transform_path(line.get_path()) for line in ax.lines if line.get_visible()]
    candidates = [(x, y, ha, va) for y, va in ((.97, "top"), (.03, "bottom"), (.5, "center"))
                  for x, ha in ((.03, "left"), (.97, "right"), (.5, "center"))]
    best, best_score = candidates[0], float("inf")
    for candidate in candidates:
        x, y, ha, va = candidate
        label.set_position((x, y))
        label.set_horizontalalignment(ha)
        label.set_verticalalignment(va)
        box = label.get_window_extent(renderer).padded(5)
        score = 1000 * sum(box.overlaps(obstacle) for obstacle in obstacles)
        for curve in curves:
            points = curve.vertices
            score += 100 * curve.intersects_bbox(box, filled=False)
            score += np.count_nonzero((points[:, 0] >= box.x0) & (points[:, 0] <= box.x1)
                                      & (points[:, 1] >= box.y0) & (points[:, 1] <= box.y1))
        if score < best_score:
            best, best_score = candidate, score
    x, y, ha, va = best
    label.set_position((x, y))
    label.set_horizontalalignment(ha)
    label.set_verticalalignment(va)
    return label


def export_figure(path, spectra, settings):
    if not spectra:
        raise ValueError(tr("請先勾選要作圖的資料。"))
    style = DEFAULT_STYLE | settings
    if len(spectra) == 1:
        style = chart_settings(style, "spectrum:"+spectra[0].id)
    for name in ("width_cm", "height_cm", "dpi", "font_size", "line_width"):
        if not np.isfinite(style[name]) or style[name] <= 0:
            raise ValueError(tr('{0} 必須為正數。').format(name, ''))
    figure = Figure(figsize=figure_size(style), dpi=style["dpi"])
    ax, _ = draw_spectra(figure, spectra, style)
    if style.get("fit_summary") and len(spectra) == 1:
        _add_fit_summary(figure, ax, spectra[0], style)
    # No tight bounding box: the exported physical size matches the user's setting.
    save_figure(figure, path, style)
