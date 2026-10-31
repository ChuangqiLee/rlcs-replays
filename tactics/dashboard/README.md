# RLCS 战术研究进度大屏

> 当前双语离线版本、`/api/jobs`、数据模式、测试和 Python 3.6.8 兼容性说明见 [CHANGES_dash.md](CHANGES_dash.md)。本地开发使用 `DASH_OFFLINE=1 python3 dashboard/server.py`（从项目根目录执行），禁止触发 Slurm 查询。下文保留历史部署与数据格式说明；本次未操作集群。

中英双语只读大屏，包含总览、数据集、创新点、实验对比、训练曲线、SLURM、会话日志、论文与 PROGRESS.md 九个页面。采用深色卡片与侧栏导航，页面每 30 秒刷新，可手动刷新。后端仅依赖 Python 3.6+ 标准库（兼容 3.6.8），绑定 `127.0.0.1`。

前端只加载本地 JS/CSS，全部图表使用原生 SVG，没有 CDN 或外部字体依赖。PROGRESS.md 显示转义原文，不执行 HTML 或加载远程图片。

## 部署位置与启动

本次交付的 `out/` 是文件暂存目录。**应用文件放入 `tactics/dashboard/`，数据文件放入 `tactics/status/`。** 后端的 `HERE` 是 `server.py` 所在目录，`ROOT` 是 `HERE` 的父目录，即 `tactics/`。不要把数据放到 `tactics/dashboard/status/`，也不要期望直接运行暂存目录时会自动读取 `out/status/`。

```text
tactics/
├── dashboard/
│   ├── server.py
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── watchdog.sh         # 保留现有脚本与文件名
│   └── ensure.sh           # 保留现有脚本与文件名
├── status/
│   ├── phases.json         # 研究流程自行维护
│   ├── dataset.json        # 将 out/status/dataset.json 放到这里
│   ├── ideas.json          # 将初始示例放到这里，已有数据则保留
│   └── paper.json          # 将初始示例放到这里，已有数据则保留
├── results/*.json
├── runs/<run>/metrics.jsonl
├── runs/<run>/meta.json    # 可选
├── logs/*.log
└── PROGRESS.md
```

将 `out/server.py`、`out/index.html`、`out/style.css`、`out/app.js` 复制到现有 `tactics/dashboard/`，将三个初始 JSON 放到 `tactics/status/`。已有研究状态应合并字段，勿用空白示例覆盖。此交付不提供、替换或改名现有 `watchdog.sh` 和 `ensure.sh`。

```bash
cd /绝对路径/tactics/dashboard
python3 server.py
# 指定端口，优先级：命令行参数 > DASH_PORT > 18765
python3 server.py 18765
DASH_PORT=18765 python3 server.py
```

浏览器打开 `http://127.0.0.1:18765/`，健康检查 `GET /healthz` 返回纯文本 `ok`。远程访问可沿用已有 SSH 转发：

```bash
ssh -N -L 18765:127.0.0.1:18765 cheaha-tunnel
```

## watchdog、tmux 与 cron

沿用 **tmux 会话 `dash` 运行 `watchdog.sh`，cron 调用 `ensure.sh`** 的方式。现有 `watchdog.sh` 每 30 秒检查健康端点，必要时重启 `server.py`，日志写入 `tactics/logs/dashboard-watchdog.log` 和 `tactics/logs/dashboard-server.log`。现有 `ensure.sh` 在会话不存在时创建会话，并限制只在 `login006` 执行；应在该节点配置 cron。

```bash
cd /绝对路径/tactics/dashboard
bash ensure.sh
tmux has-session -t dash
tmux attach -t dash
# 如需手工首次启动，并已确认没有 dash 会话：
tmux new-session -d -s dash 'bash /绝对路径/tactics/dashboard/watchdog.sh'
```

在该节点的 crontab 中使用真实绝对路径，保留脚本名：

```cron
*/5 * * * * /bin/bash /绝对路径/tactics/dashboard/ensure.sh
@reboot /bin/bash /绝对路径/tactics/dashboard/ensure.sh
```

