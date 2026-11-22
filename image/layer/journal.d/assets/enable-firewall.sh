#!/bin/bash
# Idempotent. Allows the journal and mDNS. Does not allow SSH.
set -euo pipefail

ufw default deny incoming
ufw default allow outgoing
ufw allow 443/tcp comment 'secure-journal'
ufw allow 5353/udp comment 'avahi'
ufw --force enable
