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