若改变端口，在启动 tmux 的环境和 cron 中一致设置 `DASH_PORT`；现有 tmux 会话不会自动继承后来修改的环境。替换应用文件后，需重新启动实际运行的 Python 服务以加载后端；健康的旧进程不会被 watchdog 自动替换。无需创建第二个 `dash` 会话。

## 通用数据约定

- 下列路径均相对 `tactics/`，UTF-8 编码；JSON 使用有限数值，不写 `NaN` 或 `Infinity`，未知值使用 `null`。
- `updated`、`started`、`finished`、训练 `time` 等时间戳使用带偏移的 ISO 8601，如 `2026-10-31T15:00:00+01:00` 或 `2026-10-31T14:00:00Z`；未知时间用 `null`。`as_of` 是日历日期 `YYYY-MM-DD`。
- 前端通过 `Intl` 的 `timeZone: "Europe/Amsterdam"` 转换结构化时间，并按要求统一标注 `CET`。该时区会自动执行夏令时；标签固定为 CET，不代表全年固定 UTC+1。日志正文中带偏移的 ISO 时间戳也转换为 CET，其他日志文本保持原样；建议生产端使用带偏移的时间戳。
- 进度 `progress` 范围为 `0`–`100`。缺失数据展示空态，部分读取失败或格式错误会显示提示；单个结果文件缺失或无法解析时由服务器跳过，不保证逐个显示错误。不伪造实验或作业数据。
- 建议 JSON 先写临时文件再原子重命名；JSONL 逐行追加完整 JSON，最后一行尚未写完时会跳过，后续刷新可恢复。
- 下列 JSON 是结构与字段示例，其中实验成绩、方法与时间均为**示例**，不属于真实结果。交付数据仅包含已提供的数据集统计、空创新点和未开始的论文状态。

## 1. `status/phases.json`

顶层对象包含 `updated` 和 `phases` 数组，可选 `current_phase` 显式指定当前阶段 ID。六个阶段使用稳定 ID `P0`–`P5`；每项有 `id`、`name`、`status`，可选 `started`、`finished`、`conclusion`。状态为 `not_started`、`in_progress`、`done` 或 `blocked`。总览优先使用有效的 `current_phase`；否则依次选择最后一个正在进行的阶段、受阻阶段、下一个未开始阶段，最后回退到最后一个阶段。时间线展示各阶段结论。

```json
{
  "updated": "2026-10-31T15:00:00+01:00",
  "phases": [
    {"id": "P0", "name": "环境", "status": "not_started", "started": null, "finished": null, "conclusion": ""},
    {"id": "P1", "name": "进度大屏", "status": "not_started", "started": null, "finished": null, "conclusion": ""},
    {"id": "P2", "name": "文献与创新", "status": "not_started", "started": null, "finished": null, "conclusion": ""},
    {"id": "P3", "name": "实验", "status": "not_started", "started": null, "finished": null, "conclusion": ""},
    {"id": "P4", "name": "达标即停", "status": "not_started", "started": null, "finished": null, "conclusion": ""},
    {"id": "P5", "name": "论文", "status": "not_started", "started": null, "finished": null, "conclusion": ""}
  ]
}
```

旧版不带偏移的时间应改为以上格式，避免将集群本地时间误当成浏览器本地时间。本交付未复制旧版历史阶段，避免把旧状态当作当前状态。

## 2. `status/dataset.json`

字段：`as_of` 日期，`fps` 帧率，`totals` 总量，`seasons` 分赛季数组，`storage` 存储数组，`split_protocol` 划分协议，`notes` 说明数组。帧数以帧为单位，`gb` 按来源 GB 口径记录，未知路径为 `null`。

