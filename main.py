"""PL Studio desktop entry point."""
import sys
import os
import traceback
from pathlib import Path


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
            from plstudio.smoke import run
            sys.exit(run(sys.argv[2]))
        else:
            from plstudio.gui import launch
            sys.exit(launch())
    except Exception:
        detail = traceback.format_exc()
        log = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PLStudio" / "PL_error.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(detail, encoding="utf-8")
        except OSError:
            pass
        if sys.argv[1:2] == ["--smoke-test"]:
            if sys.stderr:
                sys.stderr.write(detail)
            sys.exit(1)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication([])
            from plstudio.i18n import initialize_language, tr
            initialize_language()
            QMessageBox.critical(None, tr("PL Studio 啟動失敗"),
                tr("錯誤紀錄：{0}\n\n{1}").format(log, detail[-1800:]))
        except Exception:
            if sys.stderr:
                sys.stderr.write(detail)
        sys.exit(1)
