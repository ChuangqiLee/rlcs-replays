# RLCS replays → per-frame data

Official RLCS replays (uploaded to ballchasing.com by "RLCS Referee") parsed into per-frame ball and
player coordinates with [subtr-actor](https://github.com/rlrml/subtr-actor).

## Environment

The home filesystem (GPFS) is very slow at creating many small files, so the heavy packages come
from the cluster module `SciPy-bundle/2023.11-gfbf-2023b` (Python 3.11.5, numpy, pandas, scipy,
requests) and `.venv` only adds what is in `requirements.txt`.

```bash
bash setup_env.sh   # once: build .venv
source env.sh       # every shell: load module + activate .venv
```

Put the ballchasing API key in `.env` (never committed):

```
BALLCHASING_API_KEY=...
```

## Data sources

| Season | Source |
|---|---|
| RLCS 2021-22 | Kaggle mirror `rolvarild/rocket-league-championship-series-replays` |
| RLCS 22-23, 2024 | Kaggle mirror, plus any replays of the official ballchasing groups missing from it |
| RLCS 2025, 2026 | ballchasing API (official groups `rlcs-2025-7ielfd7uhx`, `rlcs-2026-d3chsz8nje`) |

The Kaggle datasets carry no licence statement; use them for research only, do not redistribute
the raw files, and cite the dataset and ballchasing.com.

## Dataset summary (as of 2026-10-30)

All five seasons are downloaded and parsed; there is no need to download again. To get another
frame rate or extra features, re-parse the raw replays with `scripts/parse_replays.py`.

| Season | Parsed games | Frames (30 fps) | 1v1 / 2v2 / 3v3 games |
|---|---|---|---|
| RLCS 2021-22 | 11,699 | 139.9 M | 0 / 1 / 11,671 |
| RLCS 22-23 | 15,410 | 184.3 M | 1 / 2 / 15,397 |
| RLCS 2024 | 7,307 | 87.5 M | 0 / 0 / 7,301 |
| RLCS 2025 | 7,081 | 85.1 M | 715 / 3 / 6,320 |
| RLCS 2026 | 7,762 | 94.3 M | 870 / 780 / 6,104 |
| **Total** | **49,259** | **591.2 M** | 1,586 / 786 / 46,793 |

Games with an odd number of players (a player missing or disconnected) make up the rest.
134 replays failed to parse (0.3%) and are listed in the index files with the error: mostly a
player joining or leaving mid-game, or more than six players in the header. 26 replays of the
official groups were deleted from ballchasing before they could be downloaded.

Frame data takes 128 GB (`data/frames/fps30`); raw replays take 56 GB (Kaggle, extracted) and
25 GB (ballchasing tar shards).

## Raw replays and metadata

- `data/raw/kaggle/<Kaggle season folder>/…/<ballchasing id>.replay`: the folder path follows the
  ballchasing group tree (season / event / stage / round / series). Each season folder has
  `__ballchasing_info.ijson`, one ballchasing list item per line (id, title, date, map, duration,
  overtime, groups, blue/orange teams and players).
- `data/raw/ballchasing/<season>/batch-*.tar` with `batch-*.ids.json`: replays downloaded from the
  API (2025, 2026, and one 2024 replay missing from Kaggle).
- `data/manifest/replays.jsonl`: every replay of the official groups for 22-23 to 2026, with
  `id`, `season`, `group`, `group_path` (season / split or event / region / stage / … / series),
  `title`, `date`, `rocket_league_id`, `duration`, `playlist` and `map`.
  `data/manifest/groups.jsonl` holds the group tree.
- Replay ids are ballchasing ids and match `replay_id` in the frame data.

## Pipeline

Each step is resumable; re-running continues where it stopped. Long steps run in `tmux`
(`tmux ls`, `tmux attach -t <name>`).

```bash
# 1. Kaggle mirror: ~70 GB zip, extracts only the three seasons above
tmux new -d -s kaggle "bash scripts/download_kaggle.sh 2>&1 | tee -a logs/kaggle.log"

# 2. Walk the official group trees -> data/manifest/{groups,replays}.jsonl
tmux new -d -s crawl "bash scripts/run_forever.sh crawl"

# 3. Download the replays not in the Kaggle mirror -> data/raw/ballchasing/<season>/batch-*.tar
#    (staged on the login node's /local, packed to GPFS every 500 replays; batch-*.ids.json lists
#    each shard's replays and marks it complete). Run it on one login node; restart it there.
tmux new -d -s download "bash scripts/run_forever.sh download"

python scripts/ballchasing.py status   # progress per season

# 4. Parse to Parquet (30 fps) on a compute node -> data/frames/fps30/<season>/part-*.parquet
sbatch scripts/parse_slurm.sh   # re-submit after more downloads; parsed replays are skipped
```

Rate limits follow https://ballchasing.com/doc/api per endpoint and Patreon tier. The tier is read
from `GET /api/` every 5 minutes, so a tier upgrade speeds up running jobs without a restart.
Hourly call counts are stored in `data/state/` so restarts don't exceed them. `run_forever.sh`
restarts a crashed job after 60 s and stops on success or on a fatal error (rejected API key, or
the same job already running); failures are logged in `logs/` and `data/state/download_failed.jsonl`.

## Frame data

GPFS stalls when many files are created in one directory, so replays are stored in shards of
about 200 games:

- `part-<run>-<k>.parquet`: frames, one row per frame (30 fps) and one row group per replay.
  Columns `replay_id`, `frame`, then float32 features:
  - Ball: position, rotation, linear and angular velocity (x/y/z); `current time`, `frame time`,
    `seconds remaining`, `game state`, `ball has been hit`
  - Players `p0 … p5`: position, rotation, linear and angular velocity,
    `boost level (raw replay units)`, `dodge/jump/double jump active`, `any_jump_active`,
    `player demolished by`. NaN for games with fewer than 6 players.
- `part-<run>-<k>.index.parquet`: one row per replay: `status` (`ok`/`failed` with `error`),
  `n_players`, `n_frames`, `players` (JSON, in column order) and `replay_meta` (JSON header metadata).

Players are ordered team 0 (blue) then team 1 (orange); this was checked against kickoff positions.
The order of players within a team follows the replay header.

```python
import glob, json, pyarrow.dataset as ds
base = "data/frames/fps30"
index = ds.dataset(glob.glob(f"{base}/*/*.index.parquet")).to_table().to_pandas()
frames = ds.dataset([p for p in glob.glob(f"{base}/*/*.parquet") if not p.endswith(".index.parquet")])
rid = index.query("status == 'ok'").replay_id.iloc[0]
df = frames.to_table(filter=ds.field("replay_id") == rid).to_pandas()
players = json.loads(index.set_index("replay_id").loc[rid, "players"])
```

## Notes for modelling

- There are no tactical labels; any supervision has to be derived from the data (for example from
  the frame features, goals or match outcome in `replay_meta`) or learned without labels.
- Games of the same series, and games of the same teams and players within a season, are strongly
  correlated. Split train / validation / test by series, event or season, never by individual game.
- The GitHub repository (`git@github.com:ChuangqiLee/rlcs-replays.git`, private) holds the code
  only; `data/`, `logs/` and `.env` are never committed.
