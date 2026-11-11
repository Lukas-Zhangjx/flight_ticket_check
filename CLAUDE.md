# 国际机票价格监控 · 项目规范

详细的产品设计见 [SPEC.md](SPEC.md)（目标、数据源、架构、数据格式、接口、前端、分阶段开发顺序、验收标准）。本文件只放 Git 工作流和提交规范。

## 目录结构

```
/
├─ SPEC.md
├─ CLAUDE.md
├─ README.md
├─ worker/                  Cloudflare Worker（Phase 5+）
├─ collector/                每日采集 + 提醒 + RSS（Python，只用标准库）
│  └─ notify/                通知渠道（ntfy.py，以后可能加 wechat.py）
├─ web/                      前端静态页面
├─ data/                     快照、索引、提醒状态（由 GitHub Actions 每日采集自动提交）
├─ prototype/flight_watch.py 原型参考代码
└─ .github/workflows/        定时采集任务 + Pages 部署
```

## Git 工作流

### 原则

**每个功能建一个分支，边开发边往该分支推送，测试通过后合并回 main。不要直接 commit 到 main。**

```
main                  ← 稳定版本，只接受合并，不直接 commit
  ├── feature/xxx     ← 新功能（开发期间持续 push 到此分支）
  ├── fix/xxx         ← Bug 修复
  └── refactor/xxx    ← 重构
```

开发期间随时 commit + push 到功能分支，不要攒成一个大提交：
- 随时可回滚到任意一个可用状态
- 出问题能精确定位是哪次改动引入的
- 分支上能看到这个功能完整的开发历史

### 标准流程

**开发新功能：**
```bash
git checkout main && git pull
git checkout -b feature/功能名
# ... 开发中，随时 commit + push 到功能分支 ...
git add <相关文件>
git commit -m "feat(scope): 做了什么"
git push -u origin feature/功能名      # 第一次推用 -u，后续直接 git push

# 功能开发完、测试通过后：
git checkout main && git pull
git merge feature/功能名 --no-ff       # 合并回 main（保留分支记录）
git branch -d feature/功能名
git push origin main
git push origin --delete feature/功能名   # 清理远端分支
```

**修复 Bug：**
```bash
git checkout main && git pull
git checkout -b fix/问题描述
# ... 修复、提交 ...
git checkout main && git pull
git merge fix/问题描述 --no-ff
git branch -d fix/问题描述
git push origin main
git push origin --delete fix/问题描述
```

### 例外：不走分支、可以直接碰 main 的情况

- 纯文档改动（`SPEC.md`、`README.md`、`CLAUDE.md` 本身）且不涉及代码/配置。
- GitHub Actions 自动提交的每日数据快照（`data/**`，由 `collect.yml` 自动完成，不是人工走分支流程）。
除此之外——collector、worker、web、workflow 配置——一律走 feature/fix 分支。

### 测试要求（强制）

**每次合并进 main 之前，必须实际跑一遍改动涉及的路径，不能只凭读代码判断。**

- `collector/` 改动：至少跑一次 `python3 collector/collect.py --dry-run`，确认不报错、生成的 snapshot/index/history 结构符合预期。涉及真实 API/通知的改动，有条件时手动触发一次真实 workflow run 验证。
- `web/` 改动：起本地静态服务器（`python3 -m http.server`，并把 `data/` 和 `web/` 按 Pages 部署时的结构拼在一起），在浏览器里实际点一遍受影响的交互，桌面和手机宽度都看一下。
- `.github/workflows/` 改动：`gh workflow run <name>.yml` 手动触发，`gh run watch` 跟到完成，确认真的跑通，不要只验证 YAML 语法。
- 涉及密钥的改动：确认没有把任何 token/密钥写进代码或提交记录；真实密钥只能由用户自己通过 `gh secret set` 或网页设置。

> 不实际跑一遍就合并 = 给未来的自己挖坑（Phase 3 的 `.gitignore` 挡住真实数据提交、`NTFY_SERVER` 空字符串、Actions 的 `GITHUB_TOKEN` 不触发下游 workflow——这几个坑都是真实环境跑出来才发现的，光看代码看不出来）。

### Commit Message 格式（Conventional Commits）

```
<type>(<scope>): <subject>
```

**type：**
- `feat` 新功能
- `fix` Bug 修复
- `refactor` 重构（不改功能）
- `style` 样式调整
- `docs` 文档更新
- `chore` 构建/依赖/配置
- `perf` 性能优化

**scope（本项目专用）：**
`collector` / `notify` / `worker` / `web` / `data` / `workflow` / `spec`

**合格示例：**
```
feat(collector): 支持按月分页抓取 prices_for_dates
fix(workflow): collect.yml 提交 data/ 时被自身 .gitignore 挡住，改用 git add -f
fix(notify): NTFY_SERVER 为空字符串时未回退到默认值
feat(web): 视图A点击日期弹出订票/跳转视图B的底部面板
refactor(collector): 拆分 aggregate.py 中的快照聚合逻辑
```

**禁止：**
- `fix bug` / `update code` / `WIP`
- 一个 commit 包含多个不相关改动
- 直接 commit 到 main（文档类例外见上）

### 提交前 Checklist
- [ ] 无遗留调试代码（临时 print/console.log、测试用的假数据目录）
- [ ] 无硬编码 API Key / token / secret（真实密钥只在 GitHub Secrets 里，代码里只能是 `os.getenv(...)` 或 `${{ secrets.X }}`）
- [ ] commit message 符合 Conventional Commits 格式
- [ ] **已实际跑一遍受影响的路径，确认不报错**
- [ ] 功能分支已测试通过，`merge --no-ff` 回 main 后删掉分支

## 禁止事项一览
| 禁止 | 原因 |
|------|------|
| 直接 commit 到 `main`（文档类除外） | 污染稳定版本，无法回滚单个功能 |
| 功能未测试就合并 | 破坏 main 可用性，坑后续排查 |
| 把真实 token/密钥写进代码、workflow 文件或提交记录 | 严重安全风险；只能放 GitHub Secrets |
| 只验证 YAML 语法就认为 workflow 改动没问题 | collect.yml/pages.yml 的几个真实 bug 都是语法正确但运行时出错 |
| 魔法数字/字符串散落各处 | 提取成有名字的常量，集中管理 |
| 本地 dry-run 生成的假数据被提交进仓库 | 会被误认成真实价格数据；`data/` 只能由 Actions 真实采集产生
| 本地测试后 `rm -rf data/` 清理 | `data/` 里混着 Actions 提交的真实数据（已被 git 追踪）和本地 dry-run 产物（gitignored），blanket 删除会连真实数据一起删掉——清理前先 `git status` 确认，或者用 `git checkout -- data/` 恢复误删
