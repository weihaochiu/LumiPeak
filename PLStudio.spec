# Build with: python -m PyInstaller --noconfirm PLStudio.spec
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
from pathlib import Path
import pefile
import PySide6

datas = collect_data_files("plstudio", includes=["locales/*.json", "release_config.json"])
for package in ("lmfit", "asteval", "uncertainties"):
    datas += copy_metadata(package)

a = Analysis(["main.py"], pathex=[], binaries=[], datas=datas,
    hiddenimports=["scipy.special._ufuncs_cxx", "PySide6.QtNetwork"],
    hookspath=[], hooksconfig={"matplotlib": {"backends": ["QtAgg"]}},
    runtime_hooks=[], excludes=["tkinter", "IPython", "notebook", "pytest", "pandas", "sympy"],
    noarchive=False)

# Some host Python distributions ship an ICU library whose exports are version
# suffixed. Qt can instead import the unsuffixed Windows system ICU API. Never
# shadow that system DLL with an incompatible library from the build machine.
qtcore = pefile.PE(str(Path(PySide6.__file__).parent / "Qt6Core.dll"))
icu_imports = {symbol.name for dependency in qtcore.DIRECTORY_ENTRY_IMPORT
    if dependency.dll.lower() == b"icuuc.dll" for symbol in dependency.imports if symbol.name}
for destination, source, kind in list(a.binaries):
    if Path(destination).name.lower() == "icuuc.dll" and icu_imports:
        library = pefile.PE(source)
        exports = {symbol.name for symbol in library.DIRECTORY_ENTRY_EXPORT.symbols}
        if not icu_imports.issubset(exports):
            a.binaries.remove((destination, source, kind))
            print("Excluded incompatible host ICU; Qt will use the Windows system library")

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PL-Studio",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PL-Studio")
