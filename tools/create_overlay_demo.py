"""Generate raw/normalized overlays and a UI preview with C3 unchecked."""
import copy
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from plstudio.data import load_project, save_project
from plstudio.gui import MainWindow, TRENDS, OVERLAY
from plstudio.overlay import DEFAULT_OVERLAY, export_overlay, export_overlay_files


def main():
    output = Path(__file__).resolve().parent.parent / "examples"
    spectra, style = load_project(output/"PL_condition_demo.plproj")
    for spectrum in spectra:
        if spectrum.filename == "C3.txt":
            spectrum.plot = False
        spectrum.trend_include = spectrum.plot
    settings = copy.deepcopy(DEFAULT_OVERLAY)
    style["overlay"] = settings
    save_project(output/"PL_overlay_demo.plproj", spectra, style)
    export_overlay(output/"PL_overlay_combined.png", spectra, settings)
    export_overlay_files(output/"PL_overlay.png", spectra, settings)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_project_path(output/"PL_overlay_demo.plproj")
    window.mode.setCurrentIndex(OVERLAY)
    window.show()
    app.processEvents()
    window._draw()
    app.processEvents()
    window.grab().save(str(output/"UI_overlay_both.png"))
    window.mode.setCurrentIndex(TRENDS)
    app.processEvents()
    window.grab().save(str(output/"UI_trends_C3_unchecked.png"))
    window._maybe_save = lambda: True
    window.close()
    print(f"Created raw/normalized overlay examples in {output}")


if __name__ == "__main__":
    main()
