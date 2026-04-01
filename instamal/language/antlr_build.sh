#!/usr/bin/env bash
set -euxo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OUT_DIR="$SCRIPT_DIR"
GRAMMAR="$SCRIPT_DIR/Spec.g4"
LANG="Python3"

command -v antlr4 >/dev/null || {
  echo "Error: antlr4 not found in PATH" >&2
  exit 1
}

antlr4 \
  -Dlanguage="$LANG" \
  -visitor \
  -no-listener \
  "$GRAMMAR" \
  -o "$OUT_DIR"

rm -f "$OUT_DIR"/Spec*.interp "$OUT_DIR"/Spec*.tokens

echo "Done."
