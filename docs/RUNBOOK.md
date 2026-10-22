# 每週掃描執行手冊

規則以 docs/TASK-SPEC.md 為準；本檔只記錄實際可行的抓取方法（2026-10-22 首次執行時驗證）。

## 節奏

每週三一輪（多倫多時間上午），報告在週四 Muse 看門狗檢查前更新。直接 commit 到 main 的 `reports/latest.md`。

## 環境

```
cd scripts && npm install   # 只裝 playwright-core，不下載瀏覽器
```

腳本使用預裝的 Chromium：`/opt/pw-browsers/chromium-1194/chrome-linux/chrome`。路徑若改變，修改三支腳本的 `executablePath`。輸出放在 scratchpad，不要寫進 repo。

## 各來源方法

| 來源 | 方法 | 首次結果 |
|---|---|---|
| ASQ 行事曆 my.asq.org/events/calendar | `node asq_all.js <out>`：把每頁筆數切到最大後讀全部清單與詳情頁連結；初篩後把 `id<TAB>url` 寫入清單，用 `node details.js <清單> <輸出目錄>` 逐場開詳情頁，在內文找 Cost／Fee／Free／$ 等字樣 | 152 筆全部讀到 |
| ASQ asq.org/conferences | Cloudflare 擋（403）。每週仍要試一次，失敗就在報告和 issue 註明 | 失敗 |
| OACETT | `curl` 抓原始 HTML（輪播中隱藏的項目也在裡面），解析每個項目的 Presented By／Dates／Cost／Format | 成功 |
| OSPE 活動 | 公開 REST API：`https://members.ospe.on.ca/wp-json/tribe/events/v1/events?start_date=<執行日>&end_date=<+6週>&per_page=50`，再用 `details.js` 逐場開 `url` 核價。出現 "Please log in to see Member pricing" 時一律標「會員免費待登入確認」 | 13 場 |
| OSPE EngLearn learn.ospe.on.ca | `node render.js <url> <out>`；目前只有隨選內容 | 無排定活動 |
| CTTAM | `render.js` 抓首頁、https://cttam.com/event、https://cttam.com/archives/category/news | 無活動 |

## 每週流程

1. 依上表抓取；任何來源失敗都要記錄，不能略過。
2. 依規格篩選（6 週、主題、地點、逐字免費證據）。
3. 用 `git show HEAD:reports/latest.md` 取得上週報告，標出新增、變動、已結束。
4. 覆寫 `reports/latest.md`，commit 並 push 到 main。
5. 在 issue #1 留言：新增場次數、報告連結、失敗的來源。
6. 先讀 issue #1 最新留言，確認 Muse 有沒有更新已報名名單。