```json
{
  "as_of": "2026-10-30",
  "fps": 30,
  "totals": {
    "seasons": 5, "games": 49259, "frames": 591200000,
    "modes": {"1v1": 1586, "2v2": 786, "3v3": 46793},
    "failed": 134, "failed_rate_percent": 0.3, "deleted": 26
  },
  "seasons": [
    {"name": "RLCS 2021-22", "games": 11699, "frames": 139900000, "modes": {"1v1": 0, "2v2": 1, "3v3": 11671}},
    {"name": "RLCS 22-23", "games": 15410, "frames": 184300000, "modes": {"1v1": 1, "2v2": 2, "3v3": 15397}},
    {"name": "RLCS 2024", "games": 7307, "frames": 87500000, "modes": {"1v1": 0, "2v2": 0, "3v3": 7301}},
    {"name": "RLCS 2025", "games": 7081, "frames": 85100000, "modes": {"1v1": 715, "2v2": 3, "3v3": 6320}},
    {"name": "RLCS 2026", "games": 7762, "frames": 94300000, "modes": {"1v1": 870, "2v2": 780, "3v3": 6104}}
  ],
  "storage": [
    {"name": "帧数据 · 30 fps", "path": "data/frames/fps30", "gb": 128},
    {"name": "原始回放 · Kaggle（已解压）", "path": null, "gb": 56},
    {"name": "原始回放 · ballchasing（tar 分片）", "path": null, "gb": 25}
  ],
  "split_protocol": {
    "unit": ["series", "event", "season"],
    "rule": "按 series / event / season 分组划分训练、验证与测试集。",
    "notes": "同一分组不得跨集合；不按帧随机切分。具体集合清单与比例待实验协议确定。"
  },
  "notes": ["五个赛季均已下载并完成解析，无需重新下载。"]
}
```

所有统计来自提供的 `dataset_readme.md`，保留原值。来源的分赛季帧数四舍五入后相加为 **591.1 M**，而总计为 **591.2 M**；不能据此改写来源总计。1v1、2v2、3v3 合计外的 **94 场**是奇数玩家对局。134 次解析失败与 26 次下载前被删除各自单独报告，不从 49,259 场已解析对局中再次扣除。若需要其他帧率或特征，重新解析原始回放即可。

## 3. `status/ideas.json`

顶层 `updated` 可为时间戳或 `null`，`ideas` 为数组；初始交付为空。每项建议包含唯一 `id`、`name`、`status`、`motivation`、`inspiration_refs`、`prune_reason`、`best_metric`。状态限定为 `proposed`、`running`、`promising`、`pruned`、`selected`；存活数为非 `pruned` 的候选数量。引用使用文本或 `{title,url}` 对象；`best_metric` 可为 `null` 或下例对象。

```json
{
  "updated": null,
  "ideas": [
    {
      "id": "idea-example",
      "name": "示例候选方法",
      "status": "proposed",
      "motivation": "待填写研究动机与可验证假设。",
      "inspiration_refs": [{"title": "待核验的参考文献", "url": null}],
      "prune_reason": "",
      "best_metric": {"name": "acc", "value": 0.72, "task": "next_touch", "split": "test"}
    }
  ]
}
```

被剪枝时填写具体 `prune_reason`，未评估时将 `best_metric` 置为 `null`。不要将示例数值视为已取得的结果。

## 4. `results/<name>.json`

一个文件可包含单条结果对象或结果对象数组。必需字段为 `method`、`task`、`split`、布尔值 `is_baseline`、数值映射 `metrics`。可选 `lower_is_better` 指定越小越好的指标，默认其他指标越大越好；同一 task/split/metric 必须使用一致方向、单位和评估协议。可选 `notes`、`updated` 提供上下文。

```json
[
  {
    "method": "Baseline example", "task": "next_touch", "split": "test",
    "is_baseline": true, "metrics": {"acc": 0.61, "nll": 0.82},
    "lower_is_better": ["nll"], "notes": "示例基线",
    "updated": "2026-10-31T14:00:00Z"
  },
  {
    "method": "Ours example", "task": "next_touch", "split": "test",
    "is_baseline": false, "metrics": {"acc": 0.65, "nll": 0.76},
    "lower_is_better": ["nll"], "notes": "示例方法",
    "updated": "2026-10-31T14:00:00Z"
  }
]
```

