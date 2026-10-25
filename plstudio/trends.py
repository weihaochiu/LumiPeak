"""Plot fitted parameters versus user-defined conditions, without averaging."""
from __future__ import annotations

from .i18n import tr

import math
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from .data import FitConfig
from .figure_style import apply_figure_style, figure_size, save_figure
from .chart_settings import chart_settings

# metric: UI label, figure label, source, value key, standard-error key, dimensional class
METRICS = {
    "center": ("模型中心（Model center）", "Model center", "peak", "center", "center_stderr", "x"),
    "maximum_position": ("峰頂位置（Peak position）", "Peak position", "peak", "maximum_position", None, "x"),
    "fwhm": ("Peak FWHM", "Peak FWHM", "peak", "fwhm", None, "x"),
    "area_in_range": ("Peak area（區間積分）", "Peak area in fit range", "peak", "area_in_range", None, "area"),
    "amplitude": ("Peak area（模型面積參數）", "Peak model area", "peak", "amplitude", "amplitude_stderr", "area"),
    "height": ("Peak intensity（扣背景峰高）", "Peak intensity", "peak", "height", None, "y"),
    "area_fraction": ("分峰面積比例", "Peak area fraction", "peak", "area_fraction", None, "fraction"),
    "rmse": ("RMSE", "Fit RMSE", "metrics", "rmse", None, "y"),
    "r2": ("R²", "R²", "metrics", "r2", None, "fraction"),
    "centroid_positive_background_subtracted": (
        "光譜重心（扣背景、取非負值）", "Spectral centroid", "metrics",
        "centroid_positive_background_subtracted", None, "x"),
    "measured_area_background_subtracted": (
        "實測積分（扣背景）", "Measured PL area", "metrics",
        "measured_area_background_subtracted", None, "area"),
}

DEFAULT_TRENDS = {
    "metrics": ["maximum_position", "fwhm", "area_in_range", "height"], "view": "overview", "peak": 1,
    "x_mode": "category", "sort_numeric": True, "xlabel": "Condition",
    "connect": False, "errorbars": True, "annotate": False, "include_failed": False,
    "width_cm": 20.0, "height_cm": 14.0, "dpi": 300, "font_size": 10.0,
    "plot_type": "dot", "bar_width": .65,
}
PALETTE = ["#1868b2", "#e76f51", "#238b75", "#9163b6", "#d39b20"]

SYMMETRIC_MODELS = {"Gaussian", "Lorentzian", "Voigt", "PseudoVoigt"}
ASYMMETRIC_MODELS = {"SkewedGaussian", "SkewedVoigt"}


def trend_peak_context(spectra, peak_number, include_failed=False):
    context = []
    for spectrum in spectra:
        if not spectrum.plot:
            continue
        if spectrum.result is not None:
            result = spectrum.result
            if not result["success"] and not include_failed:
                continue
            peak = next((p for p in result["peaks"] if p["peak"] == peak_number), None)
            if peak is not None:
                context.append((peak["model"], len(result["peaks"])))
        elif 1 <= peak_number <= len(spectrum.config.peaks):
            context.append((spectrum.config.peaks[peak_number - 1], len(spectrum.config.peaks)))
    return context


def position_choices(spectra, peak_number, include_failed=False):
    """Describe position selectors using the same saved peaks as the trend.

    Unfitted spectra use their working configuration. Missing peaks and excluded
    failed fits cannot enable a duplicate selector for the plotted results.
    """
    models = {model for model, count in trend_peak_context(spectra, peak_number, include_failed)}
    enabled = bool(models & ASYMMETRIC_MODELS)
    mixed = enabled and bool(models & SYMMETRIC_MODELS)
    label = (tr("模型中心（混用峰形；非對稱峰可與峰頂不同）") if mixed else
             tr("模型中心（非對稱模型的位置參數）") if enabled else
             tr("模型中心（對稱峰與峰頂相同，停用）") if models else
             tr("模型中心（僅非對稱模型可選）"))
    tip = (tr("依選取資料的已保存擬合結果及 Peak 編號判斷；未擬合資料使用目前設定。\n"
           "對稱峰只需選峰頂位置；非對稱峰可另外比較模型中心，模型中心不是光譜重心。"))
    return enabled, label, tip


