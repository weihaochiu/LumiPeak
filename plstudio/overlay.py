"""Wavelength overlays of the original spectra, independent of fitting transforms."""
from __future__ import annotations

from .i18n import tr

import copy
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from .data import FitConfig
from .plotting import COLORS, DEFAULT_STYLE
from .figure_style import apply_figure_style, figure_size, save_figure

DEFAULT_OVERLAY = {"intensity": "both", "export_mode": "separate", "width_cm": 17.8, "height_cm": 12.0,
                   "dpi": 300, "font_size": 11.0, "line_width": 1.6,
                   "legend": True, "grid": False, "title": "", "xmin": None, "xmax": None}


def overlay_inputs(spectra, settings=None):
    settings = DEFAULT_OVERLAY | (settings or {})
    if settings["intensity"] not in ("raw", "normalized", "both"):
        raise ValueError(tr("未知的疊圖強度模式。"))
    selected = []
    for s in spectra:
        if s.plot:
            source = copy.copy(s)
            source.result = None
            source.config = FitConfig()  # Original nm / Counts, regardless of fit settings.
            selected.append(source)
    normalized = settings["intensity"] == "normalized"
    style = DEFAULT_STYLE | settings | {
        "normalize": normalized, "raw": True, "fit": False, "components": False,
        "background": False, "residual": False, "offset": 0,
        "xlabel": "Wavelength (nm)",
        "ylabel": "Normalized PL intensity (I / Imax)" if normalized else "PL intensity (Counts)",
    }
    return selected, style


def draw_overlay(figure, spectra, settings=None):
    settings = DEFAULT_OVERLAY | (settings or {})
    selected, style = overlay_inputs(spectra, settings)
    modes = ["raw", "normalized"] if settings["intensity"] == "both" else [settings["intensity"]]
    if "normalized" in modes:
        for s in selected:
            if not np.isfinite(s.y.max()) or s.y.max() <= 0:
                raise ValueError(tr('{0} 的最大強度必須大於零才能歸一化。').format(s.name, ''))
    figure.clear()
    axes = []
    for index, mode in enumerate(modes, 1):
        columns = min(len(modes), max(1, int(settings.get("figure_options", {}).get("columns", 1)) or 1))
        ax = figure.add_subplot(int(np.ceil(len(modes)/columns)), columns, index, sharex=axes[0] if axes else None)
        axes.append(ax)
        for i, s in enumerate(selected):
            y = s.y/s.y.max() if mode == "normalized" else s.y
            line_style = style["styles"].get(s.id, {})
            ax.plot(s.x, y, color=line_style.get("color", COLORS[i % len(COLORS)]),
                    linestyle=line_style.get("linestyle", "-"), linewidth=style["line_width"], label=s.name)
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Normalized intensity (I / Imax)" if mode == "normalized" else "PL intensity (Counts)")
        title = "Normalized intensity" if mode == "normalized" else "Original intensity"
        ax.set_title((style["title"]+" — " if style["title"] else "")+title)
        ax.tick_params(direction="in", top=True, right=True)
        if style["grid"]:
            ax.grid(True, alpha=.15)
        if style["xmin"] is not None or style["xmax"] is not None:
            ax.set_xlim(style["xmin"], style["xmax"])
        for label in [ax.xaxis.label, ax.yaxis.label, ax.title, *ax.get_xticklabels(), *ax.get_yticklabels()]:
            label.set_fontfamily(style["font"])
            label.set_fontsize(style["font_size"])
        if style["legend"] and selected:
            ax.legend(frameon=False, prop={"family": style["font"], "size": style["font_size"]*.85})
        if not selected:
            ax.text(.5, .5, "Select spectra in the left panel", ha="center", va="center", transform=ax.transAxes,
                    color="#8292a3")
    figure.set_layout_engine("tight", pad=1.3, h_pad=1.2)
    apply_figure_style(figure, settings)
    return axes[0], axes[1] if len(axes) > 1 else None


def export_overlay(path, spectra, settings=None):
    settings = DEFAULT_OVERLAY | (settings or {})
    if not any(s.plot for s in spectra):
        raise ValueError(tr("請先勾選要疊圖的光譜。"))
    for key in ("width_cm", "height_cm", "dpi", "font_size", "line_width"):
        if not np.isfinite(settings[key]) or settings[key] <= 0:
            raise ValueError(tr('{0} 必須為正數。').format(key, ''))
    figure = Figure(figsize=figure_size(settings), dpi=settings["dpi"])
    draw_overlay(figure, spectra, settings)
    save_figure(figure, path, settings)


def export_overlay_files(path, spectra, settings=None):
    settings = DEFAULT_OVERLAY | (settings or {})
    mode = settings["export_mode"]
    if mode not in ("raw", "normalized", "both", "separate", "current"):
        raise ValueError(tr("未知的疊圖輸出模式。"))
    if mode != "separate":
        view = settings["intensity"] if mode == "current" else mode
        export_overlay(path, spectra, settings | {"intensity": view})
        return [Path(path)]
    # Check both views before creating files, so invalid normalization cannot
    # leave only the first file of a requested pair.
    if not any(s.plot for s in spectra):
        raise ValueError(tr("請先勾選要疊圖的光譜。"))
    draw_overlay(Figure(), spectra, settings | {"intensity": "both"})
    path = Path(path)
    paths = [path.with_name(path.stem+"_intensity"+path.suffix),
             path.with_name(path.stem+"_normalized"+path.suffix)]
    for output, view in zip(paths, ("raw", "normalized")):
        export_overlay(output, spectra, settings | {"intensity": view})
    return paths
