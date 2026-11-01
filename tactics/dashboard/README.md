# RLCS 只读研究仪表盘

10 个中英页签：总览、数据集、发现与创新、实验对比、训练曲线、作业、会话日志、论文、参考文献和研究记录。浏览器只读取同源接口，无 CDN。所有结构化时间显示 **CET（固定 UTC+1）**；不是夏季 UTC+2。

## 本地启动

```bash
cd ~/rlcs-codex/work/dash/dashboard
DASH_OFFLINE=1 python3 server.py 18766
```

打开 `http://127.0.0.1:18766/`。默认离线，绑定 `127.0.0.1`，不执行 Slurm 查询。后端兼容 Python 3.6.8，仅用标准库，不使用新版日期解析或时区模块；文本文件明确 UTF-8。端口优先级为命令行、`DASH_PORT`、18765。

- `DASH_DATA_ROOT`：数据根目录，默认是 dashboard 的父目录。
- `DASH_REFERENCE_ROOT`：可选的本地参考目录。额外读取训练指标；仅在数据根目录没有 `paper/` 时读取参考论文。界面明确标为历史样例。默认不启用，不复制样例到真实数据目录。
- `DASH_PROJECT_ROOT`：用于核验 WorkDir 的绝对项目路径，默认展开 `~/workspace/rlcs-replays`。本地审阅远端快照时只能按已知真实路径配置，不能补造 WorkDir。
- `DASH_OFFLINE=1`：明确禁用集群命令；未设置时也默认禁用。历史在线适配器仅在显式 `DASH_OFFLINE=0` 时可调用。本次工作未启用它，也未运行部署脚本。

本地参考审阅：

```bash
DASH_OFFLINE=1 DASH_REFERENCE_ROOT=~/rlcs-codex/work/dashref python3 server.py 18766
```

## 数据与接口

| 接口 | 数据来源 |
|---|---|
| `/api/host` | 本机名、端口、带偏移时间 |
| `/api/phases`、`/api/dataset`、`/api/ideas`、`/api/highlights` | 对应 `status/*.json` |
| `/api/job_purposes` | `status/job_purposes.json`，按精确作业名提供 `zh` / `en` 用途 |
| `/api/jobs` | 离线读取 `status/jobs_cache.psv`，过滤后计算作业与资源用量 |
| `/api/slurm`、`/api/squeue` | 兼容旧接口，同样仅返回已核验 WorkDir 的作业 |
| `/api/results` | `results/*.json`；每个 JSON 最大 16 MiB，与原服务相同 |
| `/api/runs` | 下列三种训练目录 |
| `/api/logs` | 最近 30 个 `logs/*.log`，每个最多末尾 20 KiB |
| `/api/paper` | 从 `paper/main.tex` 递归统计，保留状态表的投稿目标和引用核验信息 |
| `/paper.pdf` | 只读 `paper/main.pdf`；仅 GET/HEAD，缺失返回 404 |
| `/api/literature` | `refs/literature.jsonl` |
| `/api/progress` | `PROGRESS.md` |
| `/healthz` | `ok` |

### 作业

PSV 必须含标题行；支持字段：`JobID,JobName,Partition,State,Elapsed,Timelimit,AllocCPUS,ReqMem,MaxRSS,AllocTRES,NodeList,Start,End,WorkDir`。额外字段允许存在。

只包含 WorkDir 等于项目根或位于其子目录的记录。排除缺失、未知、相似前缀、逃逸路径和作业步骤；不根据作业名猜归属。资源合计、兼容接口和运行中卡片使用同一过滤结果。当前仓库的 `dashx/sacct_dash.psv` 是解析器回归快照，缺少 WorkDir，**不作为项目作业展示来源**。

历史 PSV 的无偏移时间遵循既有 `America/Chicago` 导出约定；有偏移时间按原偏移转换。夏令时重复或不存在的本地时间为未知。剩余时长为有效申请时长减来源快照的已用时长、最低为零；未知或无限时长不推算。缓存更新时间始终可见，浏览器不会随时钟伪造实时用量。

### 训练曲线

扫描：

```text
runs/*/metrics.jsonl
robust/*/runs/*/metrics.jsonl
artifacts/*/runs/*/metrics.jsonl
```

读取相邻 `meta.json`。嵌套目录用相对路径作为唯一标识，避免同名运行互相覆盖。保留原始有限数值、step/epoch/time 和 split，损坏行跳过，大文件按 split 保留首末点并有界抽样。单位仅来自 `metric_units`；缺失显示未知，按运行分图。缺失指标断线，不含所选指标的运行不绘图。可选择指标、横轴、划分及运行，支持悬停或键盘检查精确读数。

### 论文

扫描 `main.tex` 及 `input/include`，支持正文中的 section/chapter 和摘要，不执行 TeX、Makefile 或任意命令。字数是去掉注释和常用命令后的英文 token 加汉字数，属于近似计数；图数按 `figure` / `figure*` 环境计数，图表清单列出 `includegraphics` 引用。

- 有正文默认“草稿”，空正文“未开始”，缺失/逃逸文件“未知”。TODO/FIXME/TBD 保持草稿。
- 可在章节正文内写 `% dashboard-status: done`、`review`、`draft` 或 `not_started`；不由有正文推断论文已完成。
- 总进度为明确完成章节数 / 全部识别章节数；缺失文件或无章节时为未知。计数注明是否仅为已读文件小计。
- commit 来自本地 `git log -- paper` / 对应源文件；未纳入 Git 时未知。
- 可选本地 `pdfinfo -isodates` 提供页数与 PDF CreationDate。工具或元数据缺失时相应字段未知，不靠正则猜压缩 PDF 页数。
- PDF 创建元数据仅作为编译时间证据展示，文件修改时间单独显示。PDF 文件 commit 不冒充编译所用源码 commit。缺 PDF 时显示双语占位。
- 这不是完整 TeX 解释器；宏生成的章节、条件编译和自定义图环境不会被执行或推测。

## 双语与旧版功能

文本优先使用对应语言字段；术语表在 `dashboard/i18n_map.json`。不可翻译的 ID、路径、作业名保留原始标识。缺少译文会触发控制台告警，检查脚本阻止交付。

保留旧版的十个页面与 `#/slurm` 路由别名、阶段/下一步、候选状态筛选、赛季和比赛模式图、基线指标对比、日志筛选、引用核验、研究记录的安全 Markdown（标题、列表、表格、引用、代码和链接）等。原始指标柱图与效应量置信区间并存。基线差值仅在任务、划分、单位、方向明确一致时计算，未知不补零。

## 本地验证与全页截图

```bash
cd ~/rlcs-codex/work/dash
python3 -B -m unittest dashboard.test_server dashboard.test_dashboard_features -q
node dashboard/test_app.js
DASH_REFERENCE_ROOT=~/rlcs-codex/work/dashref node dashboard/check_i18n.js
node dashboard/review_browser.js http://127.0.0.1:18766 ~/rlcs-codex/work/dash_review
```

浏览器审阅使用已安装的 headless Chrome 和 Node 22+ 的原生 WebSocket，不安装包；可通过 `CHROME` 指定本地 Chrome 可执行文件。逐页输出 `zh-*.png`、`en-*.png` 和 `browser-review.json`，检查英文 CJK、翻译缺失、脚本异常、页面宽度溢出和外部请求。单元测试中的合成数据仅存在于临时目录，不写入研究数据目录。