def metric_unit(key, config):
    dimension = METRICS[key][5]
    if dimension == "x":
        return config.domain
    if dimension == "fraction":
        return "1"
    if config.normalization != "none":
        y = "a.u."
    elif config.domain == "eV" and config.jacobian:
        y = "converted units/eV"
    else:
        y = "Counts"
    return f"{y} · {config.domain}" if dimension == "area" else y


def selected_metrics(settings, overview=False):
    settings = DEFAULT_TRENDS | settings
    keys = settings["metrics"] if overview or settings["view"] == "overview" else [settings["view"]]
    keys = list(dict.fromkeys(keys))
    if not keys or any(k not in METRICS for k in keys):
        raise ValueError(tr("請至少勾選一個有效的趨勢指標。"))
    return keys


def prepare_trends(spectra, settings=None, overview=False):
    settings = DEFAULT_TRENDS | (settings or {})
    keys = selected_metrics(settings, overview)
    peak_number = int(settings["peak"])
    if peak_number < 1:
        raise ValueError(tr("分峰編號必須大於零。"))
    eligible = [s for s in spectra if s.plot]
    labels = [s.condition.strip() or s.name for s in eligible]
    numeric = []
    for label in labels:
        try:
            value = float(label)
            numeric.append(value if np.isfinite(value) else None)
        except (TypeError, ValueError):
            numeric.append(None)
    mode = settings["x_mode"]
    if mode not in ("category", "numeric", "auto"):
        raise ValueError(tr("未知的 Condition 座標模式。"))
    if mode == "auto":
        mode = "numeric" if labels and all(v is not None for v in numeric) else "category"
    if mode == "numeric" and any(v is None for v in numeric):
        invalid = [label for label, value in zip(labels, numeric) if value is None]
        raise ValueError(tr("數值 Condition 需為有限數字（單位請填在 X 軸標籤）：")+", ".join(invalid[:5]))
    categories = list(dict.fromkeys(labels))
    category_positions = {label: i for i, label in enumerate(categories)}
    rows, messages = [], []
    for s, label, numeric_value in zip(eligible, labels, numeric):
        result = s.result
        common_reason = ""
        if not result:
            common_reason = tr("尚未擬合")
        elif not result["success"] and not settings["include_failed"]:
            common_reason = tr("擬合未收斂，已排除")
        peak = next((p for p in result["peaks"] if p["peak"] == peak_number), None) if result else None
        config = FitConfig(**result["config"]) if result else None
        x = numeric_value if mode == "numeric" else category_positions[label]
        for key in keys:
            definition = METRICS[key]
            reason = common_reason
            source = peak if definition[2] == "peak" else (result["metrics"] if result else None)
            if not reason and source is None:
                reason = tr('沒有 Peak {1}').format('', peak_number)
            if not reason and key == "area_fraction" and len(result["peaks"]) < 2:
                reason = tr("單峰擬合不適用分峰面積比例")
            value = source.get(definition[3]) if source is not None else None
            if not reason and (value is None or not np.isfinite(value)):
                reason = tr("此數值無法取得；請檢查擬合區間／遮罩／結果")
            stderr = source.get(definition[4]) if source is not None and definition[4] else None
            if stderr is not None and (not np.isfinite(stderr) or stderr < 0):
                stderr = None
            rows.append({"spectrum_id": s.id, "name": s.name, "filename": s.filename,
                         "condition": label, "condition_stored": s.condition,
                         "x": x, "peak": peak_number if definition[2] == "peak" else None,
                         "metric": key, "metric_label": tr(definition[0]),
                         "value": float(value) if not reason else None,
                         "stderr": float(stderr) if stderr is not None and not reason else None,
                         "unit": metric_unit(key, config) if config else "",
                         "status": reason or (tr("未收斂（使用者納入）") if not result["success"] else "OK"),
                         "valid": not bool(reason), "fit_id": result["id"] if result else "",
                         "fit_config": result["config"] if result else None})
            if reason:
                messages.append(f"{s.name} / {tr(definition[0])}：{reason}")
    # Refuse to silently combine physically different axes or intensity transforms.
    for key in keys:
        valid = [r for r in rows if r["metric"] == key and r["valid"]]
        dimension = METRICS[key][5]
        signatures = set()
        for row in valid:
            cfg = row["fit_config"]
            if dimension == "fraction":
                signature = ()
            elif dimension == "x":
                signature = (cfg["domain"], cfg["jacobian"])
            else:
                signature = (cfg["domain"], cfg["jacobian"], cfg["normalization"])
            signatures.add(signature)
        if len(signatures) > 1:
            raise ValueError(tr('{0} 的座標或強度處理不一致，請選用可比較的結果。').format(tr(METRICS[key][0]), ''))
        if dimension == "area" and key in ("area_in_range", "measured_area_background_subtracted"):
            ranges = {(r["fit_config"]["xmin"], r["fit_config"]["xmax"],
                       tuple(tuple(p) for p in r["fit_config"]["excluded"])) for r in valid}
            # xmin/xmax may be None, so also compare actual fitted grid endpoints.
            spectra_by_id = {s.id: s for s in eligible}
            actual = {(spectra_by_id[r["spectrum_id"]].result["x"][0],
                       spectra_by_id[r["spectrum_id"]].result["x"][-1]) for r in valid}
            if len(ranges) > 1 or len(actual) > 1:
                messages.append(tr('{0}：積分區間或遮罩不同，請確認比較範圍。').format(tr(METRICS[key][0]), ''))
    return {"rows": rows, "messages": list(dict.fromkeys(messages)), "metrics": keys,
            "x_mode": mode, "categories": categories, "spectrum_count": len(eligible)}


