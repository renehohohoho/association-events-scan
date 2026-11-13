# association-events-scan

本 repo 是 Muse 與 Claude Code 分工中的「任務 C：專業協會活動掃描」。

- 完整任務規格：docs/TASK-SPEC.md（動工前先讀完）
- 執行方式：GitHub Actions 自動掃描（`.github/workflows/weekly-events-scan.yml`，
  每週三 13:17 UTC＋可手動 workflow_dispatch；執行細節見 docs/RUNBOOK.md）
- 追蹤與溝通：本 repo issue #1（workflow 每輪在此留言回報；Muse 在此留言驗收與提醒）
- 產出固定路徑：reports/latest.md（每週覆寫）；狀態檔 state/last-scan.json（供下輪比對新增／已結束）
- 掃描程式：scripts/scan.py＋scripts/sources/（Python；單元測試在 scripts/tests/）

硬規則速覽（細節以規格為準）：只列免費場次且須有詳情頁逐字價格證據；不登入任何網站；不代為報名；抓取失敗必須明說，不可靜默跳過；每週報告標出新增／變動／已結束；「已報名」一節由掃描原樣保留、內容由 Muse 維護。

歷史：2026-10-22 首次執行為手動 Claude session（本機腳本，未進 repo），
之後管線停擺三週；2026-11-13 改為 GitHub Actions 自動化，取代手動流程。
