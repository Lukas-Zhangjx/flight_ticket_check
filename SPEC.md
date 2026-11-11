# 国际机票价格监控 —— 开发方案说明

> 给 Claude Code 的开发说明。请先通读全文，按「开发阶段」顺序实现，每个阶段完成后停下来让我确认。
> 不确定的接口细节（字段名、限流规则）请以官方文档为准，并在代码注释中注明来源。

---

## 0. 默认假设（我还没最终确定，先按这些做，代码里要方便以后修改）

| 事项 | 默认值 |
|---|---|
| 使用者 | 只有我自己（单用户），但不要把任何密钥写进前端 |
| 往返票处理 | **第一版按单程处理**：去程、回程当成两条单程航线分别监控和画图。往返组合放到后续版本 |
| 未来价格范围 | 从今天起 **90 天**，可配置 |
| 提醒规则 | 每条关注航线可设「价格上限」；低于上限**且**创出该出发日期的新低时提醒 |
| 货币 | EUR |
| 通知渠道 | ntfy（以后可能加微信推送，所以通知模块要做成可扩展的） |

---

## 1. 项目目标

一个个人用的**国际航班**票价监控网页：

1. 用户自己选择出发地、目的地、日期范围（**只允许国际航线**）。
2. 两种图表：
   - **视图 A · 未来价格**：横轴 = 未来的出发日期，纵轴 = 价格。可同时显示多家航司的曲线做比较，并标出每天的最低价航班。
   - **视图 B · 某日的历史价格**：选定一个出发日期，横轴 = 查询日期（我们每天记录一次），纵轴 = 价格。同样可显示多家航司曲线，并标出最低价。
3. 关注列表：把航线加入关注后，每天自动记录价格快照，并在出现低价时通过 ntfy 推送提醒。
4. 附加：特价网站 RSS 的关键词过滤提醒（已有原型代码）。

**硬性约束**
- **零成本**：只用免费服务。
- **无法律风险**：只用官方授权的 API 和公开 RSS，**禁止任何形式的爬虫**（不爬 Google Flights、OTA、航司网站）。
- 遵守 Travelpayouts 使用条款：控制请求频率；页面上注明数据来源为 Aviasales / Travelpayouts；订票链接使用 API 返回的 Aviasales 链接。

---

## 2. 数据来源

### 2.1 Travelpayouts（Aviasales）Data API
- 注册 Travelpayouts 并加入 Aviasales 项目后获得 API token。
- **重要特性**：返回的是 Aviasales 全体用户最近搜索结果的**缓存价格**（保存约 2–7 天），**不是实时价格**，也**不提供过去的历史价格**。冷门航线/日期可能没有数据。
- 主要接口（以官方文档为准）：
  - `GET https://api.travelpayouts.com/aviasales/v3/prices_for_dates`
    参数：`origin`, `destination`, `departure_at`（`YYYY-MM` 或 `YYYY-MM-DD`）, `one_way=true`, `unique=false`, `sorting=price`, `currency=eur`, `limit`, `page`, `token`
    返回字段大致有：`price`, `airline`, `flight_number`, `departure_at`, `transfers`, `duration`, `link`, `origin_airport`, `destination_airport`
  - `GET https://api.travelpayouts.com/aviasales/v3/grouped_prices`（按天分组的最低价，可作为补充）
  - 静态数据（免费，无需 token，可缓存）：
    - 城市：`https://api.travelpayouts.com/data/en/cities.json`（含 `code`, `name`, `country_code`）
    - 机场：`https://api.travelpayouts.com/data/en/airports.json`
    - 航司：`https://api.travelpayouts.com/data/en/airlines.json`（用于把航司代码显示成名称）
- 请先查官方文档确认限流规则；在代码里统一做节流（建议默认 ≤ 1 请求/秒）和失败重试（最多 2 次）。

### 2.2 RSS 特价源
- 默认：`https://www.secretflying.com/feed/`、`https://www.urlaubspiraten.de/feed`（地址需验证，失效则替换）。
- 只做：下载 → 解析 `<item>` → 按 guid 去重 → 关键词正则过滤 → 推送标题和链接。

### 2.3 「国际航线」判定
- 用 `cities.json` / `airports.json` 查出发地和目的地的 `country_code`，**不同即为国际航线**。
- 前端选择时校验一次，后端（Worker）收到请求时**再校验一次**，同国家直接拒绝。

---

## 3. 系统架构

