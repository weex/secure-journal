#!/usr/bin/env bash
# Logic tests for the touchscreen setup. They do not import GTK.

set -euo pipefail
unset CDPATH

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
python3 -m compileall -q ui
python3 -m unittest discover -s tests -p 'test_*.py'
