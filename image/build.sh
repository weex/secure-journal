#!/bin/bash
# Build a flashable secure-journal.img.xz with rpi-image-gen v2.9.0.
#
#   sudo ./image/build.sh /path/to/rpi-image-gen
#
# The tool's own install_deps.sh has to have been run on the host first.
# A native Debian arm64 host is what upstream supports. The GitHub workflow
# uses a privileged Debian Trixie container on an arm64 runner.

set -euo pipefail

repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
ig=${1:-}
if [[ -z ${ig} || ! -x ${ig}/rpi-image-gen ]]; then
  echo "usage: image/build.sh /path/to/rpi-image-gen" >&2
  exit 1
fi

stage=${repo}/image/layer/journal.d/payload
rm -rf "${stage}"
mkdir -p "${stage}"
rsync -a \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "${repo}/web/journal_app" "${stage}/"

cd "${repo}"
"${ig}/rpi-image-gen" build -S "${repo}/image" -c "${repo}/image/config/journal.yaml"

img=$(find "${repo}/work" -name '*.img' -type f -printf '%s\t%p\n' | sort -n | tail -1 | cut -f2-)
if [[ -z ${img} ]]; then
  echo "rpi-image-gen finished without a .img under ${repo}/work" >&2
  exit 1
fi
mkdir -p "${repo}/dist"
xz -T0 -6 -c "${img}" > "${repo}/dist/secure-journal.img.xz"
echo "wrote ${repo}/dist/secure-journal.img.xz"
