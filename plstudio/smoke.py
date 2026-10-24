"""Exercise a frozen Windows build without a separately installed Python."""
from __future__ import annotations

import json
import os
from pathlib import Path


def run(output):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import numpy as np
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from . import __version__, gui, i18n
    from .data import load_project, parse_spectrum, save_project
    from .exporting import export_excel
    from .fitting import fit_spectrum
    from .plotting import DEFAULT_STYLE, export_figure

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("PL Studio smoke test")
    app.setOrganizationName("PLStudio")
    settings = QSettings(str(output / "preferences.ini"), QSettings.Format.IniFormat)
    i18n.preferences = gui.preferences = lambda: settings
    i18n.set_language("zh_TW", persist=False)
    x = np.linspace(730, 880, 301)
    y = 50 + 1200*np.exp(-0.5*((x-805)/9)**2)
    raw = "\n".join(f"{a:.8f}\t{b:.8f}" for a, b in zip(x, y)).encode()
    spectrum = parse_spectrum(raw, "Synthetic.txt")
    spectrum.result = fit_spectrum(spectrum)
    assert spectrum.result["success"]
    assert abs(spectrum.result["peaks"][0]["center"]-805) < .01
    project = output / "smoke.plproj"
    save_project(project, [spectrum], DEFAULT_STYLE)
    loaded, _ = load_project(project)
    assert loaded[0].raw == spectrum.raw
    export_excel(output / "smoke.xlsx", loaded)
    export_figure(output / "smoke.png", loaded, DEFAULT_STYLE)
    window = gui.MainWindow()
    window.update_timer.stop()
    try:
        window.spectra = loaded
        window.current_id = loaded[0].id
        window._refresh_tree()
        window._load_controls()
        window._refresh_tables()
        window.show()
        for code, expected in (("zh_TW", "光譜分析"), ("en", "Spectrum analysis")):
            window.change_language(code)
            window._draw()
            app.processEvents()
            assert window.mode.tabText(0) == expected
            assert window.grab().save(str(output / f"interface_{code}.png"))
        window.open_figure_template()
        app.processEvents()
        assert window.template_dialog.grab().save(str(output / "template_en.png"))
    finally:
        window._maybe_save = lambda: True
        window.template_dialog.close()
        window.close()
        app.processEvents()
    (output / "result.json").write_text(json.dumps({"version": __version__, "passed": True,
        "checks": ["import", "fit", "project_roundtrip", "excel", "figure", "zh_TW", "en", "template"]},
        indent=2), encoding="utf-8")
    return 0