def draw_trends(figure: Figure, spectra, settings=None, font="Arial"):
    settings = DEFAULT_TRENDS | (settings or {})
    prepared = prepare_trends(spectra, settings)
    keys = prepared["metrics"]
    figure.clear()
    columns = int(settings.get("figure_options", {}).get("columns", 0)) or (1 if len(keys) == 1 else 2)
    columns = max(1, min(columns, len(keys)))
    nrows = math.ceil(len(keys)/columns)
    grid = figure.add_gridspec(nrows, columns)
    axes = []
    for i, key in enumerate(keys):
        ax = figure.add_subplot(grid[i//columns, i % columns])
        ax._pl_style_key = "trend:"+key
        axes.append(ax)
        rows = [r for r in prepared["rows"] if r["metric"] == key and r["valid"]]
        if prepared["x_mode"] == "numeric" and settings["sort_numeric"]:
            rows.sort(key=lambda r: r["x"])
        xx = [r["x"] for r in rows]
        yy = [r["value"] for r in rows]
        color = PALETTE[list(METRICS).index(key) % len(PALETTE)]
        if rows:
            kind = settings.get("plot_type", "dot-line" if settings["connect"] else "dot")
            if kind not in ("dot", "line", "dot-line", "bar", "area"):
                raise ValueError(tr("不支援的趨勢圖型。"))
            if kind == "bar":
                unique = np.unique(xx)
                spacing = float(np.min(np.diff(unique))) if len(unique) > 1 else 1.0
                ax.bar(xx, yy, width=settings.get("bar_width", .65)*spacing, color=color, alpha=.85)
                ax.containers[-1]._pl_style_key = "trend:"+key
            else:
                ax.plot(xx, yy, marker="o" if kind in ("dot", "dot-line") else "None", markersize=5.5,
                        color=color, lw=settings.get("line_width", 1.6), linestyle="None" if kind == "dot" else "-")
                ax.lines[-1]._pl_style_key = "trend:"+key
                if kind == "area":
                    ax.fill_between(xx, yy, color=color, alpha=.25)
            if settings["errorbars"]:
                with_error = [r for r in rows if r["stderr"] is not None]
                if with_error:
                    ax.errorbar([r["x"] for r in with_error], [r["value"] for r in with_error],
                                yerr=[r["stderr"] for r in with_error], fmt="none", color=color,
                                capsize=3, elinewidth=1)
            if settings["annotate"]:
                for r in rows:
                    ax.annotate(r["name"], (r["x"], r["value"]), xytext=(4, 6),
                                textcoords="offset points", fontsize=settings["font_size"]*.8,
                                fontfamily=[font, "Microsoft JhengHei"])
        else:
            ax.text(.5, .5, "No valid fitted data", ha="center", va="center", transform=ax.transAxes,
                    color="#8292a3")
        if prepared["x_mode"] == "category":
            ax._pl_categorical = True
            labels = prepared["categories"]
            ax.set_xticks(range(len(labels)), labels, rotation=30 if len(labels) > 3 else 0,
                          ha="right" if len(labels) > 3 else "center")
            ax.set_xlim(-.5, max(.5, len(labels)-.5))
        ax.set_xlabel(settings["xlabel"].strip() or "Condition")
        unit = rows[0]["unit"] if rows else ""
        ylabel = METRICS[key][1] + (f" ({unit})" if unit and unit != "1" else "")
        ax.set_ylabel(ylabel)
        title = f"Peak {settings['peak']}" if METRICS[key][2] == "peak" else "Spectrum"
        ax.set_title(title, fontsize=settings["font_size"])
        ax.tick_params(direction="in", top=True, right=True)
        ax.margins(y=.18, x=.08)
        for label in [ax.xaxis.label, ax.yaxis.label, ax.title, *ax.get_xticklabels(), *ax.get_yticklabels()]:
            label.set_fontfamily([font, "Microsoft JhengHei"])
            label.set_fontsize(settings["font_size"])
        ax.grid(axis="y", alpha=.15)
        ax.ticklabel_format(axis="y", style="sci", scilimits=(-3, 5), useOffset=False)
    figure.set_layout_engine("tight", pad=1.4, h_pad=1.6, w_pad=1.6)
    apply_figure_style(figure, settings)
    return axes, prepared


def export_trends(path, spectra, settings=None, font="Arial"):
    settings = DEFAULT_TRENDS | (settings or {})
    if settings["view"] != "overview":
        settings = chart_settings(settings, "trend:"+settings["view"])
        font = settings.get("font", font)
    for key in ("width_cm", "height_cm", "dpi", "font_size"):
        if not np.isfinite(settings[key]) or settings[key] <= 0:
            raise ValueError(tr('{0} 必須為正數。').format(key, ''))
    prepared = prepare_trends(spectra, settings)
    if not any(r["valid"] for r in prepared["rows"]):
        raise ValueError(tr("沒有可繪製的擬合結果。請先擬合並勾選資料。"))
    figure = Figure(figsize=figure_size(settings), dpi=settings["dpi"])
    draw_trends(figure, spectra, settings, font)
    save_figure(figure, path, settings)


def export_trend_set(directory, spectra, settings=None, extension="png", font="Arial"):
    settings = DEFAULT_TRENDS | (settings or {})
    if extension not in ("png", "jpg", "pdf", "svg"):
        raise ValueError(tr("不支援的圖形格式。"))
    keys = selected_metrics(settings, overview=True)
    # Validate all panels before writing the first file.
    prepared = prepare_trends(spectra, settings | {"view": "overview"})
    if not any(r["valid"] for r in prepared["rows"]):
        raise ValueError(tr("沒有可繪製的擬合結果。"))
    output, skipped = [], []
    for key in keys:
        if not any(r["valid"] for r in prepared["rows"] if r["metric"] == key):
            skipped.append(tr(METRICS[key][0]))
            continue
        path = Path(directory)/f"Peak_{settings['peak']}_{key}.{extension}"
        export_trends(path, spectra, settings | {"view": key}, font)
        output.append(path)
    return output, skipped