```
┌──────────────────────┐        ┌───────────────────────────┐
│  前端（GitHub Pages）  │──API──▶│  Cloudflare Worker（免费）  │──▶ Travelpayouts API
│  选航线 / 图表 / 关注   │        │  - 持有 TP_TOKEN            │
└─────────▲────────────┘        │  - 实时查询（视图A）         │
          │ 读取静态 JSON        │  - 关注列表存在 KV          │
          │                      └──────────▲────────────────┘
┌─────────┴─────────────────┐               │ GET /watchlist
│ GitHub Actions（每天定时）   │──────────────┘
│ 1. 取关注列表               │──▶ Travelpayouts API
│ 2. 查价格 → 写每日快照      │
│ 3. 判断提醒 → ntfy 推送      │──▶ ntfy.sh
│ 4. RSS 检查                 │
│ 5. 提交数据并部署 Pages      │
└────────────────────────────┘
```

**分工**
- **视图 A（未来价格）**：前端 → Worker → Travelpayouts，实时读取当前缓存。任何航线都能查。
- **视图 B（历史价格）**：前端直接读仓库里的快照 JSON。**只有关注列表中的航线才有历史**，历史从开始关注那天起积累。
- 视图 A 对关注航线也可以直接用当天快照，减少 API 调用。

**注意**
- GitHub Pages 在免费账户下要求仓库为 **public**。价格数据公开没关系，但所有密钥必须放在 GitHub Secrets / Worker Secrets 中。
- Worker 的接口用一个简单的访问口令保护（`ACCESS_KEY`，请求头 `X-Access-Key`），防止被别人滥用我的 token。前端第一次使用时输入口令，存到 localStorage（读写要包 try/catch）。
- 已知风险：`*.workers.dev` 域名在中国大陆可能访问不了。第一版不处理，在 README 中注明；以后可绑定自定义域名。

---

## 4. 数据模型

### 4.1 关注列表（存在 Cloudflare KV，key = `watchlist`）
```json
[
  {
    "id": "MUC-SHA",
    "origin": "MUC",
    "destination": "SHA",
    "date_from": "2027-01-01",
    "date_to": "2027-03-31",
    "max_price": 450,
    "airlines": [],            // 空 = 全部航司
    "enabled": true,
    "created_at": "2026-11-11"
  }
]
```
往返需求在第一版里用两条记录表示（例如 `MUC-SHA` 和 `SHA-MUC`）。

### 4.2 每日快照（仓库 `data/snapshots/<route_id>/<YYYY-MM-DD>.json`，文件名是查询日期）
```json
{
  "route_id": "MUC-SHA",
  "fetched_at": "2026-11-11T06:17:00Z",
  "currency": "EUR",
  "source": "travelpayouts-cache",
  "dates": {
    "2027-01-20": {
      "min": { "price": 389, "airline": "MU", "flight_number": "220", "transfers": 0, "link": "/search/..." },
      "by_airline": {
        "MU": { "price": 389, "flight_number": "220", "transfers": 0 },
        "CA": { "price": 412, "flight_number": "962", "transfers": 0 },
        "LH": { "price": 455, "flight_number": "726", "transfers": 0 }
      }
    }
  }
}
```
- 每个「出发日期 × 航司」只保留最低价。
- 没有数据的日期不写，前端画图时显示为断点，**不要插值**。

### 4.3 汇总索引（方便前端读取，避免一次加载太多文件）
- `data/index.json`：所有关注航线及其可用的快照日期列表。
- `data/history/<route_id>.json`：按「出发日期 → 查询日期 → 航司 → 价格」汇总好的历史数据，专供视图 B 使用。每次定时任务结束后重新生成。

### 4.4 提醒状态
- `data/alert_state.json`：每条航线、每个出发日期的历史最低价，以及已推送过的 RSS guid（保留最近 500 条）。

---

## 5. Worker 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/prices?origin=MUC&destination=SHA&from=2027-01-01&to=2027-03-31` | 视图 A：查询 Travelpayouts，按「出发日期 × 航司」聚合成与快照相同的 `dates` 结构返回。先校验国际航线。可用 Cloudflare Cache 缓存 1 小时 |
| GET | `/watchlist` | 返回关注列表（GitHub Actions 也用这个） |
| PUT | `/watchlist` | 整体更新关注列表（新增/删除/修改） |
| GET | `/places?q=mun` | 可选：城市/机场搜索，供前端自动补全（也可以前端直接加载静态 cities.json） |

- 所有接口校验 `X-Access-Key`。
- Secrets：`TP_TOKEN`, `ACCESS_KEY`。
- CORS 只允许我的 GitHub Pages 域名。

---

## 6. 定时任务（GitHub Actions，每天 1 次）

