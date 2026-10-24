from __future__ import annotations

from .i18n import tr

import copy
import hashlib
import json
import os
import re
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

HC = 1239.8419843320026  # eV nm
MAX_MEMBER = 32 * 1024 * 1024
MAX_ARCHIVE = 256 * 1024 * 1024
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?"
ROW = re.compile(rf"^\s*({NUMBER})[\t ,;]+({NUMBER})\s*$")


@dataclass
class FitConfig:
    domain: str = "nm"
    jacobian: bool = False
    normalization: str = "none"
    xmin: float | None = None
    xmax: float | None = None
    excluded: list[list[float]] = field(default_factory=list)
    background: str = "constant"
    peaks: list[str] = field(default_factory=lambda: ["Gaussian"])
    parameters: dict = field(default_factory=dict)
    shared: list[str] = field(default_factory=list)
    starts: int = 3


@dataclass
class Spectrum:
    filename: str
    name: str
    x: np.ndarray
    y: np.ndarray
    raw: bytes
    metadata: list[list[str]] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    plot: bool = True
    config: FitConfig = field(default_factory=FitConfig)
    result: dict | None = None
    history: list[dict] = field(default_factory=list)
    notes: str = ""
    condition: str = ""
    trend_include: bool = True

    @property
    def digest(self):
        return hashlib.sha256(self.raw).hexdigest()


def parse_spectrum(raw: bytes, filename: str) -> Spectrum:
    if len(raw) > MAX_MEMBER:
        raise ValueError(tr("單一檔案超過 32 MB。"))
    for encoding in ("utf-8-sig", "utf-16", "cp950", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeError:
            continue
    else:
        raise ValueError(tr("無法辨識文字編碼。"))
    rows, metadata = [], []
    for line in text.splitlines():
        match = ROW.fullmatch(line)
        if match:
            rows.append([float(match[1]), float(match[2])])
        elif line.strip() and line.strip() not in ("--",):
            clean = line.rstrip("\t -")
            key, sep, value = clean.partition(":")
            metadata.append([key.strip(), value.strip() if sep else ""])
    if len(rows) < 10:
        raise ValueError(tr("找不到至少 10 列雙欄數值；請使用波長、強度兩欄資料。"))
    array = np.asarray(rows, dtype=float)
    if not np.isfinite(array).all() or np.any(array[:, 0] <= 0):
        raise ValueError(tr("波長必須為正數，且資料不得含非有限值。"))
    array = array[np.argsort(array[:, 0], kind="stable")]
    if np.any(np.diff(array[:, 0]) <= 0):
        raise ValueError(tr("發現重複波長；請先確認來源資料。"))
    return Spectrum(filename, Path(filename).stem, array[:, 0], array[:, 1], raw, metadata)


def import_path(path: str | Path) -> tuple[list[Spectrum], list[str]]:
    path = Path(path)
    spectra, errors = [], []
    if path.suffix.lower() != ".zip":
        return [parse_spectrum(path.read_bytes(), path.name)], []
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()
                   and Path(m.filename).suffix.lower() in (".txt", ".csv", ".dat", ".tsv")]
        if sum(m.file_size for m in members) > MAX_ARCHIVE:
            raise ValueError(tr("ZIP 解壓後的資料總量超過 256 MB。"))
        for member in members:
            try:
                if member.file_size > MAX_MEMBER:
                    raise ValueError(tr("檔案超過 32 MB"))
                spectra.append(parse_spectrum(archive.read(member), member.filename))
            except Exception as exc:
                errors.append(f"{member.filename}: {exc}")
    if not members:
        raise ValueError(tr("ZIP 內沒有支援的雙欄文字檔。"))
    return spectra, errors


def transformed(spectrum: Spectrum, config: FitConfig, crop=True):
    x, y = spectrum.x.copy(), spectrum.y.copy()
    if config.domain == "eV":
        if config.jacobian:
            y = y * x**2 / HC
        x = HC / x
        order = np.argsort(x)
        x, y = x[order], y[order]
    elif config.domain != "nm":
        raise ValueError(tr("未知座標單位。"))
    # Normalization is defined over the full acquired interval, before cropping.
    if config.normalization == "max":
        scale = float(np.max(np.abs(y)))
    elif config.normalization == "area":
        scale = float(np.trapezoid(y, x))
    else:
        scale = 1.0
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError(tr("歸一化分母必須為正數。"))
    y /= scale
    if crop:
        mask = np.ones(x.size, dtype=bool)
        if config.xmin is not None:
            mask &= x >= config.xmin
        if config.xmax is not None:
            mask &= x <= config.xmax
        if config.xmin is not None and config.xmax is not None and config.xmin >= config.xmax:
            raise ValueError(tr("擬合起點必須小於終點。"))
        for lo, hi in config.excluded:
            if lo >= hi:
                raise ValueError(tr("遮罩區間起點必須小於終點。"))
            mask &= ~((x >= lo) & (x <= hi))
        x, y = x[mask], y[mask]
        if x.size < 10:
            raise ValueError(tr("選取區間至少需要 10 個有效資料點。"))
    return x, y


def intensity_label(config: FitConfig):
    if config.normalization != "none":
        return "Normalized PL (a.u.)"
    if config.domain == "eV" and config.jacobian:
        return "PL spectral density (converted units / eV)"
    return "PL intensity (Counts)"


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean_json(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(clean_json(value), ensure_ascii=False, indent=2,
                                    allow_nan=False), encoding="utf-8")


def save_project(path, spectra: list[Spectrum], plot_settings: dict):
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    items = []
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for spectrum in spectra:
                record = {k: v for k, v in asdict(spectrum).items() if k != "raw"}
                record["trend_include"] = spectrum.plot  # Legacy compatibility mirror.
                record["sha256"] = spectrum.digest
                items.append(clean_json(record))
                archive.writestr(f"raw/{spectrum.id}.txt", spectrum.raw)
            archive.writestr("project.json", json.dumps(
                {"schema": 1, "spectra": items, "plot_settings": plot_settings},
                ensure_ascii=False, allow_nan=False))
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def load_project(path):
    with zipfile.ZipFile(path) as archive:
        if sum(m.file_size for m in archive.infolist()) > MAX_ARCHIVE:
            raise ValueError(tr("專案解壓後超過 256 MB。"))
        manifest = json.loads(archive.read("project.json"))
        if manifest.get("schema") != 1:
            raise ValueError(tr("不支援的專案版本。"))
        spectra = []
        for record in manifest["spectra"]:
            raw = archive.read(f"raw/{record['id']}.txt")
            if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError(tr("原始檔案完整性檢查失敗。"))
            spectrum = parse_spectrum(raw, record["filename"])
            # Raw bytes are authoritative; don't trust cached x/y in the manifest.
            for key in ("id", "name", "plot", "result", "history", "notes", "condition", "trend_include"):
                if key in record:
                    setattr(spectrum, key, copy.deepcopy(record[key]))
            # One shared checkbox drives all comparison plots. Old projects may
            # contain a separate trend selection; the visible main checkbox wins.
            spectrum.trend_include = spectrum.plot
            spectrum.config = FitConfig(**record["config"])
            spectra.append(spectrum)
        if len({s.id for s in spectra}) != len(spectra):
            raise ValueError(tr("專案包含重複的資料識別碼。"))
        return spectra, manifest.get("plot_settings", {})
