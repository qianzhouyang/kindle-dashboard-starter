#!/bin/sh
# PW3: little-endian, 32-bit input_event (16 bytes), EV_KEY/KEY_POWER.
# Trigger on release; ignore SYN, other keys, repeats and long presses.

DASHBOARD_DIR=${DASHBOARD_DIR:-/mnt/us/dashboard}
RUN_DIR=${DASHBOARD_RUN_DIR:-/tmp/kindle-dashboard}
DEVICE=${DASHBOARD_POWER_DEVICE:-/dev/input/event0}
EVENT_FILE="$RUN_DIR/power-event.$$"
READER_PID= OWNER_PID= PRESSED_MS=
mkdir -p "$RUN_DIR" || exit 1
if [ "${1:-}" = --notify ]; then
    OWNER_PID=$2
    case "$OWNER_PID" in ''|*[!0-9]*) exit 1 ;; esac
fi
notify() {
    [ -n "$OWNER_PID" ] || return 0
    case "$(tr '\000' ' ' < "/proc/$OWNER_PID/cmdline" 2>/dev/null)" in
        *"$DASHBOARD_DIR/refresh.sh --worker "*) kill "-$1" "$OWNER_PID" ;;
        *) return 1 ;;
    esac
}
cleanup() {
    trap - 0 HUP INT TERM
    [ -n "$READER_PID" ] && kill "$READER_PID" 2>/dev/null
    [ -n "$READER_PID" ] && wait "$READER_PID" 2>/dev/null
    rm -f "$EVENT_FILE" "$RUN_DIR/watcher.ready"
}
fail() { printf '%s\n' "ERROR: $*"; notify USR2; exit 1; }
trap cleanup 0
trap 'exit 130' HUP INT TERM
exec 3< "$DEVICE" || fail 'cannot open power-button event device'
printf '%s\n' "$$" > "$RUN_DIR/watcher.ready"
while true; do
    # Keep fd 3 open across records so queued releases are not lost.
    dd bs=16 count=1 <&3 > "$EVENT_FILE" 2>/dev/null &
    READER_PID=$!
    wait "$READER_PID" || fail 'power-button read failed'
    READER_PID=
    [ "$(wc -c < "$EVENT_FILE")" -eq 16 ] || fail 'short power-button record'
    set -- $(od -An -tu4 "$EVENT_FILE")
    [ "$#" -eq 4 ] || fail 'invalid power-button record'
    event_type=$(($3 % 65536))
    key_code=$(($3 / 65536))
    [ "$event_type" -eq 1 ] && [ "$key_code" -eq 116 ] || continue
    event_ms=$(($1 * 1000 + $2 / 1000))
    case "$4" in
        1) PRESSED_MS=$event_ms ;;
        0)
            [ -n "$PRESSED_MS" ] || continue
            held_ms=$((event_ms - PRESSED_MS))
            PRESSED_MS=
            if [ "$held_ms" -ge 0 ] && [ "$held_ms" -le 2000 ]; then
                printf 'POWER_SHORT duration_ms=%s\n' "$held_ms"
                [ -z "$OWNER_PID" ] || : > "$RUN_DIR/exit-request"
                notify USR1 || exit 1
                exit 0
            fi
            printf 'POWER_LONG_IGNORED duration_ms=%s\n' "$held_ms"
            ;;
    esac
done
