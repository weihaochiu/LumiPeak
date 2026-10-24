"""Generate a reviewable project from a user-provided reference ZIP.

Usage: python tools/create_demo.py <archive.zip>
This is a demonstration of single-Gaussian fitting, not a physical model selection.
"""
import copy
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from plstudio.data import FitConfig, import_path, save_project
from plstudio.exporting import export_excel, export_origin_bundle
from plstudio.fitting import fit_spectrum
from plstudio.gui import MainWindow, TRENDS, OVERLAY
from plstudio.plotting import DEFAULT_STYLE, export_figure


def main():
    output = Path(__file__).resolve().parent.parent / "examples"
    output.mkdir(exist_ok=True)
    spectra, errors = import_path(sys.argv[1])
    if errors:
        raise ValueError(errors)
    seen = set()
    for spectrum in spectra:
        spectrum.plot = spectrum.digest not in seen
        seen.add(spectrum.digest)
        spectrum.result = fit_spectrum(spectrum)
        spectrum.config = FitConfig(**spectrum.result["config"])
        spectrum.notes = "示範：單峰 Gaussian + 常數背景。用於操作驗證，尚未進行物理模型判定。"
    style = copy.deepcopy(DEFAULT_STYLE)
    style.update(title="Steady-state PL", width_cm=17.8, height_cm=12,
                 raw=True, fit=False, line_width=1.5)
    save_project(output/"PL_reference_demo.plproj", spectra, style)
    export_excel(output/"PL_reference_results.xlsx", spectra)
    export_origin_bundle(output/"PL_reference_Origin.zip", spectra)
    export_figure(output/"PL_reference_spectra.png", [s for s in spectra if s.plot], style)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.spectra = spectra
    window.current_id = next(s.id for s in spectra if s.filename == "AS.txt")
    window.project_path = str(output/"PL_reference_demo.plproj")
    window.plot_settings = style
    window._refresh_tree()
    window._load_controls()
    window._load_plot_inputs()
    window._refresh_tables()
    window._update_title()
    window.show()
    app.processEvents()
    window._draw()
    app.processEvents()
    window.grab().save(str(output/"UI_analysis.png"))
    window.mode.setCurrentIndex(OVERLAY)
    app.processEvents()
    window.grab().save(str(output/"UI_plotting.png"))
    window.dirty = False
    window._maybe_save = lambda: True
    window.close()
    print(f"Created demo outputs in {output}")


if __name__ == "__main__":
    main()
