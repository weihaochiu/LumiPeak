# OriginPro 2025 圖片設定對照

需求日期：2026-10-24（Asia/Taipei）。本次完成原始碼改造，尚未打包或發佈。

## 官方依據

- [Origin User Guide 2025，官方 PDF](https://d2mvzyuse3lwjc.cloudfront.net/pdfs/Origin2025_Documentation/English/Origin_User_Guide_2025_E.pdf)
- 已下載至 `test_output/origin2025/Origin_User_Guide_2025_E.pdf`，17,330,032 bytes，共 473 頁，封面標示 `UserGuide_2025`。
- SHA-256：`22d4deb6e5b32575c7f7c0e2437f8041ed39183563efbe5d9ae3ccb5bd95f938`。
- 第 11 章，印刷頁 225–226（PDF 第 231–232 頁）：Plot Details 的 Page → Layer → Plot 階層與依物件切換屬性分頁。
- 印刷頁 233–235（PDF 第 239–241 頁）：Axis Dialog 的 Horizontal／Vertical 選取與設定分頁。
- [官方線上圖形自訂說明](https://docs.originlab.com/user-guide/customizing-graphs/)僅作輔助；版本依據以已下載的 2025 PDF 為準。

官方 PDF 保留在本機測試資料夾，未納入原始碼發佈；本文件只記錄實作對照。

## 已實作的操作

| 設定 | LumiPeak 行為 |
|---|---|
| Plot Details | 左側物件樹選取 Page、Layer、Plot；中央依選取物件顯示設定分頁；右側顯示預覽。 |
| Page | Print/Dimensions、Plot Content、Layers、Legends/Titles、Export；Common Display 保留全圖共用設定。 |
| Layer | Background、Size、Display；位置使用 Left／Top／Width／Height 頁面百分比。可分別顯示／隱藏圖層。 |
| Plot | Line、Symbol、長條 Pattern；個別顏色、線型、線寬、透明度與符號。可分別顯示／隱藏曲線。 |
| Axis Dialog | 選取圖層後按 Axes...；或在預覽雙擊軸線／刻度／軸標題開啟。 |
| Axis 分頁 | Scale、Tick Labels、Title、Grids、Line and Ticks、Special Ticks、Reference Lines。 |
| 軸選取 | Bottom（下 X）、Top（上 X）、Left（左 Y）、Right（右 Y）；Ctrl 多選。四邊各自保存範圍、尺度、刻度、標題、顏色、字級、線寬、格線、軸線及刻度標籤顯示狀態。 |
| 預覽與套用 | 預覽只修改草稿；Apply 同步主畫面；OK 套用後關閉；Cancel 關閉，重新開啟回到最近套用值。已按 Apply 的變更會保留。 |
| 保存 | 沿用 v2 JSON 模板及專案保存；保留舊模板、三種圖型各自保存與載入套用流程。 |
| 輸出 | 預覽、單張輸出、資料夾批次圖片輸出共用格式渲染。疊圖 raw／normalized 和趨勢指標使用各自圖層識別碼。 |

曲線設定使用資料識別碼和曲線角色（raw、fit、分峰、background、residual），重新命名或排除其他資料不會把格式套至別筆資料。格式設定不修改原始數據與擬合數值。

## 尚未達成的部分

此版依 2025 官方手冊重建目前 PL 工作流會用到的 2-D 設定。**尚不能稱為與 OriginPro 2025 完全相同。**

- 介面採 PySide6，包含並排預覽，沒有逐像素複製 Origin 的原生 Windows 介面。
- 尚無 Origin 原生程式的逐項操作比對證據。
- 尚未實作 Axis Breaks、Rug、完整 Rescale 模式、LabTalk 自訂刻度運算、資料點級屬性、分組遞增清單、Speed Mode、3-D 專用設定與 Origin 全部輸出格式。
- 不讀寫 Origin `.oggu`／`.oth` 二進位模板；此設定不會自動轉入 Origin `.opju` 匯出。
- 個別曲線格式以資料識別碼保存；套用到全新資料時，不會自動按順序對應不同資料的識別碼。

## 驗證

- `tests/test_origin_format.py`：10 項通過，含作用範圍、重新命名／篩選後一致性、SVG 匯出、X／Y 軸獨立性、raw／fit 角色、圖層位置、無效設定、套用／取消與模板保存。
- `tests/test_templates.py` 與 `tests/test_applicability.py`：19 項通過。
- `tests/test_release.py`：14 項通過，含中英文切換保留編輯與翻譯完整性。
- 中英文畫面與官方參照頁截圖保存在 `test_output/origin2025/`。

初版專項回歸：`tests/test_origin_format.py tests/test_templates.py tests/test_applicability.py tests/test_release.py tests/test_image_export.py`，54 項通過（110.33 秒）。完整套件執行尚未取得完成結果，不列為通過。

選單整合另有 `tests/test_menus.py` 3 項通過（11.78 秒）；自動執行時停用啟動更新請求，並對儲存確認對話框提供測試回覆。合計 57 項相關測試通過；未將中止的完整套件列為通過。


## 2026-10-24 再次檢查與修正

| 檢查項目 | 介面與繪圖 | 保存與輸出 | 結果 |
|---|---|---|---|
| 四邊座標軸分開選取 | Bottom／Top／Left／Right 四個選項，可由預覽雙擊對應軸進入 | 每圖層的 `axes` 以四個邊名保存；舊 `x`／`y` 設定仍可讀取 | 已實作 |
| 四邊作用範圍 | 上、右軸有自己的刻度範圍與尺度，不修改下、左軸的資料變換；字級、線寬、顏色、標籤、格線分開套用 | 四種圖片格式使用同一渲染流程 | 已實作與圖像檢查 |
| 獨立圖與圖組 | 各 DATA、各趨勢指標、raw／normalized 疊圖各自建立 Figure；UI 以固定尺寸畫布排列，空間不足時捲動 | 個別圖尺寸以 cm 保存；輸出 DPI 僅用於檔案；圖數和視窗寬度不縮放圖 | 已實作 |
| 單張 Page 設定 | 圖片設定樹下每張 Page 可設定寬、高、DPI、字型、字級、線寬、方向、背景 | `chart_styles` 隨 JSON 模板和專案保存，匯出讀取同一設定 | 已實作 |
| 套用到每張圖 | 將選取圖的頁面、圖層、四邊軸和曲線格式套到目前圖組或全部圖型 | 曲線按角色對應，保留各 DATA；可選是否包含範圍與標題，未勾選時保留目標圖原有內容 | 已實作 |
| 逐張匯出入口 | 全部圖片匯出逐 DATA、兩張疊圖、每個勾選趨勢指標輸出；趨勢總覽匯出採資料夾 | 疊圖 both／current 在同時顯示兩圖時輸出兩檔；圖片設定預覽逐張輸出；每張圖的工具列可另存該張並使用設定 DPI | 已實作 |
| 共用操作與資料 | 勾選、名稱、Condition、順序、擬合結果的既有工作流保留；光譜分析仍顯示目前編輯資料，圖片設定中逐筆顯示正式 PL 圖 | 格式複製不修改原始數據、擬合值和資料身份 | 已加入測試 |

新的圖組不再以一個 Figure 的多個 subplot 擠進固定寬高。底層 `draw_trends`／`draw_overlay` 保留既有單 Figure API，供舊程式呼叫；本程式的圖組與匯出 UI 已走獨立圖流程。

再次檢查的官方補充依據：[Tick Labels](https://docs.originlab.com/origin-help/axesref-ticklabels/) 的四邊設定與 [Scale](https://docs.originlab.com/origin-help/axesref-scale/) 的獨立右 Y 尺度。線上內容可能隨新版變動，2025 版本依據仍以已下載 PDF 為準。

這份對照表不代表完整 OriginPro 功能或逐像素一致性已驗證；未實作項目仍列在上方，不能因本次回歸通過就標為完全相同。


### 本次最終驗證

- 最新全套回歸：114 項通過，108.80 秒；另加的跨全部圖型套用測試 1 項通過，8.91 秒。兩次均無略過或失敗，後續相容性專項另列。
- 圖組專項另跑 7 項通過，含圖數／視窗大小不改變畫布尺寸、字級與繪圖區比例；個別尺寸與 DPI、四邊軸格式套用、目標範圍與標題保留、單張工具列儲存、X 軸可選連結、每圖基本字級實際生效。跨全部圖型套用測試為之後追加的一項。
- 原始碼 smoke-test 8 項通過，涵蓋匯入、擬合、專案、Excel、圖片、中英文及設定視窗。
- 已檢視最終中英文圖片設定與四邊軸視窗，以及四色、不同尺度／範圍／方向的實際出圖；畫面位於 `test_output/origin2025/`。
- 回歸期間停用啟動更新網路請求，並為儲存確認對話框提供測試回覆；這些測試替身不寫入正式程式。
- 另外修正主視窗關閉時的生命週期：釋放 Qt 視窗、停止自動儲存，並取消已隱藏或替換畫布的待執行重繪，避免累積背景工作。
- 證據：`regression.xml`、`verification_summary.json`、`smoke/result.json`。本次沒有重打安裝包或發佈。

最終相容性補查：修正舊多面板數字編號在拆成獨立圖後的樣式歸屬，raw／normalized 及各趨勢指標按原面板設定對應。相關最新專項 43 項通過（44.36 秒），含舊設定逐張匯出、四邊軸、圖組、模板及四種圖片格式；證據 `chart_regression.xml`。這 43 項包含與全套重疊項目及追加相容性測試，不與全套直接相加。
