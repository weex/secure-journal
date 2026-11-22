#!/usr/bin/env bash
# Idempotency check for the SPI panel config.txt block. No root, no hardware.

set -euo pipefail
unset CDPATH

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
script=$root/scripts/spi-display.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

config=$work/config.txt
cat > "$config" <<'EOF'
# stock lines that must survive
dtparam=audio=on
dtoverlay=vc4-kms-v3d
auto_initramfs=1
[pi4]
dtoverlay=vc4-kms-v3d,cma-512
EOF

SECURE_JOURNAL_CONFIG=$config "$script"
SECURE_JOURNAL_CONFIG=$config "$script"
SPI_DTPARAM='piscreen,drm,rotate=180,invx,swapxy' SECURE_JOURNAL_CONFIG=$config "$script"

begin_count=$(grep -c '# BEGIN secure-journal spi-display' "$config")
end_count=$(grep -c '# END secure-journal spi-display' "$config")
if [ "$begin_count" -ne 1 ] || [ "$end_count" -ne 1 ]; then
  printf 'expected one marked block, found begin=%s end=%s\n' "$begin_count" "$end_count" >&2
  exit 1
fi

for keep in 'dtparam=audio=on' 'dtoverlay=vc4-kms-v3d' 'auto_initramfs=1' 'dtoverlay=vc4-kms-v3d,cma-512'; do
  if ! grep -F -q "$keep" "$config"; then
    printf 'lost original line: %s\n' "$keep" >&2
    exit 1
  fi
done

if ! grep -F -q 'dtoverlay=piscreen,drm,rotate=180,invx,swapxy' "$config"; then
  printf 'override overlay was not written\n' >&2
  cat "$config" >&2
  exit 1
fi
if grep -F -q 'rotate=90' "$config"; then
  printf 'previous overlay parameters were left behind\n' >&2
  exit 1
fi

# The block has to apply to every model, so it must open its own [all] section
# after the [pi4] filter above it.
if ! awk '
  $0 == "[pi4]" { saw_pi4 = 1 }
  $0 == "# BEGIN secure-journal spi-display" && saw_pi4 { in_block = 1 }
  in_block && $0 == "[all]" { found = 1 }
  $0 == "# END secure-journal spi-display" { in_block = 0 }
  END { exit !found }
' "$config"; then
  printf 'SPI block does not re-open [all] after the [pi4] section\n' >&2
  exit 1
fi

printf 'spi-display: ok\n'
