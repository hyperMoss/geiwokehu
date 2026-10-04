# 抖音 / 小红书采集能力迁移与 Next.js 接入

更新：2026-09-24 · 来源：本机 MediaCrawler `380b426` · 状态：代码迁入、离线链路验证通过；真实平台采集待账号环境验收

## 交付范围

本项目内置从 MediaCrawler 提取的**抖音和小红书**采集运行组件，放在 `vendor/mediacrawler/`。Next.js 页面统一创建两种平台的关键词任务；本机 Python 服务在隔离的子进程中运行对应平台采集器，将 JSONL 内容与首级评论标准化后写入 SQLite。`Spider_XHS` 不再参与运行，也不需要配置外部 MediaCrawler 项目路径。飞书不是采集平台，本次没有接入。

```text
Next.js 页面 → /api/jobs → 本机 Python 服务 → vendor/mediacrawler/media_platform/{douyin,xhs}
                                              ↓ JSONL
                                   标准化 → SQLite → 任务结果页
```

提取的是两个平台采集器及其运行必需的共用模块：`base`、`cache`、`config`、`database`、`media_downloader`、`model`、`proxy`、`store`、`tools`、`libs` 和 `var.py`。未迁入其他平台、Web UI、源项目 API、测试、文档和既有数据。浏览器脚本与上游原始版权头保留；完整上游许可证见 [`vendor/mediacrawler/LICENSE`](../vendor/mediacrawler/LICENSE)。该许可证仅授权非商业学习研究的复制和使用；商业获客用途需要权利人另外授权。

本次实现关键词搜索、素材详情、每条素材首级评论、JSONL 导入、任务记录与结果查看。不包含私信、发布、二级评论、代理、媒体下载或自动登录。MediaCrawler 导出的作者 ID 是匿名哈希，昵称经过脱敏；**不能从这些字段得到可联系客户的真实平台 ID**。设计文档中的客户转化、AI 评分、飞书同步、内容生成仍是后续模块，不能把采集条目直接当成已转化客户。

## 接口与数据

`POST /api/jobs` 示例：

```json
{"adapter":"mediacrawler","platform":"xhs","keyword":"AI转型","max_items":20,"max_comments":10}
```

`platform` 只接受 `dy` 或 `xhs`。源采集器的搜索页大小固定，抖音一次至少 10 条、小红书至少 20 条；本工作台上限均为 20 条，每条首级评论上限 30 条。任务顺序运行，避免共享账号并发。`GET /api/jobs` 返回最近 50 条任务；`GET /api/jobs/:id` 返回任务及最多 100 条素材和评论预览。结果以 `(platform, external_id)` 去重，任务与结果的关联保留。记录包含标题/正文、来源 URL、关键词、匿名作者哈希、发布时间、评论正文和运行来源。展示 URL 移除临时查询令牌。

任务与结果写在 `.local-data/crawler.sqlite3`。每次运行的 JSONL、临时浏览器目录和 `source.log` 写在 `.local-data/runs/<job-id>/`，均被 `.gitignore` 排除。Cookie 只通过环境变量传给子进程，不出现在命令行参数或前端。任务超时为 10 分钟；失败和超时会标记失败，已经写出的部分数据保留。服务重启时排队/运行中的任务改为“已中断”。

## 本机启动

需要 Node.js、npm、Python 3.11+。采集器依赖清单随代码保存在 `vendor/mediacrawler/requirements.txt`；还需要 Playwright Chromium。使用单独 Python 环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r vendor/mediacrawler/requirements.txt
.venv/bin/python -m playwright install chromium
npm install
cp .env.example .env.local
```

编辑 `.env.local`：把 `MEDIACRAWLER_PYTHON` 改成当前项目 `.venv/bin/python` 的绝对路径，按需填写 `DOUYIN_ACCOUNT_COOKIE`、`XHS_ACCOUNT_COOKIE`。不要提交 Cookie。没有对应 Cookie 时任务会失败并显示缺少的变量；页面本身可打开。启动两个终端：

```bash
# 推荐：启动脚本会自动载入 .env.local 并设置 NO_PROXY
./scripts/start_crawler.sh          # 前台启动，Ctrl-C 停止
./scripts/start_crawler.sh --check  # 只查状态，已在运行则不重复启动
```

手工方式（等价）：

```bash
set -a; source .env.local; set +a
python3 -m crawler_bridge.server
```

```bash
npm run dev
```

浏览器打开 `http://localhost:3000`。采集服务只允许监听回环地址，默认端口 8765；Next.js 的 `CRAWLER_API_URL` 默认指向该地址。当前本地服务无生产鉴权，不应直接暴露公网。

## 本机排查约定

- **端口占用**：重复启动会报 `端口 8765 已被占用`（服务已内置友好提示）。先跑 `./scripts/start_crawler.sh --check` 判断是否已有健康实例；确需重启用 `lsof -ti tcp:8765 | xargs kill`。
- **代理变量**：本机 shell 常设置 `HTTP_PROXY`，会让请求回环地址的流量走代理并失败，表现为前端提示「本地采集服务未启动」，但服务其实健康。启动脚本与 `lib/backend.ts` 已处理；手工排查时 curl 加 `--noproxy '*'`。
- **`.env.local` 格式**：值内含 `;` `&` `|` `$` 等shell 特殊字符时必须加单引号，否则 `source` 会被拆成多条命令。Cookie 建议始终加引号。

不调用平台也可导入已有 JSONL 验证数据链路：

```bash
python3 -m crawler_bridge.import_jsonl /absolute/path/to/output --platform xhs --keyword AI转型
```

目录须包含 `xhs/jsonl/search_contents_*.jsonl` 和可选 `search_comments_*.jsonl`；抖音对应 `douyin/jsonl/`。导入会生成任务并在页面展示。

## 验证状态

- 已通过：Python 单元测试 3 项，提取代码与服务编译检查，Next.js 类型检查与构建，离线 JSONL 导入路径。
- 待验收：本机尚无采集依赖、Playwright 浏览器和可用平台 Cookie；未执行真实抖音/小红书搜索，无法承诺实际账号状态、结果数量、评论覆盖或平台接口稳定性。
- 后续正式系统需要组织权限、持久任务队列、取消/重试、增量游标、审计与数据保留策略；这些不属于当前工作台。
