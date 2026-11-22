#!/bin/sh
# Chromium starts after the localhost setup page answers.
set -eu

i=0
while [ "$i" -lt 60 ]; do
  if curl -sf -o /dev/null http://127.0.0.1:8080/health; then
    exit 0
  fi
  i=$((i + 1))
  sleep 0.5
done
echo "setup server did not answer on 127.0.0.1:8080" >&2
exit 1
