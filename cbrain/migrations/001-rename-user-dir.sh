#!/usr/bin/env bash
# Forwarding stub — pre-rename. An updater from before v2.1.0 looks for migrations
# in cbrain/migrations/ only. The real script lives in greymatter/migrations/.
exec bash "$(cd "$(dirname "$0")/../../greymatter/migrations" && pwd)/001-rename-user-dir.sh"
