# RLCS tactics research — progress log

## P0 environment — 2026-10-31

**Data (from ../README.md, 2026-10-30):** 49,259 parsed games, 591.2 M frames @30 fps; seasons
2021-22 11,699 / 22-23 15,410 / 2024 7,307 / 2025 7,081 / 2026 7,762 games. Modes 1v1/2v2/3v3 =
1,586 / 786 / 46,793. 134 parse failures (0.3%), 26 replays deleted from ballchasing. Frames 128 GB
(`data/frames/fps30/<season>/part-*.parquet`, ~200 games/shard, one row group per replay; ball +
p0..p5 float32 features, NaN for missing players); index parquet per shard (status, n_players,
n_frames, players JSON, replay_meta JSON). `data/` total 274 GB. Manifest `data/manifest/replays.jsonl`
gives `group_path` (season/event/region/stage/.../series) for 22-23..2026; 2021-22 group tree via
Kaggle folder path / `__ballchasing_info.ijson`. No tactical labels → self-supervised or derived
supervision (goals, outcome). Split by series/event/season, never by game.

**GPU (job 41104643, node c0254, amperenodes):** NVIDIA A100 80GB PCIe (81,920 MiB), driver
550.90.07, max CUDA 12.4; RHEL 7.9, glibc 2.17. amperenodes: 20 nodes × 2 A100 (17 mix, 2 idle,
1 drain at check time). Node-local `/local` (= `$TMPDIR` = /scratch/local) 5.9 TB free on c0254.

**PyTorch (job 41104646):** `rc/torch/7` is Lua Torch7 — not usable. Working recipe
(`slurm/torch_probe.sh`): `module reset; module load Miniforge3/24.3.0-0`; conda env (Python 3.11)
in `$TMPDIR/dlenv`; `pip install torch==2.5.1 --index-url .../whl/cu121` → torch 2.5.1+cu121,
cuDNN 9.1, cuda available, bf16 matmul 218.5 TFLOPS. Env 5.1 GB, built in ~1.5 min per job.
Note: `module purge` breaks module loading — use `module reset`. pip `pyarrow` (newest) fails to
build on glibc 2.17; numpy not installed.

**Next:** install numpy/pandas/pyarrow from conda-forge (or pin manylinux2014 wheels) in the env
script; consider a cached env tarball to unpack into $TMPDIR; then P1 dashboard + P2 literature.

