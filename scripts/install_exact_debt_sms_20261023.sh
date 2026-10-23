#!/usr/bin/env bash
# Backward-compatible alias: update BOTH debt and waiting-payment SMS on server.
# Do not let the historical installer leave phone-app drafts with old expiry text.
set -Eeuo pipefail
exec bash "$(cd "$(dirname "$0")" && pwd)/install_unified_debt_sms_20261023.sh"
