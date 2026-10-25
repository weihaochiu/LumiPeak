import copy

import numpy as np
import pytest
from matplotlib.figure import Figure
from PIL import Image

from plstudio.data import FitConfig
from plstudio.fitting import fit_spectrum
from plstudio.overlay import DEFAULT_OVERLAY, draw_overlay, export_overlay, export_overlay_files
from tests.test_core import synthetic


def test_overlay_uses_original_nm_counts_and_shared_checkboxes():
    s1, s2 = synthetic(), synthetic(amplitude=10000)
    s1.config = FitConfig(domain="eV", normalization="max", xmin=1.5, xmax=1.65)
    s1.result = fit_spectrum(s1)
    s2.name = "C3"
    s2.plot = False
    before = copy.deepcopy(s1.result)
    figure = Figure()
    ax, residual = draw_overlay(figure, [s1, s2], {"intensity": "raw"})
    assert residual is None
    assert len(ax.lines) == 1
    assert ax.get_xlabel() == "Wavelength (nm)"
    assert ax.get_ylabel() == "PL intensity (Counts)"
    assert np.array_equal(ax.lines[0].get_xdata(), s1.x)
    assert np.array_equal(ax.lines[0].get_ydata(), s1.y)
    assert len(ax.lines[0].get_xdata()) == len(s1.x)
    assert s1.result == before
    assert "C3" not in ax.get_legend_handles_labels()[1]


def test_overlay_normalizes_each_spectrum_without_changing_sources():
    spectra = [synthetic(), synthetic(amplitude=10000)]
    original = [s.y.copy() for s in spectra]
    ax, _ = draw_overlay(Figure(), spectra, {"intensity": "normalized"})
    assert len(ax.lines) == 2
    for s, line, raw in zip(spectra, ax.lines, original):
        assert line.get_ydata().max() == pytest.approx(1)
        assert np.allclose(line.get_ydata(), raw/raw.max())
        assert np.array_equal(s.y, raw)
    assert "I / Imax" in ax.get_ylabel()
    spectra[0].y[:] = 0
    with pytest.raises(ValueError, match="最大強度"):
        draw_overlay(Figure(), spectra, {"intensity": "normalized"})


def test_overlay_export_matches_selected_curves(tmp_path):
    spectra = [synthetic(), synthetic(amplitude=10000)]
    style = DEFAULT_OVERLAY | {"intensity": "normalized", "dpi": 100,
                               "width_cm": 15.24, "height_cm": 10.16}
    for extension in ("png", "jpg", "pdf", "svg"):
        path = tmp_path/f"overlay.{extension}"
        export_overlay(path, spectra, style)
        assert path.stat().st_size > 1000
    with Image.open(tmp_path/"overlay.png") as image:
        assert image.size == (600, 400)


def test_simultaneous_views_and_independent_export_choice(tmp_path):
    spectra = [synthetic(), synthetic(amplitude=10000)]
    figure = Figure()
    raw_ax, normalized_ax = draw_overlay(figure, spectra)
    assert len(figure.axes) == 2
    assert np.array_equal(raw_ax.lines[0].get_ydata(), spectra[0].y)
    assert normalized_ax.lines[0].get_ydata().max() == pytest.approx(1)
    style = DEFAULT_OVERLAY | {"dpi": 100}
    paths = export_overlay_files(tmp_path/"comparison.png", spectra, style)
    assert [p.name for p in paths] == ["comparison_intensity.png", "comparison_normalized.png"]
    assert all(p.exists() for p in paths)
    assert paths[0].read_bytes() != paths[1].read_bytes()
    for export_mode in ("raw", "normalized"):
        path = tmp_path/f"{export_mode}.png"
        assert export_overlay_files(path, spectra, style | {"export_mode": export_mode}) == [path]
        assert path.stat().st_size > 1000
    for export_mode in ("both", "current"):
        path = tmp_path/f"{export_mode}.png"
        outputs = export_overlay_files(path, spectra, style | {"export_mode": export_mode})
        assert [p.name for p in outputs] == [f"{export_mode}_intensity.png", f"{export_mode}_normalized.png"]
        assert all(p.stat().st_size > 1000 for p in outputs)
        assert not path.exists()
    # No partial pair should be written if one selected spectrum cannot be normalized.
    spectra[0].y[:] = 0
    with pytest.raises(ValueError, match="最大強度"):
        export_overlay_files(tmp_path/"invalid.png", spectra, style)
    assert not (tmp_path/"invalid_intensity.png").exists()
