# RLCS Tactics 进度大屏

纯标准库 (`/usr/bin/python3` 3.6, `http.server`)，绑定 `127.0.0.1:18765`，运行于 **login006**。页面每 30 秒自动刷新。

## 运行与自动拉起
- `ensure.sh`：若 tmux 会话 `dash` 不存在则创建，会话内运行 `watchdog.sh`（仅在 login006 上生效）。
- `watchdog.sh`：每 30 秒 `curl /healthz`，挂了就重新启动 `server.py`。日志：`tactics/logs/dashboard-*.log`。
- crontab：`*/5 * * * *` 与 `@reboot` 调用 `ensure.sh`（cron 是节点本地的，只在 login006 上有效）。
- Mac 端转发：`ssh -N -L 18765:127.0.0.1:18765 cheaha-tunnel`，浏览器打开 http://127.0.0.1:18765/

## 数据约定（均相对 `tactics/`）
| 来源 | 格式 |
|---|---|
| `status/phases.json` | `{"updated": "...", "phases":[{"id":"P0","name":"...","status":"not_started|in_progress|done|blocked","started":"YYYY-MM-DD HH:MM","finished":"","conclusion":"..."}]}` |
| `runs/<run>/metrics.jsonl` | 每行一个 JSON：`{"step":100,"epoch":1,"split":"train","loss":0.5,"val_acc":0.7}`；除 step/epoch/time/split 外的数值字段各画一条曲线，所有 run 叠加。可选 `runs/<run>/meta.json`。runs/ 被 gitignore。|
| `logs/*.log` | 纯文本（agent/Codex 会话与操作），显示最新 30 个文件末尾 20 KB。logs/ 被 gitignore。|
| `results/<name>.json` | `{"method":"TAGNet","task":"next_touch","split":"test","is_baseline":true,"metrics":{"acc":0.61,"f1":0.55},"lower_is_better":["nll"],"notes":"..."}`；按 task/split 分组成表，每列最优加粗绿色。|
| `PROGRESS.md` | Markdown，简单渲染。|
| SLURM | 实时执行 `squeue -u $USER`。|
