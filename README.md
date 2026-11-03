# Tactics in Professional Rocket League (RLCS)

How do the best Rocket League teams in the world actually play? This repository turns five seasons of
official **Rocket League Championship Series (RLCS)** replays into per-frame trajectories and studies
team tactics, score-state behaviour and individual player style at scale.

Rocket League is "car football": two teams of three rocket-powered cars try to hit an oversized ball
into the opposing goal. Every professional match is recorded as a replay file, which gives a complete,
frame-by-frame record of where every car and the ball were. The project started purely out of curiosity
about the game, and grew into a research paper (target: *IEEE Transactions on Games*).

## What is in here

| Path | Contents |
|---|---|
| `scripts/` | Download (Kaggle mirror, ballchasing.com API) and replay parsing with [subtr-actor](https://github.com/rlrml/subtr-actor) |
| `tactics/src/` | Analysis code: feature extraction, score-state analyses, tactic tokens, player-fingerprint retrieval, deep-learning experiments (`ai_experiments/`, `pilot_encoder/`) |
| `tactics/slurm/` | SLURM job scripts used on the UAB Cheaha cluster |
| `tactics/docs/` | Pre-registrations, implementation notes and result write-ups |
| `tactics/results/` | Aggregated result files (JSON) behind the paper's numbers |
| `tactics/paper*/` | LaTeX source, figure scripts and figures of the paper and its supplement |
| `tactics/dashboard/` | Bilingual (EN/中文) progress dashboard |

## Research questions

1. **Score state** — do teams position and pressure differently when leading, tied or trailing?
2. **Structure** — what recurring spatial patterns ("tactic tokens") describe team play, and how do they change across seasons?
3. **Player style** — does each pro player leave a recognisable movement fingerprint that can be retrieved from trajectories alone?
4. **Deep learning** — can learned trajectory encoders beat hand-crafted features for these tasks?

All results are reported as associations from observational data, with confidence intervals; negative
and boundary results are kept in the supplement.

## Data

| Season | Parsed games | Frames (30 fps) |
|---|---|---|
| RLCS 2021-22 | 11,699 | 139.9 M |
| RLCS 22-23 | 15,410 | 184.3 M |
| RLCS 2024 | 7,307 | 87.5 M |
| RLCS 2025 | 7,081 | 85.1 M |
| RLCS 2026 | 7,762 | 94.3 M |
| **Total** | **49,259** | **591.2 M** |

Replays come from the public Kaggle mirror `rolvarild/rocket-league-championship-series-replays` and the
official RLCS groups on [ballchasing.com](https://ballchasing.com). **Raw replays and frame data are not
included in this repository** (about 210 GB); re-create them with the scripts below. The Kaggle data carry
no licence statement, so use them for research only and cite the dataset and ballchasing.com.

## Reproducing

```bash
bash setup_env.sh            # once: build .venv (cluster module SciPy-bundle/2023.11)
source env.sh                # every shell
echo "BALLCHASING_API_KEY=..." > .env   # never committed
bash scripts/download_kaggle.sh
python scripts/ballchasing.py
sbatch scripts/parse_slurm.sh
```

Analysis and paper jobs are under `tactics/slurm/`; see `tactics/PROGRESS.md` for the current state.

## Citation

Paper in preparation. Please cite this repository, the RLCS replay dataset and ballchasing.com if you use the code.