## P1 进度大屏 — 2026-10-31 14:55 CET（已上线）
- 服务：login006 127.0.0.1:18765，标准库 http.server（/usr/bin/python3 3.6），tmux 会话 dash + watchdog.sh（30s 健康检查自动拉起）+ crontab */5 与 @reboot 调 ensure.sh。
- Mac 转发：ssh -N -L 18765:127.0.0.1:18765 cheaha-tunnel → http://127.0.0.1:18765/ ，已 curl 验证。
- 数据约定见 tactics/dashboard/README.md（status/phases.json、runs/*/metrics.jsonl、logs/*.log、results/*.json）。
- 下一步：各阶段完成时更新 status/phases.json 和本文件。

## P0b DL environment — 2026-10-31
`tactics/slurm/env.sh` (source inside a job): `module reset; module load Miniforge3/24.3.0-0`; unpacks
`tactics/envs/dlenv.tar.gz` (conda-pack, 3.16 GB, git-ignored) into `$TMPDIR/dlenv` in **49 s**
(fresh build with `REBUILD=1`, repack with `PACK=1`: 277 s). Versions: Python 3.11, torch 2.5.1+cu121,
numpy 2.4.6, pandas 3.1.0, pyarrow 25.0.0 (conda-forge), torch_geometric 2.8.1 + torch_scatter OK;
pyg-lib disabled (needs glibc 2.27). Check jobs 41104648 (build+pack) / 41104652 (unpack): read
rlcs-2024 shard (199 row groups, 127 cols; replay 0 = 13,587 frames × 125 float cols) and moved it to A100.

## Direction change — 2026-10-31 (创奇)
Goal is no longer to beat baselines/SOTA but to produce a fun, interesting study. Reference: TAGNet
(IEEE ToG 2026, DOI 10.1109/TG.2026.3745970; label-free self-supervised graph learning finds
interpretable CS2 defensive patterns, links them to context statistically, team fingerprints).
P2 output = interesting research questions/hypotheses + methods + statistical/robustness plan +
expected visual cases; baselines only as controls. **New P4 criterion:** converge once findings are
interesting, credible, interpretable and pass statistical and robustness tests. Splits, citation
verification and cluster rules unchanged. P2 design running (Codex, ultra).

## P2 design — 2026-10-31
TAGNet PDF read in full (Codex ultra). Design `docs/P2_design.md` "The Grammar of Rotation":
7 RQs — RQ1 reusable temporal grammar of 3-man rotation; RQ2 handoff gaps vs conceding risk;
RQ3 pressure (late/trailing/OT) redistributes cover; RQ4 player vs roster vs org style fingerprints
and 2021→2026 meta evolution; RQ5 measurable pre-goal 势 (history beyond current state) +
model-based counterfactual scenarios; RQ6 compensation for low boost/demolition; RQ7 tactical
"conversation" within a series. Headline order: RQ1 > RQ3 > RQ4. Split train 21-22/22-23/2024,
val 2025, test 2026 (+event-wise), 3v3 primary; series-bootstrap, mixed effects, Holm over 3
confirmatory tests; robustness: seeds, K, windows, fps, field mirror/team swap. Controls: handcrafted
+k-means, PCA, GRU-AE, static GNN, TAGNet-style, GBDT value model. 11 verified refs
(`docs/references.bib`, `refs/literature.jsonl`). Next: P3-A data/measurement audit (clock, touches, IDs).

## P3 small-scale run 1–2 — 2026-10-31 16:25 CET
Pipeline (Codex ultra; `tactics/src/tactics_code`: audit → stage → extract → tokens(RQ1) → pressure(RQ3) → style(RQ4) → viz)
runs end-to-end on 1,500 3v3 replays (300/season, whole series) in ~8 min on 1 A100 (jobs 41104697, 41104704; 1 h limit).
Audit: 49,393 index rows = 49,259 ok + 134 failed; the 94-game gap = odd-player games (5-player 87, 1/3-player 7 …) confirmed.
Series coverage 100%, stable player IDs 100%; replay_meta has no timed goals.
**Problem found:** `game state` codes are replay-specific object ids (e.g. {66,72,127}, {80,89,137}, a 5-code 2025 variant), so the
global state map gave only 470k live frames of 11.9 M and 0 detected goals → RQ3/RQ4 gated (no score context), RQ1 ran on only
5,268 windows (K=8, val recon 0.687; RQ1 p=0.023, Holm 0.069 — not trustworthy yet). Fix in progress: per-replay decoding
(live = dominant code while ball-has-been-hit; goal = leaving live with |ball y|>5000, sign gives scorer; OT after 0-s regulation end),
validated against summed player Goals. Infra fixes: env.sh nounset-safe, conda-forge matplotlib/statsmodels, no tee/`set -u` (bash 4.2).

## P3 small run 3 (decoding fixed) — 2026-10-31 17:11 CET
Job 41104720 (1,500 3v3 replays, 38 min, 1 A100). Goal agreement 99.2% (1426/1438), 6,381 goals, 0 decode failures.
RQ1: 120,524 windows, K=8, val recon 0.637; learned-token excess gain 0.0049 bits/jump, p=0.001 (999 nulls), Holm 0.003;
heldout predictive gain -0.0013 bits (learned) / +0.0007 (handcrafted). Significant but very small → needs scale + seed check.
RQ3 primary (uncovered fraction, late×trailing): +0.023, SE 0.016, p=0.155, series bootstrap CI [-0.008, 0.053] → not significant.
Secondary: third-man depth -740 uu (CI [-969,-521], p=1.1e-8, BH q=2.3e-6): trailing late teams push the last man up. MixedLM did not converge.
RQ4: 0 eligible rosters (needs >=20 series) → insufficient data. Exploratory BH: 16/203 discoveries.
Next: medium run 41104745 (1,500 replays/season = 7,500, NULLS=499, 3 h limit; est. ~1.5 h).
