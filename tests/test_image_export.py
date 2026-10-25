import pytest
from PIL import Image

from plstudio.exporting import export_image_set
from plstudio.fitting import fit_spectrum
from tests.test_core import synthetic


@pytest.fixture
def spectra():
    first, second, excluded = synthetic(), synthetic(center=815), synthetic(center=825)
    for index, spectrum in enumerate((first, second, excluded), 1):
        spectrum.name = f"Sample_{index}"
        spectrum.result = fit_spectrum(spectrum)
    excluded.plot = False
    return [first, second, excluded]


def settings():
    size = {"width_cm": 12.7, "height_cm": 10.16, "dpi": 72}
    return size | {"overlay": size,
                   "trends": size | {"metrics": ["maximum_position", "height"], "view": "height"}}


@pytest.mark.parametrize("extension", ["png", "jpg", "pdf", "svg"])
def test_exports_individual_spectra_both_overlays_and_each_trend(spectra, tmp_path, extension):
    paths, skipped = export_image_set(tmp_path, spectra, settings(), extension)
    assert not skipped
    assert {p.name for p in paths} == {
        f"{stem}.{extension}" for stem in (
            "PL_001_Sample_1", "PL_002_Sample_2", "PL_overlay_intensity",
            "PL_overlay_normalized", "Peak_1_maximum_position", "Peak_1_height")}
    assert all(p.parent == tmp_path and p.stat().st_size > 1000 for p in paths)
    if extension == "png":
        for path in paths:
            with Image.open(path) as image:
                assert image.size == (360, 288)
    if extension == "svg":
        first = (tmp_path / "PL_001_Sample_1.svg").read_text("utf-8")
        second = (tmp_path / "PL_002_Sample_2.svg").read_text("utf-8")
        overlay = (tmp_path / "PL_overlay_intensity.svg").read_text("utf-8")
        assert "Sample_1" in first and "Sample_2" not in first
        assert "Sample_2" in second and "Sample_1" not in second
        assert "Sample_1" in overlay and "Sample_2" in overlay and "Sample_3" not in overlay
        peak = spectra[0].result["peaks"][0]
        assert f"xc = {peak['maximum_position']:.2f} ± {peak['maximum_position_stderr']:.2f} nm" in first
        assert f"w = {peak['fwhm']:.2f} ± {peak['fwhm_stderr']:.2f} nm" in first
        assert f"R2 = {spectra[0].result['metrics']['r2']:.3f}" in first
        assert "xc =" not in overlay


def test_safe_duplicate_names_and_existing_files_are_preserved(spectra, tmp_path):
    spectra[0].name = spectra[1].name = '../CON:<name>?\\*'
    paths, skipped = export_image_set(tmp_path, spectra, settings())
    assert not skipped
    before = {p: p.read_bytes() for p in paths}
    again, skipped = export_image_set(tmp_path, spectra, settings())
    assert not skipped and len(again) == len(paths)
    assert not set(paths) & set(again)
    assert all(p.name.endswith("_2.png") for p in again)
    assert all(p.read_bytes() == data for p, data in before.items())
    assert all(p.parent == tmp_path and not any(c in p.name for c in '<>:"/\\|?*') for p in paths)


def test_unfitted_data_still_exports_pl_and_overlays(tmp_path):
    paths, skipped = export_image_set(tmp_path, [synthetic()], settings())
    assert len(paths) == 3
    assert len(skipped) == 2
    assert all("沒有可繪製的擬合結果" in reason for reason in skipped)


def test_unavailable_trends_do_not_block_valid_charts(spectra, tmp_path):
    style = settings()
    style["trends"]["metrics"] = ["area_fraction", "height"]
    paths, skipped = export_image_set(tmp_path, spectra, style)
    assert len(paths) == 5
    assert (tmp_path / "Peak_1_height.png") in paths
    assert not (tmp_path / "Peak_1_area_fraction.png").exists()
    assert len(skipped) == 1 and "分峰面積比例" in skipped[0]


def test_empty_selection_or_invalid_format_writes_nothing(spectra, tmp_path):
    for spectrum in spectra:
        spectrum.plot = False
    with pytest.raises(ValueError, match="勾選"):
        export_image_set(tmp_path / "empty", spectra, settings())
    with pytest.raises(ValueError, match="格式"):
        export_image_set(tmp_path / "invalid", spectra, settings(), "bmp")
    assert not list(tmp_path.iterdir())


def test_fit_summary_uses_saved_peak_position_units_and_avoids_curves(spectra, monkeypatch, tmp_path):
    from plstudio.plotting import export_figure
    spectrum = spectra[0]
    spectrum.name = "Name with $literal$ text"
    peak = spectrum.result["peaks"][0]
    # Deliberately distinguish the model center from the measured peak position.
    peak["maximum_position"] = 812.345
    peak["center"] = 800
    spectrum.config.domain = "eV"  # Export must still describe the saved nm fit.
    captured = []
    monkeypatch.setattr("plstudio.plotting.save_figure", lambda figure, *a: captured.append(figure))
    export_figure(tmp_path / "summary.svg", [spectrum], settings() | {"fit_summary": True})
    figure = captured[0]
    figure.canvas.draw()
    ax = figure.axes[0]
    label = ax.texts[-1]
    assert spectrum.name in label.get_text()
    assert "xc = 812.35 ±" in label.get_text()
    assert "xc = 800" not in label.get_text()
    assert label.get_text().splitlines()[1].endswith(" nm")
    renderer = figure.canvas.get_renderer()
    box = label.get_window_extent(renderer)
    assert ax.bbox.contains(box.x0, box.y0) and ax.bbox.contains(box.x1, box.y1)
    assert not box.overlaps(ax.get_legend().get_window_extent(renderer))
    assert not any(line.get_transform().transform_path(line.get_path()).intersects_bbox(box, filled=False)
                   for line in ax.lines)


def test_multi_peak_and_missing_values_are_explicit(spectra, tmp_path):
    spectrum = spectra[0]
    first = spectrum.result["peaks"][0]
    spectrum.result["peaks"].append(first | {"peak": 2, "fwhm": None, "maximum_position": 820})
    spectrum.result["metrics"]["r2"] = None
    export_image_set(tmp_path, [spectrum], settings(), "svg")
    text = (tmp_path / "PL_001_Sample_1.svg").read_text("utf-8")
    assert "Peak 1" in text and "Peak 2" in text
    assert "xc = 820.00 ±" in text
    assert "w = N/A ±" in text and "R2 = N/A" in text


def test_older_fit_records_reuse_saved_symmetric_parameter_errors(spectra, tmp_path):
    spectrum = spectra[0]
    peak = spectrum.result["peaks"][0]
    del peak["maximum_position_stderr"], peak["fwhm_stderr"]
    export_image_set(tmp_path, [spectrum], settings(), "svg")
    text = (tmp_path / "PL_001_Sample_1.svg").read_text("utf-8")
    assert f"xc = {peak['maximum_position']:.2f} ± {peak['center_stderr']:.2f} nm" in text
    assert "± N/A" not in text
