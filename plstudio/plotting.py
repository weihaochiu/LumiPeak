from __future__ import annotations

from .i18n import tr

import numpy as np
from matplotlib.figure import Figure

from .data import FitConfig, intensity_label, transformed
from .figure_style import apply_figure_style, figure_size, save_figure

DEFAULT_STYLE = {"width_cm": 16.0, "height_cm": 11.0, "dpi": 300,
                 "font": "Arial", "font_size": 11.0, "line_width": 1.6,
                 "raw": True, "fit": True, "components": False, "background": False,
                 "residual": False, "legend": True, "grid": False, "logy": False,
                 "normalize": False, "offset": 0.0, "title": "", "xlabel": "", "ylabel": "",
                 "xmin": None, "xmax": None, "ymin": None, "ymax": None,
                 "styles": {}}
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
        rax.set_ylabel("Residual")
    else:
        ax, rax = figure.add_subplot(111), None
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
            if style["components"] and len(result["peaks"]) > 1:
                for key, values in result["components"].items():
                    if key.startswith("p"):
                        ax.plot(xx, masked(values)/scale+offset, color=color, ls="--", lw=1,
                                alpha=0.75, label=f"{spectrum.name} {key.rstrip('_')}")
            if style["background"] and "b_" in result["components"]:
                ax.plot(xx, masked(result["components"]["b_"])/scale+offset,
                        color=color, lw=1, ls=":", label=spectrum.name+" background")
            if rax is not None:
                rax.plot(xx, masked(result["residual"])/scale, color=color, lw=0.8)
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


def export_figure(path, spectra, settings):
    if not spectra:
        raise ValueError(tr("請先勾選要作圖的資料。"))
    style = DEFAULT_STYLE | settings
    for name in ("width_cm", "height_cm", "dpi", "font_size", "line_width"):
        if not np.isfinite(style[name]) or style[name] <= 0:
            raise ValueError(tr('{0} 必須為正數。').format(name, ''))
    figure = Figure(figsize=figure_size(style), dpi=style["dpi"])
    draw_spectra(figure, spectra, style)
    # No tight bounding box: the exported physical size matches the user's setting.
    save_figure(figure, path, style)
