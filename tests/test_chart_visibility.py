"""Regressions for data that existed in Figures but was clipped out of the UI."""
import numpy as np

from PySide6.QtGui import QImage

from plstudio.gui import ANALYSIS, TRENDS, OVERLAY
from tests.test_core import synthetic
from tests.test_gui import app, window, wait_worker


def assert_visible_plots(window, app):
    group = window.chart_group
    app.processEvents()
    assert group.cards
    for card in group.cards:
        canvas = card.canvas
        # isVisible() alone is insufficient: a visible widget can be fully
        # clipped by a 16 x 16 parent, as happened after rebuilding this group.
        assert group.panel.width() >= card.geometry().right()+1
        assert group.panel.height() >= card.geometry().bottom()+1
        group.ensureWidgetVisible(canvas)
        app.processEvents()
        visible = canvas.visibleRegion().boundingRect()
        assert visible.width() > 100 and visible.height() > 100
        assert canvas.isVisible() and card.navigation.isVisible()
        assert any(ax.lines for ax in canvas.figure.axes)
        # Inspect what the scroll viewport displays, not a direct canvas grab
        # which would bypass parent clipping and conceal this regression.
        image = group.viewport().grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        pixels = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
        rgb = pixels[:, :image.width()*4].reshape(image.height(), image.width(), 4)[:, :, :3].astype(int)
        assert np.count_nonzero((rgb.max(axis=2)-rgb.min(axis=2) > 60) & (rgb.min(axis=2) < 150)) > 5


def test_import_fit_and_rebuild_all_three_pages_show_painted_charts(window, app, tmp_path):
    paths = []
    for i, center in enumerate((805, 815)):
        path = tmp_path/f"sample_{i}.txt"
        path.write_bytes(synthetic(center=center).raw)
        paths.append(str(path))
    window.import_paths(paths)
    assert len(window.spectra) == 2
    assert_visible_plots(window, app)
    window.tree.selectAll()
    window.start_fit("batch")
    wait_worker(window, app)
    assert all(sample.result and sample.result["success"] for sample in window.spectra)
    for mode in (ANALYSIS, TRENDS, OVERLAY, ANALYSIS, OVERLAY, TRENDS):
        window.mode.setCurrentIndex(mode)
        window._draw()
        assert_visible_plots(window, app)


def test_hidden_then_rebuilt_group_recovers_on_show(window, app):
    from tests.test_gui import populate
    populate(window)
    group = window.chart_group
    group.hide()
    window._draw()
    app.processEvents()
    group.show()
    assert_visible_plots(window, app)
