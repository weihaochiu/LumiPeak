"""Application translations, independent of project data and scientific keys."""
from __future__ import annotations

import json
import re
import string
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings, QSignalBlocker, QLibraryInfo, QTranslator

CATALOG = json.loads((Path(__file__).parent / "locales" / "en.json").read_text("utf-8"))
_language = "zh_TW"
_qt_translator = None


def preferences():
    return QSettings("PLStudio", "PLStudio")


def language():
    return _language


def tr(text):
    """Translate only application-owned source messages, never arbitrary data."""
    return CATALOG.get(text, text) if _language == "en" else text


@lru_cache(maxsize=1)
def _saved_patterns():
    patterns = []
    for source, english in CATALOG.items():
        for template in (source, english):
            fields, chunks = [], []
            for literal, field, _, _ in string.Formatter().parse(template):
                chunks.append(re.escape(literal))
                if field is not None:
                    fields.append(field)
                    chunks.append("(.*?)")
            if fields:
                patterns.append((source, re.compile("".join(chunks), re.DOTALL), fields))
    return patterns


def saved_message(text):
    """Render application warnings stored by an earlier language/version.

    Only complete catalog messages match; captured parameter names and user
    values are copied verbatim. The saved result itself is never modified.
    """
    if text in CATALOG:
        return tr(text)
    for source, english in CATALOG.items():
        if text == english:
            return tr(source)
    for source, pattern, fields in _saved_patterns():
        match = pattern.fullmatch(text)
        if match:
            values = [""] * (max(map(int, fields)) + 1)
            for field, value in zip(fields, match.groups()):
                values[int(field)] = value
            return tr(source).format(*values)
    return text


def set_language(value, persist=True):
    global _language, _qt_translator
    if value not in ("zh_TW", "en"):
        raise ValueError("Unsupported interface language")
    _language = value
    if persist:
        preferences().setValue("language", value)
    # Translate Qt's standard buttons and dialogs as well as our own strings.
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        if _qt_translator is not None:
            app.removeTranslator(_qt_translator)
        _qt_translator = QTranslator(app)
        if value == "zh_TW" and _qt_translator.load(
                "qtbase_zh_TW", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(_qt_translator)


def initialize_language():
    fallback = "zh_TW" if QLocale.system().name().startswith("zh") else "en"
    saved = preferences().value("language", fallback)
    set_language(saved if saved in ("zh_TW", "en") else fallback, persist=False)


def retranslate_widgets(root):
    """Refresh presentation text while preserving input, selections and item data.

    Canonical text is stored per object/property so switching is reversible even
    when two Chinese labels share an English translation. Signals are blocked:
    changing a combo's display text must never modify its scientific settings.
    """
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QGroupBox, QLabel,
                                  QLineEdit, QTabBar, QTableWidget, QTreeWidget, QWidget)
    reverse = {v: k for k, v in CATALOG.items()}

    def update(obj, key, current, setter):
        prop = "i18n_" + key
        previous = obj.property(prop)
        if previous and current == previous[1]:
            source = previous[0]
        else:
            source = reverse.get(current, current)
        rendered = tr(source)
        obj.setProperty(prop, [source, rendered])
        if current != rendered:
            setter(rendered)

    for obj in [root, *root.findChildren(QWidget), *root.findChildren(QAction)]:
        blocker = QSignalBlocker(obj)
        update(obj, "tooltip", obj.toolTip(), obj.setToolTip)
        update(obj, "status_tip", obj.statusTip(), obj.setStatusTip)
        if isinstance(obj, QWidget):
            update(obj, "title", obj.windowTitle(), obj.setWindowTitle)
        if isinstance(obj, (QAbstractButton, QLabel, QAction)):
            update(obj, "text", obj.text(), obj.setText)
        if isinstance(obj, QGroupBox):
            update(obj, "group", obj.title(), obj.setTitle)
        if isinstance(obj, QLineEdit):
            update(obj, "placeholder", obj.placeholderText(), obj.setPlaceholderText)
        if isinstance(obj, QComboBox):
            for i in range(obj.count()):
                update(obj, f"item_{i}", obj.itemText(i), lambda text, i=i: obj.setItemText(i, text))
        if isinstance(obj, QTabBar):
            for i in range(obj.count()):
                update(obj, f"tab_{i}", obj.tabText(i), lambda text, i=i: obj.setTabText(i, text))
        if isinstance(obj, QTableWidget):
            for i in range(obj.columnCount()):
                item = obj.horizontalHeaderItem(i)
                if item:
                    update(obj, f"header_{i}", item.text(), item.setText)
        if isinstance(obj, QTreeWidget):
            for i in range(obj.columnCount()):
                update(obj, f"header_{i}", obj.headerItem().text(i),
                       lambda text, i=i: obj.headerItem().setText(i, text))
        del blocker
