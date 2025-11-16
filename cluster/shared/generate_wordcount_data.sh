#!/bin/bash
set -euo pipefail

DATA_DIR="/shared/wordcount-data/raw"
FILES=${FILES:-12}
LINES_PER_FILE=${LINES_PER_FILE:-3000000}

mkdir -p "$DATA_DIR"
echo "[wordcount-data] directory: $DATA_DIR"
echo "[wordcount-data] generating $FILES files with $LINES_PER_FILE lines each"

for idx in $(seq -w 1 "$FILES"); do
  target="$DATA_DIR/chunk${idx}.txt"
  echo "[wordcount-data] writing $target"
  awk -v lines="$LINES_PER_FILE" -v idx="$idx" 'BEGIN { for (i = 0; i < lines; ++i) printf "hadoop tolerancia falhas desempenho wordcount texto idx%s dado experimento resiliencia throughput latencia linha%d\n", idx, i }' > "$target"
  sync
  ls -lh "$target"
done

du -sh "$DATA_DIR"
