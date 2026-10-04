# AI Growth Ops 使用手册

AI Growth Ops 是一个仅在本机运行的获客工作台：用关键词采集抖音或小红书的素材与首级评论，将有意向信号的评论整理为潜客，人工复核后转入客户，并查看本地获客分析。潜客页还支持由用户手动触发的、可配置的大模型辅助分析。

> 当前项目是本地单用户工作台，不是公网服务。采集使用的内置 MediaCrawler 组件受[非商业学习许可证](vendor/mediacrawler/LICENSE)约束；请自行确认平台规则、账号授权和适用法律。真实平台结果、Cookie 有效性和模型输出都需要你自行核实。

## 当前能力与边界

| 页面 | 路径 | 当前可用功能 |
| --- | --- | --- |
| 关键词获客 | `/` | 创建抖音/小红书关键词任务、查看任务与素材、在素材下展开关联的首级评论、重试失败或中断任务 |
| 潜客筛选 | `/leads` | 本地规则初筛 A/B/C、筛选/复核/排除、手动触发 AI 分析、人工转客户 |
| 客户管理 | `/customers` | 手动新建或从潜客转入、编辑资料、生命周期和下次跟进时间、查看本地变更记录 |
| 获客分析 | `/analytics/lead` | 7/30/90 天任务、素材、评论、潜客、转化漏斗、每日新增和来源平台统计 |
| 集成配置 | `/integrations` | 查看 Cookie 是否已配置，以及在网页上保存/替换/清除模型配置 |

当前不提供自动登录、二维码/短信登录、读取浏览器 Cookie/密码/用户资料目录、私信、发布、二级评论、代理、媒体下载、飞书同步、多人权限或公网鉴权。不会自动联系潜客、自动转客户，也不会把模型结论当作事实或改写规则分。

## 前置条件

- Node.js `>= 20.9.0`（由当前 Next.js 依赖要求）和 npm。
- Python 3，以及一个专门给 MediaCrawler 使用的 Python 环境。
- 网络可访问你实际使用的平台与模型服务；模型服务必须是 HTTPS。
- 如要真实采集：你自己手动取得、且有权使用的目标平台 Cookie。

项目内置 MediaCrawler 依赖清单在 [`vendor/mediacrawler/requirements.txt`](vendor/mediacrawler/requirements.txt)，其中包含 Playwright；还必须为该 Python 环境安装 Chromium。

## 第一次启动

在项目根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r vendor/mediacrawler/requirements.txt
.venv/bin/python -m playwright install chromium
npm install
cp .env.example .env.local
```

编辑 `.env.local`，先填写实际虚拟环境 Python 的**绝对路径**。例如：

```dotenv
MEDIACRAWLER_PYTHON=/absolute/path/to/geiwokehu/.venv/bin/python
CRAWLER_HOST=127.0.0.1
CRAWLER_PORT=8765
CRAWLER_API_URL=http://127.0.0.1:8765
```

`MEDIACRAWLER_PYTHON` 必须是一个存在的 Python 可执行文件，且其中已安装上述依赖和 Chromium。它不是项目目录，也不是 `python3` 这类命令名；未设置或路径无效时，任务会显示“`MEDIACRAWLER_PYTHON 不是有效 Python 路径`”。

打开两个终端。

终端 A：启动本机 Python 采集服务（前台运行，按 `Ctrl-C` 停止）。

```bash
./scripts/start_crawler.sh
```

终端 B：启动网页。

```bash
npm run dev
```

浏览器访问 [http://127.0.0.1:3000](http://127.0.0.1:3000)。启动前或排查时，可执行：

```bash
./scripts/start_crawler.sh --check
```

该脚本会加载 `.env.local`，并让本机回环请求绕过常见的代理变量。采集服务默认只监听 `127.0.0.1:8765`；不要把它或 Next.js 开发服务器暴露到公网。

## 配置抖音 / 小红书采集账号

分别在 `.env.local` 中手动填入完整 Cookie：

```dotenv
DOUYIN_ACCOUNT_COOKIE='name=value; another_name=another_value'
XHS_ACCOUNT_COOKIE='name=value; another_name=another_value'
```

Cookie 是浏览器请求头中完整的 `name=value; name2=value2` 字符串。因启动脚本会读取 `.env.local`，建议始终使用单引号包住值；不要把 Cookie 粘贴到网页、终端记录、Issue 或版本库。

配置或修改 Cookie 后，停止并重新启动终端 A 的服务，再到“集成配置”页点击“重新检查”。页面只显示“已配置 / 未配置”，不会显示、保存或读取 Cookie 内容。显示“已配置”仅代表本机环境变量非空，不代表平台账号一定有效。

采集运行时，Cookie 仅通过子进程环境变量提供给对应平台；采集器使用每个任务独立的非持久化浏览器上下文，不保存登录状态，也不会读取你的系统浏览器资料、已有登录会话、密码或验证码。

## 在网页配置 AI 模型

打开“集成配置”页的“AI 模型配置”，填写：

- **API 基础地址**：默认 `https://api.deepseek.com`。
- **模型名**：默认 `deepseek-flash`。
- **API Key**：仅在需要新增或替换时输入；留空会保留已保存的 Key，也可勾选清除。

