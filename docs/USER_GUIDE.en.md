# PL Studio user guide

[Back to home](../README.en.md) · [繁體中文](USER_GUIDE.zh-TW.md)

The menu bar contains **File, Figure, Settings and Help**. File groups project creation/opening, Save/Save as, data import and export. Figure opens Figure Template and loads/saves templates for all figure types. Settings controls language and startup update checks. Help contains the user guide (F1), manual update checks and About. Existing Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+Shift+S, Ctrl+I and Ctrl+T shortcuts remain available.

## Basic workflow

1. Create a project and import spectra with at least 10 numeric rows. Input wavelengths must be positive, finite and unique.
2. Edit display names on the left. Checkboxes control overlays, trends and figure exports; Ctrl / Shift selection controls batch operations. These are separate selections.
3. Choose fitting coordinates, range, exclusions, background and peak models. Shift-drag selects a range in the main plot.
4. Edit initial values, bounds, fixed parameters and expressions. Parameter expressions constrain existing model parameters; they do not define arbitrary peak functions.
5. Fit the current spectrum, batch fit selected spectra with their own settings, or joint fit with the current configuration and checked shared parameters.
6. Inspect residuals, convergence, uncertainty and warnings. Refit after changing working settings; existing results retain the configuration used to produce them.
7. Enter a Condition for each spectrum to compare fitted metrics. Conditions may be names or finite numbers; no replicate averaging or group statistics are performed.
8. Use Figure Template for presentation settings, export results and save the complete project.

The **File → Export → Images** action exports to a folder regardless of the active tab. Choose PNG, JPG, PDF or SVG, then a destination folder. Each checked spectrum gets its own `PL_001_name` file. Absolute and normalized overlays are saved separately as `PL_overlay_intensity` and `PL_overlay_normalized`. Every checked trend metric for the current Peak number gets a separate `Peak_1_metric` file, using its current layout settings. Existing files are preserved by adding a numeric suffix. The completion dialog lists any charts skipped because of missing fit results or other plotting constraints; the remaining charts are still exported.

Each individual PL image includes the DATA name and a summary such as `xc = 806.42 ± 0.05 nm`, `w = 48.83 ± 0.14 nm`, `R2 = 0.995`, placed in a less occupied area. Here xc is peak position and w is FWHM; values and errors use two decimal places, with three for R2. Units come from the saved fit. Multi-peak fits list xc and w for each peak. Errors are one standard error from the local fit covariance; asymmetric peak errors use full covariance propagation. Missing values show N/A, and unfitted data show Not fitted. Older asymmetric fits need refitting to obtain these derived errors.

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


## Graph formatting (Plot Details)

Open Figure Template from the Figure menu. The editor follows the downloaded Origin 2025 User Guide: select Page, Layer or Plot in the object tree, edit the corresponding tabs, and inspect the preview. Layer positions use percentages of the page; plot formatting applies to the selected curve. Axes... opens separate Bottom/Top/Left/Right axis settings with Scale, Tick Labels, Title, Grids, Line and Ticks, Special Ticks and Reference Lines.

Apply updates the main graph; OK applies and closes; Cancel discards edits made since the last Apply. Formats are preserved in v2 JSON templates and projects. The implementation covers the current PL 2-D workflow; full Origin feature and pixel parity, binary themes and style transfer to .opju remain unverified or unsupported. See the [version comparison](ORIGIN2025_GRAPH_SETTINGS.zh-TW.md).

Each DATA, trend metric, and raw/normalized overlay is rendered in an independent figure. Groups arrange fixed-size canvases and scroll instead of shrinking plots when their count increases. Select a chart Page to set its own dimensions and DPI. Apply to Every Chart copies the selected chart format to the current group or all plot types (Apply Scope); the optional checkbox includes axis ranges and titles. Batch and overview exports write separate image files, and each chart toolbar saves at its configured export DPI.
