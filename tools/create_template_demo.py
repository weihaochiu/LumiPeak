"""Create an editable per-figure preset, project, trend examples and UI screenshots."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from plstudio.data import save_project
from plstudio.gui import MainWindow, TRENDS
from plstudio.trends import export_trends


def main():
    output = Path(__file__).resolve().parent.parent / "examples"
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.load_project_path(output/"PL_overlay_demo.plproj")
    window.mode.setCurrentIndex(TRENDS)
    window.trend_panel.plot_type.setCurrentIndex(window.trend_panel.plot_type.findData("bar"))
    window.show()
    app.processEvents()
    window.open_figure_template()
    dialog = window.template_dialog
    dialog.widgets["line_width"].setValue(1.2)
    dialog.option_widgets["minor_ticks"].setChecked(True)
    dialog.option_widgets["panel_labels"].setChecked(True)
    dialog.option_widgets["legend_frame"].setChecked(False)
    dialog.apply(False)
    dialog.save_file(output/"PL_figure_template.json")
    app.processEvents()
    dialog.grab().save(str(output/"UI_figure_template.png"))
    dialog.tabs.setCurrentIndex(1)
    app.processEvents()
    dialog.grab().save(str(output/"UI_metric_availability.png"))
    dialog.close()
    app.processEvents()
    window.grab().save(str(output/"UI_trends_bar.png"))
    settings = window.trend_panel.settings()
    export_trends(output/"PL_trends_bar.png", window.spectra, settings)
    window.trend_panel.plot_type.setCurrentIndex(window.trend_panel.plot_type.findData("dot-line"))
    app.processEvents()
    window.grab().save(str(output/"UI_trends_dot_line.png"))
    export_trends(output/"PL_trends_dot_line.png", window.spectra, window.trend_panel.settings())
    save_project(output/"PL_template_demo.plproj", window.spectra, window._read_plot_inputs())
    window._maybe_save = lambda: True
    window.close()
    print(f"Created Figure Template examples in {output}")


if __name__ == "__main__":
    main()
