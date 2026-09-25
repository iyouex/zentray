#!/usr/bin/env bash
set -euo pipefail
STATE_FILE="${TMPDIR:-/tmp}/zentray-sample-service.state"
action="${1:-status}"
case "$action" in
  start)
    echo running >"$STATE_FILE"
    echo "started"
    exit 0
    ;;
  stop)
    echo stopped >"$STATE_FILE"
    echo "stopped"
    exit 0
    ;;
  status)
    if [[ -f "$STATE_FILE" ]]; then
      cat "$STATE_FILE"
    else
      echo stopped
    fi
    exit 0
    ;;
  *)
    echo "unknown action" >&2
    exit 2
    ;;
esac
