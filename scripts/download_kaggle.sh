#!/bin/bash
# Download the Kaggle mirror of official RLCS replays (rolvarild/rocket-league-championship-series-replays,
# ~70 GB zip) and extract only the seasons we use. Safe to re-run: curl resumes a partial zip,
# and extraction skips files already on disk.
#
# Usage: bash scripts/download_kaggle.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL="https://www.kaggle.com/api/v1/datasets/download/rolvarild/rocket-league-championship-series-replays"
ZIP="$PROJECT_DIR/data/kaggle/rolvarild.zip"
OUT="$PROJECT_DIR/data/raw/kaggle"
SEASONS=("RLCS 2021-22" "RLCS 22-23" "RLCS 2024")

mkdir -p "$(dirname "$ZIP")" "$OUT"

if [ ! -f "$ZIP.complete" ]; then
    # Kaggle redirects to a short-lived signed URL, so each retry starts again from the Kaggle URL.
    for attempt in $(seq 1 20); do
        echo "[$(date -Is)] download attempt $attempt"
        if curl -fL -C - --retry 3 --retry-delay 10 -o "$ZIP" "$URL"; then
            touch "$ZIP.complete"
            break
        fi
        sleep 30
    done
    [ -f "$ZIP.complete" ] || { echo "download failed after retries" >&2; exit 1; }
fi
echo "[$(date -Is)] zip size: $(du -h "$ZIP" | cut -f1)"

# Python's zipfile handles Zip64 reliably and lets us extract a subset of members.
source "$PROJECT_DIR/env.sh"
python - "$ZIP" "$OUT" "${SEASONS[@]}" <<'EOF'
import sys, zipfile, pathlib
zip_path, out = sys.argv[1], pathlib.Path(sys.argv[2])
seasons = sys.argv[3:]
with zipfile.ZipFile(zip_path) as z:
    names = z.namelist()
    tops = sorted({n.split("/")[0] for n in names})
    print("top-level entries in zip:", tops)
    for season in seasons:
        members = [i for i in z.infolist() if i.filename.startswith(season + "/") and not i.is_dir()]
        if not members:
            sys.exit(f"no members found for season {season!r}")
        done = 0
        for info in members:
            target = out / info.filename
            if target.exists() and target.stat().st_size == info.file_size:
                continue
            z.extract(info, out)
            done += 1
        print(f"{season}: {len(members)} files in zip, {done} newly extracted")
EOF
touch "$OUT/.extract_complete"
echo "[$(date -Is)] done"
