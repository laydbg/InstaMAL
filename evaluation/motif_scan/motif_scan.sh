#!/usr/bin/env bash
set -euxo pipefail

usage() {
  echo "Usage: $0 <lang_path> <models_dir> <output_dir>"
  echo
  echo "Arguments:"
  echo "  lang_path    Path to language specification"
  echo "  models_dir   Directory containing models"
  echo "  output_dir   Directory where results will be written"
}

if [[ $# -ne 3 ]]; then
  usage
  exit 1
fi

LANG_PATH="$1"
MODELS_DIR="$2"
OUTPUT_DIR="$3"

if [[ ! -e "$LANG_PATH" ]]; then
  echo "Error: lang_path does not exist: $LANG_PATH" >&2
  exit 1
fi

if [[ ! -d "$MODELS_DIR" ]]; then
  echo "Error: models_dir is not a directory: $MODELS_DIR" >&2
  exit 1
fi


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FANMOD_PATH="${FANMOD_PLUS_PATH:?FANMOD_PLUS_PATH is not set}"

EDGE_LIST_FILE="edges.txt"     # Produced by ModelsToEdgeList.py
MOTIF_SIZE=4
RESULTS_FILE="fanmod_results.csv"

mkdir -p "$OUTPUT_DIR"

python "$SCRIPT_DIR/ModelsToEdgeList.py" \
  --lang "$LANG_PATH" \
  "$MODELS_DIR" \
  "$OUTPUT_DIR"

"$FANMOD_PATH" \
  -i "$OUTPUT_DIR/$EDGE_LIST_FILE" \
  -o "$OUTPUT_DIR/$RESULTS_FILE" \
  -V -E \
  -s "$MOTIF_SIZE"

echo "Done."

