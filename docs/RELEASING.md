# Windows release guide / Windows 發佈說明

目前狀態：自動發佈工作流程已啟用，首個正式版 [v0.5.0](https://github.com/weihaochiu/LumiPeak/releases/tag/v0.5.0) 已發佈。執行紀錄：[Windows build and release](https://github.com/weihaochiu/LumiPeak/actions/runs/40064721085)。

## First publication / 首次發佈

1. Create an empty public GitHub repository. Configure its address:

   ```powershell
   .\.venv\Scripts\python.exe tools/configure_release.py --repository YOUR_NAME/PL-Studio
   ```

   This updates both READMEs and the update source bundled with the application.
   此步驟會同步設定中英文說明的下載按鈕，以及程式內的版本檢查來源。

2. Source-code license terms have not been selected. The owner can add a LICENSE file separately.
   原始碼授權尚未選定，可由專案擁有者另外補上 LICENSE。

3. Install build requirements and Inno Setup 6+:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
   powershell -ExecutionPolicy Bypass -File tools/build_windows.ps1
   ```

   Optional: `-Iscc 'C:\path\to\ISCC.exe'`. The installer is `release/PL-Studio-Setup.exe`.
   安裝版包含 Python 與套件，使用者不需要安裝開發環境。

4. Test the installer on Windows 10 / 11 x64, including a computer without Python: startup, both languages, import, fitting, save/reopen, image/Excel export, update check and uninstall. The installer defaults to per-user installation and does not require administrator privileges.
   正式公開前，在未安裝 Python 的 Windows 電腦測試上述流程。此安裝版採目前使用者安裝。

5. Push the complete source to `main`. Changes to `plstudio/__init__.py` trigger the Windows workflow: it tests the source, builds an installer, calculates SHA-256, and creates the matching version tag and Release if that release does not already exist. Alternatively push an explicit tag matching `plstudio.__version__`, for example `v0.5.0`. GitHub Actions must be enabled. A manually triggered run only uploads a build artifact.
   首次推送原始碼或在 main 更新程式版本後，工作流程會建立對應的 Release；也可推送一致的版本標籤。既有 Release 的安裝檔不會被覆蓋。手動執行僅產生測試安裝檔。

## Subsequent versions / 後續版本

- Update `plstudio/__init__.py` and the version references in documentation and `installer/PLStudio.iss`.
- Push the version change to `main` or push a matching version tag. Keep the installer asset name **PL-Studio-Setup.exe** unchanged; README buttons and update checks depend on it.
- Startup checks use the latest published stable Release. Drafts, prereleases and versions no newer than the installed version are excluded.
- A newer Release without the expected installer is not offered as an update. Manual checks display the problem; startup failures stay quiet.
- Update release notes for both language audiences. The application displays the Release body as provided by the maintainer.
- Users select Download, Later or Skip. The application never overwrites itself while it is running.

後續更新請同步提高版本、推送版本標籤，並維持安裝檔名稱。更新摘要使用 GitHub Release 原文，建議維護者以中英文撰寫。

## Included source / 公開內容

The ignore rules exclude virtual environments, build outputs, recovery files, logs and local experimental examples. They retain the source, tests, documentation and reusable plot template. Existing local measurements are preserved on disk.

`.gitignore` 排除本機環境、建置檔、復原檔、日誌與實驗示範輸出；既有資料仍留在本機。第一次推送前請檢查實際提交內容。
