"""Generate condition-trend examples from the existing fitted reference project.

Condition labels are the original display names, not inferred experimental groups.
"""
import copy
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from plstudio.data import load_project, save_project
from plstudio.exporting import export_trend_excel
from plstudio.gui import MainWindow, TRENDS, OVERLAY
from plstudio.trends import DEFAULT_TRENDS, export_trend_set, export_trends


def main():
    output = Path(__file__).resolve().parent.parent / "examples"
    spectra, style = load_project(output/"PL_reference_demo.plproj")
    settings = copy.deepcopy(DEFAULT_TRENDS)
    style["trends"] = settings
    # Filenames are the only known condition identifiers supplied by the user.
    for spectrum in spectra:
        spectrum.condition = spectrum.name
    save_project(output/"PL_condition_demo.plproj", spectra, style)
    export_trends(output/"PL_condition_overview.png", spectra, settings)
    export_trend_excel(output/"PL_condition_trends.xlsx", spectra, settings)
    separate = output/"condition_plots"
    separate.mkdir(exist_ok=True)
    export_trend_set(separate, spectra, settings)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_project_path(output/"PL_condition_demo.plproj")
    window.mode.setCurrentIndex(TRENDS)
    window.show()
    app.processEvents()
    window._draw()
    app.processEvents()
    window.grab().save(str(output/"UI_condition_trends.png"))
    window._maybe_save = lambda: True
    window.close()
    print(f"Created condition trend examples in {output}")


if __name__ == "__main__":
    main()
