"""Resolve one chart's saved overrides for both preview and export."""
import copy
import math

from .i18n import tr


def chart_settings(settings, key):
    result = copy.deepcopy(settings)
    patch = result.pop("chart_styles", {}).get(key, {})
    options = result.get("figure_options", {})
    local = patch.get("figure_options", {})
    result.update({k: copy.deepcopy(v) for k, v in patch.items() if k != "figure_options"})
    if options or local or "figure_options" in result:
        result["figure_options"] = options | copy.deepcopy(local)
        if "layers" in options or "layers" in local:
            result["figure_options"]["layers"] = options.get("layers", {}) | copy.deepcopy(local.get("layers", {}))
            layers = result["figure_options"]["layers"]
            source_index = None
            if key.startswith("overlay:"):
                source_index = 2 if key.endswith(":normalized") else 1
            elif key.startswith("trend:"):
                metric = key.split(":", 1)[1]
                metrics = settings.get("metrics", [])
                source_index = metrics.index(metric)+1 if metric in metrics else 1
            elif key.startswith("spectrum:"):
                source_index = 1
            if source_index is not None and key not in layers and str(source_index) in layers:
                layers[key] = copy.deepcopy(layers[str(source_index)])
            if key.startswith(("overlay:", "trend:")):
                result["figure_options"]["layers"] = {k: v for k, v in layers.items() if not str(k).isdigit()}
    return result


def validate_chart_styles(settings):
    from .figure_style import validate_options
    styles = settings.get("chart_styles", {})
    if not isinstance(styles, dict):
        raise ValueError(tr("個別圖設定必須是 JSON 物件。"))
    for key, patch in styles.items():
        if not isinstance(key, str) or not isinstance(patch, dict) or "chart_styles" in patch:
            raise ValueError(tr("個別圖設定無效。"))
        resolved = chart_settings(settings, key)
        for name in ("width_cm", "height_cm", "dpi", "font_size", "line_width"):
            value = resolved.get(name, 1)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(tr('{0} 必須為正數。').format(name, ''))
        validate_options(resolved.get("figure_options", {}))
