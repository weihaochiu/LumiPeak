# PL Studio user guide

[Back to home](../README.en.md) · [繁體中文](USER_GUIDE.zh-TW.md)

## Basic workflow

1. Create a project and import spectra with at least 10 numeric rows. Input wavelengths must be positive, finite and unique.
2. Edit display names on the left. Checkboxes control overlays, trends and figure exports; Ctrl / Shift selection controls batch operations. These are separate selections.
3. Choose fitting coordinates, range, exclusions, background and peak models. Shift-drag selects a range in the main plot.
4. Edit initial values, bounds, fixed parameters and expressions. Parameter expressions constrain existing model parameters; they do not define arbitrary peak functions.
5. Fit the current spectrum, batch fit selected spectra with their own settings, or joint fit with the current configuration and checked shared parameters.
6. Inspect residuals, convergence, uncertainty and warnings. Refit after changing working settings; existing results retain the configuration used to produce them.
7. Enter a Condition for each spectrum to compare fitted metrics. Conditions may be names or finite numbers; no replicate averaging or group statistics are performed.
8. Use Figure Template for presentation settings, export results and save the complete project.

**Peak intensity** is the fitted component's maximum, excluding background and other peaks. It differs from peak area. Peak identifiers follow the order of components in each fit; users must verify that compared peaks represent the same physical feature.

## Definitions and scientific limits

- Instrument Counts are not calibrated photon flux. Energy uses `E = 1239.8419843320026 / wavelength_nm`. The optional Jacobian is valid only when the input is spectral density per nm; Counts/pixel must not be treated as per nm automatically.
- Normalization uses the full measured spectrum before cropping to the fitting range. Display-only normalization and offsets do not change fitted data.
- Fits use unweighted least squares with deterministic initial-value retries. Standard errors are local covariance estimates, not replicate statistics. Unidentifiable or unavailable errors remain blank.
- Model center, numerical peak maximum and spectral centroid are different quantities. FWHM is unavailable if either half-maximum crossing lies outside the fit range. Model areas are integrated over the full fit interval, including excluded intervals; measured integration and centroid are not reported across masked gaps.
- Trend comparisons require compatible coordinates and intensity processing. Different integration ranges produce notices. Only already available parameter standard errors are plotted; FWHM or peak-position errors are not invented.
- AIC / BIC comparisons require the same data and assumptions. Joint-fit information criteria and degrees of freedom describe the entire joint fit.
- Peak decomposition alone does not establish excitonic, defect or phase assignments. A single uncalibrated PL spectrum does not determine lifetime, defect density, PLQY or QFLS. Finite-range area is not PLQY.
- Origin exports currently transfer data and basic curves, without reproducing all Figure Template styles. Direct `.opju` automation requires a separate compatible Origin installation and has not been validated on this computer.

