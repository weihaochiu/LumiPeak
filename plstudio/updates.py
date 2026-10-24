"""Bounded background checks against public GitHub Releases."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__
from .i18n import tr

CONFIG = json.loads((Path(__file__).parent / "release_config.json").read_text("utf-8"))


def repository():
    value = CONFIG.get("repository", "")
    return value if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value) else ""


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    download_url: str


def parse_release(data, current=__version__, repo=None):
    repo = repo or repository()
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name", "")
    if not isinstance(tag, str):
        return None
    try:
        latest = Version(tag.removeprefix("v"))
        if latest.is_prerelease or latest.is_devrelease or latest <= Version(current):
            return None
    except InvalidVersion:
        return None
    # Only a real installer asset on this repository is offered for download.
    assets = data.get("assets") or []
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") != CONFIG["installer_asset"]:
            continue
        url = asset.get("browser_download_url", "")
        if not isinstance(url, str):
            continue
        parsed = urlparse(url)
        if (parsed.scheme == "https" and parsed.netloc == "github.com"
                and parsed.path.startswith(f"/{repo}/releases/download/")
                and parsed.path.endswith("/" + CONFIG["installer_asset"])):
            return Release(str(latest), str(data.get("body") or "")[:12000], url)
    raise ValueError(tr("新版尚未提供 Windows 安裝檔。"))


def check_latest(repo=None, opener=urlopen):
    repo = repo or repository()
    if not repo:
        raise ValueError(tr("尚未設定 GitHub 更新來源。"))
    request = Request(f"https://api.github.com/repos/{repo}/releases/latest", headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"PL-Studio/{__version__}",
        "X-GitHub-Api-Version": "2022-11-28"})
    with opener(request, timeout=8) as response:
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError(tr("更新資訊過大。"))
    return parse_release(json.loads(raw), repo=repo)


class UpdateChecker(QObject):
    checked = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.reply = None
        self.buffer = bytearray()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.cancel)

    def start(self):
        if self.reply is not None:
            return
        request = QNetworkRequest(QUrl(f"https://api.github.com/repos/{repository()}/releases/latest"))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", f"PL-Studio/{__version__}".encode("ascii"))
        request.setTransferTimeout(8000)
        self.buffer.clear()
        self.reply = self.manager.get(request)
        self.reply.readyRead.connect(self._read)
        self.reply.finished.connect(self._finished)
        self.timer.start(9000)

    def cancel(self):
        if self.reply is not None:
            self.reply.abort()

    def _read(self):
        self.buffer.extend(bytes(self.reply.readAll()))
        if len(self.buffer) > 512 * 1024:
            self.cancel()

    def _finished(self):
        self.timer.stop()
        reply = self.reply
        self._read()
        self.reply = None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError(reply.errorString())
            if len(self.buffer) > 512 * 1024:
                raise ValueError(tr("更新資訊過大。"))
            self.checked.emit(parse_release(json.loads(bytes(self.buffer))))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            reply.deleteLater()