支持 DeepSeek，以及兼容 OpenAI Chat Completions 的 HTTPS 服务。基础地址必须是无查询参数、无用户名密码的 HTTPS 地址；服务应支持项目所请求的 `POST {基础地址}/chat/completions` 和 JSON 对象响应模式。

点击“保存模型配置”后，模型名、基础地址和 Key 会写入本机 `.env.local`，正在运行的 Python 服务立即使用新配置，无需重启。网页和接口只会返回“是否已配置”、模型名和基础地址，Key 不回显；通过网页保存的 `.env.local` 会设为仅当前用户可读。不要把 Key 写入 `NEXT_PUBLIC_*` 变量，也不要提交 `.env.local`。

也可在未打开网页时手动配置：

```dotenv
DEEPSEEK_API_KEY='your-api-key'
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

手动修改 `.env.local` 后需要重启 Python 服务才会加载新值。

## 日常工作流

### 1. 关键词采集

1. 在“关键词获客”选择抖音或小红书，填写 1–80 个字符的关键词。
2. 设置素材和评论数量：抖音素材数为 10–20；小红书当前固定为 20；每条素材的首级评论数为 0–30。设为 `0` 不采评论。
3. 点击“开始采集”，任务会依次运行，避免同一账号并发采集。
4. 任务完成后点击任务，查看素材。每条素材下的“关联评论”默认折叠，按需展开；没有关联素材的评论会单独列出。

任务状态会定时刷新。单个运行最长 10 分钟；失败时已成功导入的素材和评论仍会保留。选择失败或“已中断”的任务可点击“重试任务”，新任务会复用原来的平台、关键词、素材上限和评论上限。

### 2. 潜客筛选与人工转客户

评论入库后，系统按固定文本规则做首次提示，而不是模型打分：

| 等级 | 规则分 | 典型信号 |
| --- | ---: | --- |
| A | 85 | 询价、购买、报名、找机构、求合作等明确需求 |
| B | 65 | 方案、适用性、收费、怎么做等咨询 |
| C | 30 | 想了解、求资料、泛兴趣 |

包含“不需要”“没兴趣”“私信我”“招代理”等否定或广告表达的评论不会进入潜客。相同平台的匿名作者哈希会聚合为一条潜客；没有作者哈希时按评论 ID 单独保留。匿名标识仅用于去重和聚合，不能用于联系用户。

在“潜客筛选”可按关键词、意向等级和复核状态筛选，然后：

- 点击“标记已复核”或“排除”；已转客户的潜客不能再排除。
- 点击“转客户”，填写**人工核实过**的名称、公司、手机号与需求摘要。相同潜客重复转入会返回同一客户，不会重复建档。

### 3. 手动 AI 分析

在潜客卡片点击“AI 分析”（已有结果时为“重新 AI 分析”）。仅这次手动操作会调用已配置的模型；系统发送的平台、关键词、规则等级/分数/依据以及该潜客的评论正文证据，不发送昵称、匿名作者哈希、潜客 ID、Cookie 或客户资料。

返回结果会保存到该潜客卡片，包括摘要、意向判断、置信度、建议动作、人工核实后可用的沟通草稿，以及可折叠的“建议跟进 Skill”。请把它当作辅助草稿：模型可能出错、遗漏或受到评论内容影响，必须人工核实后再联系、填写客户资料或做业务决策。

### 4. 客户管理与看板

在“客户管理”中可手动新建客户，或编辑已转入客户的公司、手机号、需求、生命周期（待分配/跟进中/培育中/已成交/已流失）和下次跟进时间。每次修改会留下本地操作记录；出于隐私考虑，修改手机号的具体值不会写入操作详情。

在“获客分析”中选择 7、30 或 90 天，查看任务、素材、评论、潜客、高意向（规则分 ≥70）、转入客户、漏斗、每日新增和来源平台。日期按 `Asia/Shanghai` 自然日统计；看板是当前本地数据的快照，不构成模型质量或实际转化效果证明。

## 离线导入已有 JSONL

若不想调用平台，可导入已有的 MediaCrawler 输出验证数据链路：

```bash
python3 -m crawler_bridge.import_jsonl /absolute/path/to/output --platform xhs --keyword AI转型
```

目录需要包含 `xhs/jsonl/search_contents_*.jsonl`，评论文件 `search_comments_*.jsonl` 可选；抖音则使用 `douyin/jsonl/`。导入任务会在网页任务列表中显示。

## 常见问题

| 现象 | 排查方式 |
| --- | --- |
| 网页提示“本地采集服务未启动或无法连接” | 在终端 A 运行 `./scripts/start_crawler.sh --check`；确认服务在 `127.0.0.1:8765`，再检查终端中的启动错误。 |
| `MEDIACRAWLER_PYTHON 不是有效 Python 路径` | 把 `.env.local` 的值改为真实的绝对可执行文件路径，例如 `/…/geiwokehu/.venv/bin/python`；确认文件存在，随后重启采集服务。 |
| `未配置 XHS_ACCOUNT_COOKIE` 或 `未配置 DOUYIN_ACCOUNT_COOKIE` | 只为所选平台在 `.env.local` 手动填写完整 Cookie，重启采集服务并在“集成配置”重新检查。系统不会代登录或读取浏览器 Cookie。 |
| `MediaCrawler 执行失败；已保留可用数据，请检查本地运行日志` | 打开该任务的 `.local-data/runs/<任务 UUID>/source.log`。先检查目标 Python 的依赖、Chromium、Cookie 和平台账号/权限；已导入的数据仍可在任务结果中查看。 |
| 任务一直“采集中” | 一个采集任务串行运行，且平台请求耗时不稳定。最长 10 分钟会自动失败；服务重启后运行中任务会标记为“已中断”，可从原任务重试。 |
| “集成配置”页显示接口不存在或旧配置 | 终止旧的 Python 服务，再执行 `./scripts/start_crawler.sh`。网页模型配置保存成功后无需重启；手动编辑 `.env.local` 才需要重启。 |
| 模型分析提示未配置或请求失败 | 在“集成配置”填写 Key、HTTPS 基础地址和模型名；检查网络、模型供应商兼容性与账号配额。页面不提供真实 Key 的回显或余额校验。 |
| 端口 8765 被占用 | 先运行 `./scripts/start_crawler.sh --check` 判断是否健康。确需停止旧服务时，先用 `lsof -nP -iTCP:8765 -sTCP:LISTEN` 确认目标进程，再手动结束该进程。 |

## 数据、隐私与安全

- 本地 SQLite 数据库在 `.local-data/crawler.sqlite3`；任务 JSONL、浏览器运行目录和日志在 `.local-data/runs/<任务 UUID>/`。这些目录以及 `.env.local` 已被 Git 忽略。
- 账号 Cookie 和模型 Key 不会由状态接口返回，也不会写入前端配置。不要通过聊天、截图、Issue 或 Git 共享它们。
- 采集数据、评论和客户资料会保留在本机数据库中。删除、备份、迁移或分享 `.local-data` 前，请自行评估其中的个人信息与保留要求。
- 当前没有登录、角色、审计服务或公网 API 鉴权。仅限受控本机使用，不要直接部署为对外服务。
- 采集和模型分析均受外部平台、账户权限、地区网络、配额和服务条款影响。项目不承诺平台可用性、采集完整性、联系授权或模型判断准确性。

## 验证与开发检查

在项目根目录运行：

```bash
python3 -m unittest discover -s tests -p 'test*.py' -v
python3 -m compileall -q crawler_bridge scripts
npm run typecheck
npm run build
```

这些检查覆盖本地桥接、离线导入、Cookie/模型 Key 不回显、模型响应校验、任务重试、潜客转客户和前端构建；它们不等同于真实平台采集或真实模型调用验收。真实调用会使用你的账号、Cookie 或 Key，应由你在受控环境中手动发起并核实结果。

## 相关文档

- [当前实现与验收](docs/当前实现与验收.md)：较早的实现记录，部分内容已被本 README 的模型配置与 AI 分析功能更新。
- [爬虫能力提取与 Next.js 接入](docs/爬虫能力提取与Nextjs接入.md)：MediaCrawler 迁入边界、JSONL 结构与许可说明。
- [AI Growth Ops 系统设计文档 v1.0](docs/AI-Growth-Ops-系统设计文档-v1.0.md)：产品设计目标，包含尚未实现的设想，不应视作当前功能清单。