结果按 **task + split** 分组，每个指标分别确定最佳值与最佳基线。Δ 为方向归一化的绝对差：越大越好时 `当前值 − 最佳基线值`，越小越好时 `最佳基线值 − 当前值`，因此正数始终表示提升，未换算百分比。没有基线的指标不计算 Δ，不跨任务、数据划分或指标比较裸数值。同组同指标的方向声明冲突时，停止计算该指标的最佳值和 Δ，并提示修正数据。缺失指标显示空值，不能当作 0。

## 5. `runs/<run>/metrics.jsonl` 与可选 `meta.json`

每个 `<run>` 为一个目录，`metrics.jsonl` 每行一个对象。保留字段为 `step`、`epoch`、`time`、`split`，其余有限数值字段均为可选曲线指标。`step`/`epoch` 为数值，至少提供一种；同一 run/split 内应递增。`time` 可为带偏移 ISO 时间戳或 UTC epoch 秒。`split` 建议为 `train`、`val`、`test`。不同 split 分开画线，支持选择指标并叠加不同 run。

```jsonl
{"step":100,"epoch":1,"time":"2026-10-31T14:00:00Z","split":"train","loss":0.84,"acc":0.55}
{"step":100,"epoch":1,"time":"2026-10-31T14:01:00Z","split":"val","loss":0.88,"acc":0.53}
{"step":200,"epoch":2,"time":"2026-10-31T14:05:00Z","split":"train","loss":0.73,"acc":0.61}
```

`meta.json` 为可选对象，可提供展示名称、方法、任务、状态、创建时间及参数；无该文件时使用目录名。

```json
{
  "name": "示例训练",
  "method": "Baseline example",
  "task": "next_touch",
  "is_baseline": true,
  "status": "running",
  "created": "2026-10-31T14:00:00Z",
  "config": {"seed": 42, "learning_rate": 0.0001, "batch_size": 64}
}
```

损坏、未完成或非对象的行会跳过；大日志会抽样以控制浏览器负载，所以曲线不用于替代原始指标的统计分析。

## 6. `logs/*.log`

UTF-8 纯文本；按文件修改时间降序取最新 **30** 个，每个只读取末尾 **20 KB（20,480 字节）**。界面提供筛选，显示文件名、修改时间和日志尾部。修改时间由服务器发送带偏移的 ISO 时间，前端统一转 CET。日志正文中带偏移的 ISO 时间戳转换为 CET，其余文本不变。

```text
2026-10-31T15:00:00+01:00 [INFO] 示例：启动一次训练
2026-10-31T15:05:00+01:00 [INFO] 示例：epoch=1 loss=0.84
```

## 7. `status/paper.json`

顶层字段为 `updated`、`target`、`sections`、`figures`、`citations`。`sections` 各项包含 `name`、`status`、`progress`；建议状态为 `not_started`、`in_progress`、`done`、`blocked`。总进度按章节百分比求平均。`figures` 各项可包含 `id`、`name`、`status`、`path`，用于跟踪，不自动公开文件下载。`citations.verified` 为已核验数，`citations.total` 为总数。

```json
{
  "updated": null,
  "target": "IEEE Transactions on Games",
  "sections": [
    {"name": "Introduction", "status": "not_started", "progress": 0},
    {"name": "Related Work", "status": "not_started", "progress": 0},
    {"name": "Dataset", "status": "not_started", "progress": 0},
    {"name": "Method", "status": "not_started", "progress": 0},
    {"name": "Experiments", "status": "not_started", "progress": 0},
    {"name": "Conclusion", "status": "not_started", "progress": 0},
    {"name": "Appendix", "status": "not_started", "progress": 0}
  ],
  "figures": [],
  "citations": {"verified": 0, "total": 0}
}
```

图表项结构示例（未加入初始状态）：

```json
{"id":"fig-1","name":"方法架构图","status":"not_started","path":null}
```

## 8. `PROGRESS.md`

UTF-8 Markdown，用于研究记录。marked 加载成功时支持常用标题、段落、列表、代码块、链接、表格等；离线时使用安全的基础 Markdown 渲染，没有文件时显示空态。渲染结果经过 HTML 清理，外部图片、脚本和不安全链接会被移除。

