from __future__ import annotations

from .i18n import tr

import copy
import re
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

import numpy as np
from lmfit import Minimizer, Parameters
from lmfit.models import (ConstantModel, GaussianModel, LinearModel, LorentzianModel,
                          PseudoVoigtModel, SkewedGaussianModel, SkewedVoigtModel,
                          VoigtModel)
from scipy.signal import find_peaks, savgol_filter
from scipy.optimize import brentq, minimize_scalar

from .data import FitConfig, Spectrum, clean_json, transformed

MODELS = {"Gaussian": GaussianModel, "Lorentzian": LorentzianModel,
          "Voigt": VoigtModel, "PseudoVoigt": PseudoVoigtModel,
          "SkewedGaussian": SkewedGaussianModel, "SkewedVoigt": SkewedVoigtModel}


class FitCancelled(Exception):
    pass


def peak_candidates(spectrum: Spectrum, config: FitConfig, prominence=0.06, maximum=8):
    x, y = transformed(spectrum, config)
    window = min(21, (len(y) // 2) * 2 - 1)
    smoothed = savgol_filter(y, window, 3) if window >= 5 else y
    indices, properties = find_peaks(smoothed, prominence=max(np.ptp(smoothed)*prominence, 1e-15),
                                     distance=max(3, len(x)//40))
    if len(indices) == 0:
        indices = np.array([int(np.argmax(smoothed))])
    else:
        order = np.argsort(properties["prominences"])[::-1][:maximum]
        indices = indices[order]
    return sorted(float(x[i]) for i in indices)


def build_model(spectrum: Spectrum, config: FitConfig):
    x, y = transformed(spectrum, config)
    if not config.peaks or len(config.peaks) > 12:
        raise ValueError(tr("請設定 1–12 個分峰。"))
    model = None
    params = Parameters()
    baseline = float(np.percentile(y, 8)) if config.background != "none" else 0.0
    width = float(np.ptp(x))
    dx = float(np.median(np.diff(x)))
    centers = peak_candidates(spectrum, config)
    for i, model_name in enumerate(config.peaks, 1):
        if model_name not in MODELS:
            raise ValueError(tr('未知模型：{1}').format('', model_name))
        prefix = f"p{i}_"
        part = MODELS[model_name](prefix=prefix)
        pp = part.make_params()
        center = centers[min(i-1, len(centers)-1)]
        sigma = max(width/(15*len(config.peaks)), dx)
        height = max(float(np.interp(center, x, y))-baseline, np.ptp(y)*0.05, 1e-12)
        pp[prefix+"amplitude"].set(value=height*sigma*np.sqrt(2*np.pi), min=0)
        pp[prefix+"center"].set(value=center, min=float(x.min()), max=float(x.max()))
        pp[prefix+"sigma"].set(value=sigma, min=max(dx*0.25, 1e-12), max=width)
        if prefix+"gamma" in pp:
            pp[prefix+"gamma"].set(expr="", vary=True, value=sigma,
                                   min=max(dx*0.25, 1e-12), max=width)
        params.update(pp)
        model = part if model is None else model+part
    if config.background == "constant":
        bg = ConstantModel(prefix="b_")
        bp = bg.make_params(c=baseline)
        model += bg
        params.update(bp)
    elif config.background == "linear":
        bg = LinearModel(prefix="b_")
        bp = bg.make_params(intercept=baseline, slope=0)
        model += bg
        params.update(bp)
    elif config.background != "none":
        raise ValueError(tr("未知背景模型。"))
    for name, saved in config.parameters.items():
        if name not in params:
            continue
        parameter = params[name]
        if name.endswith(("_fwhm", "_height")):
            continue  # Derived values are not optimization controls.
        lo, hi = saved.get("min", -np.inf), saved.get("max", np.inf)
        lo = -np.inf if lo is None else float(lo)
        hi = np.inf if hi is None else float(hi)
        value = float(saved.get("value", parameter.value))
        expr = str(saved.get("expr", "")).strip()
        if np.isnan(lo) or np.isnan(hi) or lo >= hi or not np.isfinite(value):
            raise ValueError(tr('{0}：數值或上下限無效。').format(name, ''))
        if not expr and not lo <= value <= hi:
            raise ValueError(tr('{0}：初始值超出上下限。').format(name, ''))
        if name.endswith(("_sigma", "_gamma")) and lo <= 0:
            raise ValueError(tr('{0}：寬度下限必須大於零。').format(name, ''))
        if name.endswith("_amplitude") and lo < 0:
            raise ValueError(tr('{0}：面積下限不得小於零。').format(name, ''))
        parameter.set(value=value, min=lo, max=hi,
                      vary=bool(saved.get("vary", True)), expr=expr)
    params.update_constraints()
    if not np.isfinite(model.eval(params, x=x)).all():
        raise ValueError(tr("初始模型產生非有限值，請檢查參數或關係式。"))
    return model, params, x, y


def parameter_config(params):
    return {name: {"value": p.value, "min": p.min, "max": p.max,
                   "vary": p.vary, "expr": p.expr or ""}
            for name, p in params.items() if not name.endswith(("_fwhm", "_height"))}


def _cancel_callback(event):
    def callback(params, iteration, residual, *args, **kwargs):
        if event is not None and event.is_set():
            raise FitCancelled(tr("使用者已取消擬合。"))
    return callback


def _optimize(params, residual, starts, event):
    free = [p for p in params.values() if p.vary and not p.expr]
    ndata = len(residual(params))
    if ndata <= len(free):
        raise ValueError(tr("有效資料點數必須大於自由參數數目。"))
    if not free:
        # lmfit requires at least one variable for its least-squares backend.
        from types import SimpleNamespace
        r = residual(params)
        return SimpleNamespace(params=params, success=True, message=tr("所有參數固定，僅評估模型。"),
                               nvarys=0, ndata=ndata, chisqr=float(r@r), covar=None,
                               var_names=[], nfev=0)
    rng = np.random.default_rng(2026)
    best = None
    for attempt in range(max(1, min(int(starts), 10))):
        if event is not None and event.is_set():
            raise FitCancelled()
        trial = params.copy()
        if attempt:
            for p in trial.values():
                if not p.vary or p.expr:
                    continue
                if p.name.endswith("_center"):
                    scale = (p.max-p.min)*0.025 if np.isfinite([p.min, p.max]).all() else abs(p.value)*0.005
                    value = p.value + rng.normal()*scale
                elif p.name.endswith(("_amplitude", "_sigma", "_gamma")):
                    value = p.value*rng.uniform(0.65, 1.5)
                else:
                    continue
                p.value = float(np.clip(value, p.min+1e-12, p.max-1e-12))
        result = Minimizer(residual, trial, iter_cb=_cancel_callback(event),
                           nan_policy="raise").minimize(method="least_squares", max_nfev=6000)
        if best is None or (result.success and not best.success) or (
                result.success == best.success and result.chisqr < best.chisqr):
            best = result
    return best


def _statistics(residual, nvars):
    n = len(residual)
    rss = float(np.dot(residual, residual))
    return {"rss": rss, "rmse": float(np.sqrt(rss/n)),
            "redchi": rss/(n-nvars) if n > nvars else None,
            "aic": n*np.log(max(rss/n, np.finfo(float).tiny))+2*nvars,
            "bic": n*np.log(max(rss/n, np.finfo(float).tiny))+np.log(n)*nvars,
            "npoints": n, "nfree": nvars}


def _peak_geometry(part, params, lower, upper):
    """Continuous peak position and width for uncertainty propagation."""
    def curve(value):
        return float(np.asarray(part.eval(params, x=np.array([value])))[0])

    # Optimize relative to the model center: scipy's relative stopping tolerance
    # must not scale with an absolute wavelength of hundreds of nanometers.
    origin = params[part.prefix+"center"].value
    optimum = minimize_scalar(lambda shift: -curve(origin+shift), bounds=(lower-origin, upper-origin),
                              method="bounded", options={"xatol": (upper-lower)*1e-11})
    position = origin+optimum.x
    half = curve(position) / 2
    width = np.nan
    if curve(lower) < half and curve(upper) < half:
        left = brentq(lambda value: curve(value)-half, lower, position)
        right = brentq(lambda value: curve(value)-half, position, upper)
        width = right-left
    return np.array([position, width])


def _asymmetric_peak_errors(part, params, solution, lower, upper, namespace=""):
    """Propagate the full fit covariance, including joint-fit constraints."""
    if solution.covar is None:
        return None, None
    gradients = []
    for name in solution.var_names:
        parameter = solution.params[name]
        step = max(abs(parameter.value)*1e-4, (parameter.stderr or 0)*1e-3, 1e-6)
        low = max(parameter.min, parameter.value-step)
        high = min(parameter.max, parameter.value+step)
        if high <= low:
            return None, None
        values = []
        for value in (low, high):
            global_params = solution.params.copy()
            global_params[name].value = value
            global_params.update_constraints()
            local = params.copy()
            for key, p in local.items():
                if not p.expr:
                    p.value = global_params[namespace+key].value
            local.update_constraints()
            values.append(_peak_geometry(part, local, lower, upper))
        gradients.append((values[1]-values[0])/(high-low))
    jacobian = np.asarray(gradients).T
    variances = np.einsum("ij,jk,ik->i", jacobian, solution.covar, jacobian)
    return tuple(float(np.sqrt(v)) if np.isfinite(v) and v >= 0 else None for v in variances)


def _record(spectrum, config, model, params, x, y, solution, joint=None, namespace=""):
    fitted = np.asarray(model.eval(params, x=x))
    residual = y-fitted
    components = {k: np.broadcast_to(np.asarray(v), x.shape).copy()
                  for k, v in model.eval_components(params=params, x=x).items()}
    stats = _statistics(residual, solution.nvarys) if joint is None else {
        "rss": float(residual@residual), "rmse": float(np.sqrt(np.mean(residual**2))),
        "redchi": None, "aic": None, "bic": None, "npoints": len(x), "nfree": None}
    total = float(np.sum((y-y.mean())**2))
    stats["r2"] = 1-float(residual@residual)/total if total > 0 else None
    warnings = []
    if not solution.success:
        warnings.append(tr("未收斂"))
    if solution.nvarys and solution.covar is None:
        warnings.append(tr("無法估算參數協方差／標準誤"))
    if solution.covar is not None:
        diag = np.sqrt(np.maximum(np.diag(solution.covar), 0))
        denom = np.outer(diag, diag)
        corr = np.divide(solution.covar, denom, out=np.zeros_like(solution.covar), where=denom>0)
        np.fill_diagonal(corr, 0)
        if np.any(np.abs(corr) > 0.98):
            warnings.append(tr("部分自由參數高度相關（|r| > 0.98）"))
    parameter_rows = []
    for name, p in params.items():
        near = False
        if p.vary and not p.expr:
            tol = max(abs(p.value)*1e-5, 1e-9)
            near = (np.isfinite(p.min) and abs(p.value-p.min)<tol) or (
                np.isfinite(p.max) and abs(p.value-p.max)<tol)
            if near:
                warnings.append(tr('{0} 接近上下限').format(name, ''))
        parameter_rows.append({"parameter": name, "value": p.value, "stderr": p.stderr,
                               "min": p.min, "max": p.max, "fixed": not p.vary and not p.expr,
                               "expr": p.expr or "", "at_bound": bool(near)})
    dense = np.linspace(x.min(), x.max(), 12001)
    peak_rows = []
    for i, model_name in enumerate(config.peaks, 1):
        prefix = f"p{i}_"
        part = MODELS[model_name](prefix=prefix)
        curve = part.eval(params, x=dense)
        maximum = int(np.argmax(curve))
        height = float(curve[maximum])
        half = np.flatnonzero(curve >= height/2)
        fwhm = None
        if len(half) and half[0] > 0 and half[-1] < len(dense)-1:
            a, b = half[0], half[-1]
            left = np.interp(height/2, curve[a-1:a+1], dense[a-1:a+1])
            right = np.interp(height/2, curve[b:b+2][::-1], dense[b:b+2][::-1])
            fwhm = float(right-left)
        else:
            warnings.append(tr('Peak {1} 的半高寬超出擬合區間，未回報 FWHM').format('', i, ''))
        if model_name in ("SkewedGaussian", "SkewedVoigt"):
            position_error, width_error = _asymmetric_peak_errors(part, params, solution, x.min(), x.max(), namespace)
        else:
            position_error = params[prefix+"center"].stderr
            width_parameter = params.get(prefix+"fwhm")
            width_error = width_parameter.stderr if width_parameter is not None else None
        if maximum in (0, len(dense)-1):
            position_error = None
        peak_rows.append({"peak": i, "model": model_name,
                          "center": params[prefix+"center"].value,
                          "center_stderr": params[prefix+"center"].stderr,
                          "maximum_position": float(dense[maximum]), "maximum_position_stderr": position_error,
                          "height": height, "fwhm": fwhm, "fwhm_stderr": width_error if fwhm is not None else None,
                          "amplitude": params[prefix+"amplitude"].value,
                          "amplitude_stderr": params[prefix+"amplitude"].stderr,
                          "area_in_range": float(np.trapezoid(curve, dense))})
    area = sum(p["area_in_range"] for p in peak_rows)
    for peak in peak_rows:
        peak["area_fraction"] = peak["area_in_range"]/area if area else None
    bg = components.get("b_", np.zeros_like(x))
    signal = np.maximum(y-bg, 0)
    # Integrate on the full grid inside the fit limits; masked data are not bridged.
    # These descriptive metrics are omitted when masks are present.
    denominator = float(np.trapezoid(signal, x)) if not config.excluded else 0
    stats["centroid_positive_background_subtracted"] = (
        float(np.trapezoid(x*signal, x)/denominator) if denominator > 0 else None)
    stats["measured_area_background_subtracted"] = (
        float(np.trapezoid(y-bg, x)) if not config.excluded else None)
    effective_config = copy.deepcopy(config)
    effective_config.parameters = parameter_config(params)
    return clean_json({"id": uuid.uuid4().hex, "timestamp": datetime.now(timezone.utc).isoformat(),
                       "source_sha256": spectrum.digest, "config": asdict(effective_config),
                       "success": bool(solution.success), "message": str(solution.message),
                       "warnings": warnings, "metrics": stats, "peaks": peak_rows,
                       "parameters": parameter_rows, "x": x, "y": y, "fitted": fitted,
                       "residual": residual, "components": components, "joint": joint,
                       "error_assumption": "Unweighted least squares; independent equal-variance errors. "
                       "Standard errors are local covariance estimates, not replicate statistics."})


def fit_spectrum(spectrum: Spectrum, config: FitConfig | None = None,
                 cancel: threading.Event | None = None):
    config = copy.deepcopy(config or spectrum.config)
    model, params, x, y = build_model(spectrum, config)
    solution = _optimize(params, lambda p: model.eval(p, x=x)-y, config.starts, cancel)
    return _record(spectrum, config, model, solution.params, x, y, solution)


def fit_joint(spectra: list[Spectrum], configs: list[FitConfig], shared: list[str], cancel=None):
    if len(spectra) < 2:
        raise ValueError(tr("聯合擬合至少需要兩條光譜。"))
    if len(configs) != len(spectra):
        raise ValueError(tr("設定與光譜數目不一致。"))
    built = [build_model(s, c) for s, c in zip(spectra, configs)]
    allparams = Parameters()
    names = []
    for i, (_, local, _, _) in enumerate(built):
        names.append(set(local))
        for name, p in local.items():
            allparams.add(f"s{i}_{name}", value=p.value, min=p.min, max=p.max, vary=p.vary)
    for key in shared:
        if not all(key in n for n in names):
            raise ValueError(tr('共用參數 {1} 並非每條光譜都有。').format('', key, ''))
        locals_ = [b[1][key] for b in built]
        if any(p.expr or not p.vary for p in locals_):
            raise ValueError(tr('共用參數 {1} 必須為自由參數，不能同時固定或指定關係式。').format('', key, ''))
        low, high = max(p.min for p in locals_), min(p.max for p in locals_)
        if low >= high:
            raise ValueError(tr('共用參數 {1} 沒有共同的上下限範圍。').format('', key, ''))
        allparams[f"s0_{key}"].set(min=low, max=high,
                                      value=float(np.clip(locals_[0].value, low, high)))
    for i, (_, local, _, _) in enumerate(built):
        for name, p in local.items():
            if i and name in shared:
                expr = f"s0_{name}"
            elif p.expr:
                expr = re.sub(r"\b[A-Za-z_]\w*\b",
                              lambda m: f"s{i}_{m[0]}" if m[0] in names[i] else m[0], p.expr)
            else:
                continue
            allparams[f"s{i}_{name}"].set(expr=expr)

    def localize(global_params, i):
        pp = built[i][1].copy()
        for name in pp:
            gp = global_params[f"s{i}_{name}"]
            if not pp[name].expr:
                pp[name].value = gp.value
            pp[name].stderr = gp.stderr
        pp.update_constraints()
        return pp

    def residual(pp):
        return np.concatenate([model.eval(localize(pp, i), x=x)-y
                               for i, (model, _, x, y) in enumerate(built)])

    solution = _optimize(allparams, residual, max(c.starts for c in configs), cancel)
    joint = clean_json({"id": uuid.uuid4().hex, "members": [s.id for s in spectra],
                        "shared": shared, "metrics": _statistics(residual(solution.params), solution.nvarys),
                        "note": "AIC/BIC and reduced chi-square describe the entire joint fit."})
    results = []
    for i, (spectrum, config, (model, _, x, y)) in enumerate(zip(spectra, configs, built)):
        pp = localize(solution.params, i)
        for key in shared:
            pp[key].stderr = solution.params[f"s0_{key}"].stderr
        results.append(_record(spectrum, config, model, pp, x, y, solution, joint, f"s{i}_"))
    return results
