# 任務 C 交接規格：專業協會活動掃描（給 Claude Code）

狀態：正式版。2026-10-22 由 Muse 推送至本 repo；追蹤 issue 為本 repo issue #1。

## 任務

每週掃描四個專業協會的官方活動頁，找出未來 6 週內、免費、且與 Rene 背景相關的活動，產出報告。只查詢整理，絕不代為報名。

## 背景（給 Claude 的最少必要資訊）

- Rene：多倫多 MedTech 產業 Disposable Device Technician；ASQ CSSGB 持證人；OACETT、OSPE、CTTAM 會員；OACETT C.Tech. 申請中；P.Eng（PEO）路徑規劃中；職涯目標 MedTech R&D 或 AI engineering。
- 費用偏好是硬規則：只列免費場次，付費一律不列（可在報告的備查節提及相關但付費者）。

## 來源（全部公開，不需登入；不要嘗試任何登入）

1. ASQ：https://asq.org/conferences ＋ 會員行事曆 https://my.asq.org/events/calendar
   - 行事曆不需登入即可瀏覽（已驗證，約 150 筆動態刊登）。清單不顯示價格，相關活動必須逐場開詳情頁核價；詳情頁未標示價格者不可列為免費。
   - 注意：行事曆是動態 JS 頁面，需要能渲染的抓取方式；若你的環境抓不到，回報 Muse，不要用搜尋摘要硬湊。
2. OACETT：https://oacett.org/professional-development/cpd-workshops-webinars（公開頁全文）
3. OSPE：https://members.ospe.on.ca/events/（逐月篩選當月到 +6 週）＋ https://learn.ospe.on.ca/ EngLearn
   - 標示「Please log in to see Member pricing」者：會員價未驗證，列入時須註明「會員免費待登入確認」，不可寫成已確認免費。
4. CTTAM：https://cttam.com/ 首頁；公開頁查不到活動就如實註明（其活動多經 email 公告，網站更新慢）。

## 篩選條件（同時符合才列入主清單）

- 日期在執行日起未來 6 週內。
- 主題相關：醫療器材／MedTech、品質管理／ISO 13485、工程技術認證（C.Tech.）、AI／R&D、工程相關（工程實務、工程職涯、工程技術；優先製造／製程／生醫／系統／可靠度／品質工程）。純土木／結構主題不列。
- 地點：線上，或多倫多／安大略實體。免費但實體在外州／外省者不列主清單（可備查）。
- 免費：詳情頁有逐字價格證據（Free、No Charge、$0 等）。未標價不等於免費。

## 去重

- 「已報名」活動不重複列為新活動。目前已報名：ASQ HIRA 工作坊（2026-10-24，Oakville，已舉行，僅存記錄）。
- 每週報告須標出與上週相比的新增／變動／已結束。

## 產出

- 報告檔寫入 repo：`reports/latest.md`（固定路徑，覆寫），結構比照 Muse 現行報告：掃描日期、涵蓋區間、主清單（名稱、日期時間含時區、地點、一句話說明、官方連結、相關性）、已排除備查、查證限制。
- 完成後在追蹤 issue 留言：本週新增場次數、報告連結、任何抓取失敗的來源。
- 抓取失敗（例如 ASQ 行事曆渲染失敗）必須明說，不可靜默跳過。

## 分工邊界

- Claude：掃描、核價、寫報告。
- Muse：看門狗。每週檢查 reports/latest.md 是否更新；缺席或失敗時在 issue 留言並向 Rene 標註「Claude 管線異常」。負責把摘要送進 Rene 的聊天室（Claude 無此通道）、維護「已報名」名單、與求職管線的活動資訊不混用。
- 不碰：登入、報名、Gmail、Rene 個資。