```markdown
# 研究进度

更新时间：2026-10-31T15:00:00+01:00

## 当前工作
- 待补充已完成事项与证据。

## 下一步
- 待补充下一项实验。
```

## 9. SLURM 数据与 API

SLURM 数据按服务器进程的 `$USER` 查询；`squeue` 使用分隔符格式解析出 `jobid`、`partition`、`name`、`state`、`time`、`limit`、`nodes`、`reason`。作业历史使用：

```bash
squeue -u "$USER" -h -o '%i|%P|%j|%T|%M|%l|%D|%R'
sacct -u "$USER" -S now-2days --format=JobID,JobName%30,State,Elapsed,End -P -n
```

两种命令各有 15 秒超时；未安装 SLURM、无权限或调度器暂时不可用时显示错误提示，其他页面仍可用。作业用时和限时为持续时长，无需转换时区。End 的有效日期转换为带偏移 ISO 时间，前端显示 CET；`Unknown` 等非日期值保留为空缺说明。结果可短暂缓存以避免重复请求调度器。

所有 API 均为只读 GET，返回 JSON，以下为返回形状：

| 端点 | 来源与响应 |
|---|---|
| `/api/host` | `{ "host": "主机名", "port": 18765, "time": "带偏移 ISO 时间" }` |
| `/api/phases` | `status/phases.json` 对象 |
| `/api/dataset` | `status/dataset.json` 对象 |
| `/api/ideas` | `status/ideas.json` 对象 |
| `/api/jobs` | 近三天 sacct / 本地缓存作业与资源统计，详见 CHANGES_dash.md |
| `/api/highlights` | `status/highlights.json` 对象 |
| `/api/paper` | `status/paper.json` 对象 |
| `/api/results` | `{ "文件名不含.json": 结果对象或数组 }` |
| `/api/runs` | `{ "run目录名": { "meta": {}, "rows": [] } }`，可能附带读取提示 |
| `/api/logs` | `{ "文件名.log": { "mtime": "带偏移 ISO 时间", "tail": "末尾文本" } }` |
| `/api/progress` | Markdown 字符串（JSON 字符串，不是 JSON 对象） |
| `/api/slurm` | `{ "queue": [], "history": [], "queue_error": null, "history_error": null, "updated": "带偏移 ISO 时间" }` |
| `/api/squeue` | `/api/slurm` 的兼容入口 |

队列项结构为 `{jobid, partition, name, state, time, limit, nodes, reason}`；历史项为 `{jobid, name, state, elapsed, end}`。字段值来自 SLURM 文本。静态入口为 `/`、`/index.html`、`/style.css`、`/app.js`，禁止路径穿越；其他研究文件通过对应 API 读取。

## 校验

最小 Python 语法校验（不会启动服务）：

```bash
python3 -c "import ast; ast.parse(open('server.py', encoding='utf-8').read()); print('server.py syntax OK')"
```

在交付目录运行自动验证：

```bash
python3 -m unittest dashboard.test_server -v
node dashboard/test_app.js
```

验证均离线执行，不访问网络。SLURM 测试使用模拟命令响应，未连接真实调度器；实际集群的权限、命令可用性和返回内容仍需部署后检查。

部署后检查健康端点、九个侧栏页面与数据缺失时的空态，并确认页头主机名、更新时间及页脚时区。若表格没有数据，首先检查数据是否放在 `tactics/` 下的约定路径。


## 参考文献 `refs/literature.jsonl`（/api/literature，页面 #/literature）
每行一个 JSON 对象，文件不存在或为空时显示空表；无法解析的行跳过：
```json
{"title":"...","authors":["A","B"],"venue":"IEEE Transactions on Games","year":2026,"category":"ToG","tier":"best_paper|oral|spotlight|accepted","doi_or_url":"10.1109/... 或 https://...","takeaway":"一句话借鉴点","verified_count":3,"added":"2026-10-31 15:30 CET"}
```
页面只显示三列：标题（有 `doi_or_url` 时可点击，`10.` 开头自动链接 https://doi.org/）、期刊/会议（venue）、年份；其余字段供记录用。
