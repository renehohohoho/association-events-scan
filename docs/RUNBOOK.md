# 每週掃描執行手冊

規則以 docs/TASK-SPEC.md 為準；本檔記錄實際可行的抓取方法與自動化流程。

## 節奏

每週三一輪（多倫多時間上午），報告在週四 Muse 看門狗檢查前更新。
由 GitHub Actions 自動執行（`.github/workflows/weekly-events-scan.yml`，
每週三 13:17 UTC＋可手動 workflow_dispatch），直接 commit 到 main 的
`reports/latest.md`，並在 issue #1 留言回報。**不再需要任何人手動開
Claude session、也不再依賴任何本機腳本或本機瀏覽器。**

根因（2026-11-13）：此前沒有任何排程觸發，掃描腳本只存在於某台本機的
`scripts/` 資料夾、從未進 repo；唯一一次執行是 2026-10-22 的手動
Claude session，之後再也沒人開過 session，管線就停了。本 workflow
就是修復：排程＋程式碼＋報告提交全部在 repo 內完成。

## 自動化流程（workflow）

1. `actions/checkout`（取分支最新 commit）→ `setup-python 3.11` →
   `pip install -r scripts/requirements.txt` →
   `playwright install --with-deps chromium`（JS 渲染來源用）。
2. `python -m unittest discover -s scripts/tests`（單元測試先跑）。
3. `python -m scripts.scan --with-browser`：掃描全部來源，寫入
   `reports/latest.md`、`state/last-scan.json`、`scan-summary.json`。
4. 成功時提交 `reports/ state/ scan-summary.json` 回 main（無變更則略過）；
   成功與失敗都在 issue #1 留言（成功：新增場次數＋報告連結＋失敗來源；
   失敗：run 連結）。
5. 任何單一來源失敗都不會中斷整輪：失敗會記入報告的查證限制、摘要檔
   與 issue 留言，不靜默跳過。

手動執行：repo Actions 頁 → weekly-events-scan → Run workflow。
本機執行：`python -m scripts.scan --date YYYY-MM-DD [--with-browser]`
（`--with-browser` 才跑 Playwright 來源；不加則只跑 requests 來源）。

## 各來源方法（已驗證）

| 來源 | 方法 | 備註 |
|---|---|---|
| ASQ 行事曆 my.asq.org/events/calendar | `requests`：GET 取 `__VIEWSTATE` 等表單欄位後 POST `__doPostBack`（`ddlResultsPerPage=9999999`，All），一次取回全部刊登（約 93 場，11＋12 月）；逐場開詳情頁，在去標籤後的內文找 Cost／Fee／Free／$ 等字樣 | 免登入；清單本身不顯示價格，必須逐場核價 |
| ASQ asq.org/conferences | `requests` GET；Cloudflare 擋（403） | 每週仍要試一次，失敗就在報告和 issue 註明 |
| OACETT | `requests` 抓原始 HTML，解析每個項目的 Presented By／Dates／Cost／Format | 成功；自學項目（無排定日期）免費者列入補充資源 |
| OSPE 活動 | 公開 REST API：`https://members.ospe.on.ca/wp-json/tribe/events/v1/events?start_date=<執行日>&end_date=<+6週>&per_page=100`，再用活動清單頁交叉核對 API 漏掉的場次；逐場開詳情頁核價。出現 "Please log in to see Member pricing" 時一律標「會員免費待登入確認」 | API 回傳可能截斷，不可只信 API |
| OSPE EngLearn learn.ospe.on.ca | 輕量 GET 確認只有隨選內容、無排定活動 | 無排定活動 |
| CTTAM | `requests` 抓首頁、https://cttam.com/event、https://cttam.com/archives/category/news | 通常無活動 |
| TPL 活動清單 | `requests`：`https://tpl.bibliocommons.com/v2/events?page=N` 逐頁抓（伺服器渲染，約 21 場／頁、日期遞增），候選場次開詳情頁確認無費用與滿額狀態 | TPL 活動原則免費；已滿額者列備查 |
| Mississauga 作者講座 | `requests`：campaign.mississauga.ca/author-talks-updated/，解析 Divi 作者區塊（姓名／日期／時間／Virtual／Eventbrite 連結） | 作者講座免費登記；退休理財主題依規則不列 |
| Mississauga 一般活動 | Playwright：ActiveNet 活動搜尋頁（JS 渲染） | 失敗時記入查證限制，不中斷整輪 |
| LPL 線上 | Playwright：https://programs.lpl.ca/（Communico JS 元件），只取 Virtual／Online 場 | 失敗時記入查證限制，不中斷整輪 |