1. 从 Worker 的 `GET /watchlist` 取关注列表（Secrets：`WORKER_URL`, `ACCESS_KEY`）。
2. 对每条启用的航线，按月份分段调用 `prices_for_dates`，聚合后写入 `data/snapshots/<route_id>/<今天>.json`。
3. 重新生成 `data/index.json` 和 `data/history/*.json`。
4. 提醒判断：对每个出发日期，若 `min.price <= max_price` 且低于 `alert_state` 中记录的历史最低价 → 推送 ntfy，并更新状态。同一次运行里，同一条航线的多条提醒**合并成一条消息**，避免刷屏。
5. RSS 检查（复用原型逻辑；第一次运行只记录、不推送）。
6. 提交 `data/` 的改动，部署 GitHub Pages。
- Secrets：`TP_TOKEN`, `NTFY_TOPIC`，可选 `NTFY_SERVER`。
- 定时时间避开整点，例如 `17 6 * * *`。

**通知模块**：定义统一的 `notify(title, message, click_url)` 接口，目前实现 ntfy（用 JSON 方式发布，保证中文和 emoji 标题正常；带 `click` 链接）。以后加微信推送时只需新增一个实现。

---

## 7. 前端（GitHub Pages，静态网页）

- 技术：纯 HTML + JS 即可，图表用 **ECharts**（中文支持好）。界面语言：中文。
- **航线选择**：出发地、目的地输入框带自动补全（城市名/机场代码），选同一国家时提示「仅支持国际航线」。日期范围选择。
- **视图 A · 未来价格**
  - 多条折线：每家航司一条，可勾选显示哪些航司（默认显示最便宜的前 5 家）。
  - 一条加粗的「每日最低价」线，悬停显示航司、航班号、转机次数、价格。
  - 点击某一天 → 打开该日最低价的 Aviasales 订票链接，并提示「缓存价，下单前请在航司官网确认」。
  - 点击某一天 → 也可跳到视图 B 查看这一天的历史。
- **视图 B · 某日历史价格**
  - 选择关注航线 + 出发日期。
  - 横轴 = 查询日期，多条航司折线 + 最低价线。
  - 没有历史时显示「这条航线从 X 月 X 日开始记录，历史数据还在积累中」。
- **关注列表管理**：列表显示所有关注航线，可新增、删除、启用/停用、修改价格上限。
- 页面底部注明：数据来源 Aviasales / Travelpayouts，价格为缓存价，非实时。
- 手机上要能正常使用（我主要用手机看）。

---

## 8. 仓库结构（建议）

```
/
├─ SPEC.md                  本文件
├─ README.md                部署步骤（Secrets 怎么配、Worker 怎么部署）
├─ worker/                  Cloudflare Worker（wrangler 项目）
├─ collector/               每日采集 + 提醒 + RSS（Python，尽量只用标准库）
│   └─ notify/              通知渠道（ntfy.py，以后加 wechat.py）
├─ web/                     前端静态页面
├─ data/                    快照、索引、提醒状态（由 Actions 自动提交）
├─ prototype/flight_watch.py  已有原型，可参考其中 RSS 与 ntfy 的逻辑
└─ .github/workflows/       定时任务与 Pages 部署
```

---

## 9. 开发阶段（每完成一阶段停下来让我确认）

1. **采集器**：读取本地 `watchlist.json`（先不接 Worker），调用 Travelpayouts，写快照和 `history`。带一个 `--dry-run` 模式，用假数据也能跑通。
2. **提醒**：ntfy 推送 + `alert_state` + RSS。
3. **GitHub Actions**：每日定时运行、提交数据、部署 Pages。
4. **前端视图 B**（只读静态 JSON，最简单），然后视图 A 先用最新快照。
5. **Cloudflare Worker**：实时查询 + 关注列表 KV；采集器改为从 Worker 读取关注列表；前端视图 A 改为调用 Worker。
6. **关注列表管理界面** 和收尾（README、错误提示、手机适配）。

---

## 10. 验收标准

- 选择同一国家的两个城市时，前端和 Worker 都会拒绝。
- 前端代码和仓库里**找不到任何 token**。
- 关注 `MUC → SHA` 后，连续运行几天，视图 B 能画出多航司历史曲线。
- 视图 A 能显示未来 90 天的多航司曲线和每日最低价，缺数据的日期显示为断点。
- 价格低于上限并创新低时，手机收到 ntfy 通知，点击可打开订票链接；同一价格不会重复推送。
- 定时任务失败时（API 出错），不会写入空快照，也不会覆盖已有数据。

---

## 11. 以后可能做（第一版不做）

- 往返组合：固定停留天数（如 14–21 天）的往返最低价。
- 多出发地/多目的地一起比较（如慕尼黑、法兰克福、维也纳 → 上海）。
- 微信推送（Server酱 / PushPlus），按我人在哪里切换通知渠道。
- 接入 Duffel 获取实时价格（需先确认只查询不下单的费用和条款）。
- 自定义域名，解决中国大陆访问 workers.dev 的问题。
