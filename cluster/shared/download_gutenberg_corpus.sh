#!/bin/bash
set -euo pipefail

# Directory that will store the downloaded .txt files.
DATA_DIR=${DATA_DIR:-/shared/wordcount-data/gutenberg}
# Space-separated list of Gutenberg IDs to fetch. Override BOOK_IDS to customize.
BOOK_IDS=${BOOK_IDS:-"11 84 98 1342 1400 158 345 4300 1661 2554 2701 5200"}
# When set to 1 the script re-downloads files even if they already exist.
OVERWRITE=${OVERWRITE:-0}

CACHE_BASE="https://www.gutenberg.org/cache/epub"
FILES_BASE="https://www.gutenberg.org/files"

mkdir -p "$DATA_DIR"
echo "[gutenberg] Target directory: $DATA_DIR"
echo "[gutenberg] Book IDs: $BOOK_IDS"

download_tool() {
  if command -v wget >/dev/null 2>&1; then
    wget -q -O "$2" "$1"
  elif command -v curl >/dev/null 2>&1; then
    curl -fsSL "$1" -o "$2"
  else
    echo "[gutenberg] ERROR: neither wget nor curl is available" >&2
    exit 1
  fi
}

need_binary() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[gutenberg] ERROR: '$1' is required but not installed" >&2
    exit 1
  fi
}

download_book() {
  local id="$1"
  local dest="$DATA_DIR/gutenberg-${id}.txt"
  local temp

  if [[ -f "$dest" && "$OVERWRITE" != "1" ]]; then
    echo "[gutenberg][${id}] already exists, skipping (set OVERWRITE=1 to re-download)."
    return 0
  fi

  echo "[gutenberg][${id}] downloading..."
  temp=$(mktemp)

  # Candidate URLs ordered by likelihood of success.
  local candidates=(
    "$CACHE_BASE/${id}/pg${id}.txt"
    "$CACHE_BASE/${id}/pg${id}.txt.utf8"
    "$FILES_BASE/${id}/${id}-0.txt"
    "$FILES_BASE/${id}/${id}.txt"
    "$FILES_BASE/${id}/${id}-8.txt"
    "$FILES_BASE/${id}/${id}-0.txt.utf8"
    "$FILES_BASE/${id}/${id}.txt.utf8"
    "$FILES_BASE/${id}/${id}.zip"
    "$FILES_BASE/${id}/${id}-0.zip"
  )

  for url in "${candidates[@]}"; do
    if download_tool "$url" "$temp"; then
      if [[ "$url" == *.zip ]]; then
  need_binary unzip
  echo "[gutenberg][${id}] extracting from zip"
        if unzip -p "$temp" > "$dest" 2>/dev/null; then
          rm -f "$temp"
          echo "[gutenberg][${id}] saved to $dest"
          return 0
        else
          echo "[gutenberg][${id}] unzip failed for $url" >&2
          rm -f "$temp"
          continue
        fi
      else
        mv "$temp" "$dest"
        echo "[gutenberg][${id}] saved to $dest"
        return 0
      fi
    fi
  done

  rm -f "$temp"
  echo "[gutenberg][${id}] ERROR: could not download from Gutenberg mirrors" >&2
  return 1
}

failed=0
for book_id in $BOOK_IDS; do
  if ! download_book "$book_id"; then
    failed=$((failed + 1))
  fi
  sync || true
  if [[ -f "$DATA_DIR/gutenberg-${book_id}.txt" ]]; then
    ls -lh "$DATA_DIR/gutenberg-${book_id}.txt"
  fi
  echo ""
done

du -sh "$DATA_DIR" || true

if [[ "$failed" -gt 0 ]]; then
  echo "[gutenberg] Completed with $failed failures" >&2
  exit 1
fi

echo "[gutenberg] Download complete."