## 每週流程（程式自動做）

1. 依上表抓取；任何來源失敗都要記錄，不能略過。
2. 依規格篩選（6 週、主題、地點、逐字免費證據）。
3. 用 `state/last-scan.json`（無則解析上份 `reports/latest.md`）比對，標出新增、變動、已結束。
4. 覆寫 `reports/latest.md`，保留「已報名」一節原文，commit 並 push 到 main。
5. 在 issue #1 留言：新增場次數、報告連結、失敗的來源。
6. 先讀 issue #1 最新留言，確認 Muse 有沒有更新已報名名單（程式只會原樣保留該節，不改內容）。

## 已知陷阱（2026-11-13 實測，勿重蹈）

- **ASQ 行事曆 Where: 欄位不可信**：線上場次的 Where: 常空白或填分會預設地址
  （如 QMS 11/20 填 Oklahoma City 假地址，實際是 Webex 線上）。地點一律以
  詳情頁 Location 欄位為準（"Online Instructions"／Webex／Zoom 連結＝線上），
  空白 Where: 視為線上。舊寫法 `location_ok("線上")` 曾因 "線上" 不在
  ONLINE_MARKERS 而把全部免費場次誤判為外州實體（free=0 的假陰性）。
- **ASQ 清單標題常被截短／改名**（如 "online meeting: Build the Same Report..."，
  缺少副標題裡的 "AI Briefing Workflow"）。主題初篩不過時，先開詳情頁，
  以詳情頁標題＋"Topic:" 開頭的描述再篩一次，通過才核價。
- **OSPE 詳情頁絕對不能用裸 `free` 判斷**：頁尾有 "Toll Free: 1-866-763-1654"，
  裸搜 `free` 會把 $50–$190 的 Monte Carlo 課程、$25 的 PEO 課程、$350 的 CBA
  工作坊全誤判為免費（2026-11-13 實測四起）。只認價格語境的免費
  （`Cost:/Price: Free`、`Free to everyone`），並以 REST API 的 cost 欄位交叉核對：
  詳情頁說免費但 API 標示正價，一律改判付費。
- **OSPE 分類只看標題**：每個 OSPE 描述都提到 engineer，用描述篩選會放行
  整個行事曆（含土木／土地開發／水務）。P.Eng／CBA／AMR 等主題靠標題關鍵字。
- **TPL 詳情頁滿額有三種寫法**："Registration full"、"All places have been
  registered"、"no longer register"，另有清單標題前綴 `**FULL**`。三者都要擋。
- **TPL 每週重複系列**：同一標題＋分館每週重複，只列首場並註明，否則報告
  會被 WRAP、Google AI Essentials 等系列淹沒。
- **CTTAM 經 egress proxy 常連不上**（RemoteDisconnected），在 Actions 直連
  應可恢復；失敗時記入查證限制即可，週期重試。
- **TPL 清單頁很大**（每頁約 1.3MB、90 頁上限）：Actions 直連很快；本機經
  proxy 測試時單輪約 5 分鐘，屬正常。

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
python -m playwright install chromium   # 只有 --with-browser 需要
python -m unittest discover -s scripts/tests -v
python -m scripts.scan --date 2026-11-13            # requests 來源
python -m scripts.scan --date 2026-11-13 --with-browser  # 全部來源
```

輸出在 repo 根目錄執行時寫入 `reports/latest.md`、`state/last-scan.json`、
`scan-summary.json`。測試時用 `--date` 指定日期、用另一個 `--repo-root`
指向複本，避免覆寫正式報告。
