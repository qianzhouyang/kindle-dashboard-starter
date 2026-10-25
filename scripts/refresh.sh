#!/bin/sh
# One detached session owns the screen and its power-button listener.
# --start: KUAL cached display; --once: USB display with completion wait.
# URL [interval]: optional HTTP refresh using the same session lifecycle.

DASHBOARD_DIR=${DASHBOARD_DIR:-/mnt/us/dashboard}
RUN_DIR=${DASHBOARD_RUN_DIR:-/tmp/kindle-dashboard}
SCRIPT="$DASHBOARD_DIR/refresh.sh"
IMAGE_PATH="$DASHBOARD_DIR/dashboard.png"
LOG_PATH="$DASHBOARD_DIR/refresh.log"
PID_FILE="$RUN_DIR/session.pid"
STATE_FILE="$RUN_DIR/state"
INITCTL=${DASHBOARD_INITCTL:-/sbin/initctl}
EIPS=${DASHBOARD_EIPS:-/usr/sbin/eips}
FB_DEVICE=${DASHBOARD_FB_DEVICE:-/dev/fb0}
PROC_DIR=${DASHBOARD_PROC_DIR:-/proc}
GUI_KILL=${DASHBOARD_GUI_KILL:-kill}
GUI_NAMES=${DASHBOARD_GUI_NAMES:-"awesome cvm pillowd KPPMainApp blanket kb JunoStatusBarDriver kfxview kfxreader webreader mesquite"}
GUI_PAUSED="$RUN_DIR/gui-paused"
GUI_FRAME="$RUN_DIR/native-framebuffer.bin"
DEFAULT_URL=
export DASHBOARD_DIR DASHBOARD_RUN_DIR="$RUN_DIR"
mkdir -p "$DASHBOARD_DIR" "$RUN_DIR" || exit 1

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_PATH"; }
state() { printf '%s\n' "$1" > "$STATE_FILE.next.$$" && mv "$STATE_FILE.next.$$" "$STATE_FILE"; }
read_state() { cat "$STATE_FILE" 2>/dev/null; }

session_alive() {
    SESSION_PID=$(cat "$PID_FILE" 2>/dev/null)
    case "$SESSION_PID" in ''|*[!0-9]*) return 1 ;; esac
    kill -0 "$SESSION_PID" 2>/dev/null || return 1
    case "$(tr '\000' ' ' < "/proc/$SESSION_PID/cmdline" 2>/dev/null)" in
        *"$SCRIPT --worker "*) return 0 ;;
        *) return 1 ;;
    esac
}

gui_start_time() { awk '{print $22}' "$PROC_DIR/$1/stat" 2>/dev/null; }
gui_state() { awk '{print $3}' "$PROC_DIR/$1/stat" 2>/dev/null; }

wake_if_needed() {
    [ "$(lipc-get-prop com.lab126.powerd state 2>/dev/null)" = active ] && return 0
    # wakeUp is an integer property and rejects requests while already active.
    lipc-set-prop -i com.lab126.powerd wakeUp 1 >> "$LOG_PATH" 2>&1 || true
}

pause_gui() {
    [ ! -s "$GUI_PAUSED" ] || restore_gui || return 1
    # Require a healthy existing UI; this mode never cold-restarts Java/KPP.
    [ "$(lipc-get-prop -i com.lab126.kaf frameworkStarted 2>/dev/null)" = 1 ] || return 1
    for name in awesome cvm; do
        pid=$(pidof -s "$name")
        [ -n "$pid" ] && [ "$(gui_state "$pid")" != T ] || return 1
    done
    : > "$GUI_PAUSED"
    for name in $GUI_NAMES; do
        for pid in $(pidof "$name"); do
            [ "$(gui_state "$pid")" != T ] || continue
            born=$(gui_start_time "$pid")
            [ -n "$born" ] || continue
            printf '%s %s\n' "$pid" "$born" >> "$GUI_PAUSED"
            "$GUI_KILL" -STOP "$pid" || return 1
        done
    done
    cat "$FB_DEVICE" > "$GUI_FRAME" || return 1
    [ -s "$GUI_FRAME" ] || return 1
    log 'Native GUI paused; original framebuffer saved.'
}

restore_gui() {
    log 'Restoring native Kindle GUI...'
    wake_if_needed
    restored=0
    if [ -s "$GUI_FRAME" ]; then
        cat "$GUI_FRAME" > "$FB_DEVICE" || restored=1
        # -f alone is only an option: it exits 0 without refreshing the panel.
        # PW3 has a 1072x1448 visible area (1088 is the framebuffer stride).
        "$EIPS" -s w=1072,h=1448 -f >> "$LOG_PATH" 2>&1 || restored=1
    fi
    if [ -f "$GUI_PAUSED" ]; then
        while read -r pid born; do
            # Compare process start time to protect against PID reuse.
            if [ "$(gui_start_time "$pid")" = "$born" ]; then
                "$GUI_KILL" -CONT "$pid" || restored=1
            else
                log "ERROR: saved GUI process $pid no longer exists."
                restored=1
            fi
        done < "$GUI_PAUSED"
    fi
    wake_if_needed
    lipc-set-prop com.lab126.powerd preventScreenSaver 0 >> "$LOG_PATH" 2>&1 || restored=1
    if [ "$restored" -eq 0 ]; then
        rm -f "$GUI_PAUSED" "$GUI_FRAME"
        log 'Native GUI restored from saved frame; original processes resumed.'
    else
        log 'ERROR: native GUI restore did not complete.'
    fi
    return "$restored"
}

render_image() {
    render_path=${1:-$IMAGE_PATH}
    [ -s "$render_path" ] || { log 'ERROR: no cached dashboard.png; push an image first.'; return 1; }
    log "Rendering $render_path to E-Ink display..."
    "$EIPS" -f -g "$render_path" >> "$LOG_PATH" 2>&1
}

finish_session() {
    result=$?
    trap - 0
    trap '' HUP INT TERM USR1 USR2
    state RESTORING
    # Cancel only children created by this session, never unrelated dd/shells.
    for child in "$WATCH_PID" "$JOB_PID"; do
        [ -n "$child" ] && kill "$child" 2>/dev/null
    done
    [ -n "$WATCH_PID" ] && wait "$WATCH_PID" 2>/dev/null
    [ -n "$JOB_PID" ] && wait "$JOB_PID" 2>/dev/null
    [ "$NETWORK_READY" != 1 ] || network_cleanup || result=1
    restore_gui || result=1
    if [ "$result" -eq 0 ]; then state READING; else state ERROR; fi
    rm -f "$RUN_DIR/watcher.ready" "$RUN_DIR/exit-request" "$RUN_DIR/session-mode" "$PID_FILE"
    rmdir "$RUN_DIR/session.lock" 2>/dev/null
    exit "$result"
}

worker() {
    mkdir "$RUN_DIR/session.lock" 2>/dev/null || exit 1
    printf '%s\n' "$$" > "$PID_FILE"
    WATCH_PID= JOB_PID= NETWORK_READY=
    trap finish_session 0
    trap 'exit 0' HUP INT TERM
    trap 'log "Short power press: restoring reading."; exit 0' USR1
    trap 'log "ERROR: power-button listener failed; restoring reading."; exit 1' USR2
    state STARTING
    log "Starting detached dashboard session ($1), pid=$$."
    printf '%s\n' "$1" > "$RUN_DIR/session-mode"
    [ -s "$IMAGE_PATH" ] || { log 'ERROR: no cached image.'; exit 1; }
    if [ "$1" = http ]; then
        . "$DASHBOARD_DIR/power-cycle.sh" || exit 1
        NETWORK_READY=1
        network_init || exit 1
    fi
    lipc-set-prop com.lab126.powerd preventScreenSaver 1 >> "$LOG_PATH" 2>&1 || exit 1
    wake_if_needed
    rm -f "$RUN_DIR/watcher.ready"
    "$DASHBOARD_DIR/watch_power.sh" --notify "$$" >> "$LOG_PATH" 2>&1 &
    WATCH_PID=$!
    tries=0
    while [ ! -f "$RUN_DIR/watcher.ready" ]; do
        kill -0 "$WATCH_PID" 2>/dev/null || exit 1
        tries=$((tries + 1))
        [ "$tries" -le 5 ] || { log 'ERROR: listener not ready.'; exit 1; }
        sleep 1
    done
    # Let KUAL finish its exitmenu action before freezing the existing UI.
    sleep 1
    log 'Pausing native GUI processes...'
    pause_gui || exit 1
    render_image || exit 1
    state DASHBOARD
    log "MODE=DASHBOARD ($1); short power press returns to reading."

    if [ "$1" = offline ]; then
        wait "$WATCH_PID"
        log 'ERROR: listener exited unexpectedly.'
        exit 1
    fi

    url=$2 interval=$3
    while true; do
        network_cycle || exit 1
        power_wait || exit 1
    done
}

launch_session() {
    if session_alive; then return 0; fi
    # /tmp resets on reboot. Only stale metadata in this private directory.
    if [ -f "$RUN_DIR/network-state" ] || [ -f "$RUN_DIR/rtc-owned" ]; then
        . "$DASHBOARD_DIR/power-cycle.sh" && network_cleanup || return 1
    fi
    rm -f "$PID_FILE" "$RUN_DIR/watcher.ready" "$RUN_DIR/exit-request"
    rmdir "$RUN_DIR/session.lock" 2>/dev/null
    state STARTING
    nohup setsid "$SCRIPT" --worker "$@" </dev/null >> "$DASHBOARD_DIR/launcher.log" 2>&1 &
}

wait_for_dashboard() {
    tries=0
    while [ "$tries" -lt 90 ]; do
        case "$(read_state)" in
            DASHBOARD) session_alive && return 0 ;;
            ERROR|READING) log 'ERROR: dashboard start was interrupted or failed.'; return 1 ;;
        esac
        tries=$((tries + 1))
        sleep 1
    done
    log 'ERROR: timed out waiting for the dashboard.'
    return 1
}

case "${1:-}" in
    --worker) shift; worker "$@" ;;
    --start)
        [ -s "$IMAGE_PATH" ] || { log 'ERROR: no cached image; leaving reading mode unchanged.'; exit 1; }
        launch_session offline
        ;;
    --start-auto)
        config=${DASHBOARD_NETWORK_CONFIG:-$DASHBOARD_DIR/network.conf}
        url= interval=300
        if [ -f "$config" ]; then
            while IFS='=' read -r key value; do
                case "$key" in URL) url=$value ;; INTERVAL) interval=$value ;; esac
            done < "$config"
        fi
        url=${2:-$url} interval=${3:-$interval}
        case "$url" in http://*|https://*) ;; *) log 'ERROR: configure a dashboard URL first.'; exit 1 ;; esac
        case "$interval" in ''|*[!0-9]*) exit 1 ;; esac
        [ "$interval" -ge 20 ] && [ "$interval" -le 86400 ] || exit 1
        [ -s "$IMAGE_PATH" ] || exit 1
        if session_alive && [ "$(cat "$RUN_DIR/session-mode")" != http ]; then
            log 'ERROR: restore reading before changing dashboard modes.'; exit 1
        fi
        launch_session http "$url" "$interval"
        ;;
    --once)
        [ -s "$IMAGE_PATH" ] || { log 'ERROR: no cached image; leaving reading mode unchanged.'; exit 1; }
        if session_alive && [ "$(read_state)" = DASHBOARD ]; then
            render_image
        else
            launch_session offline && wait_for_dashboard
        fi
        ;;
    --restore)
        if session_alive; then
            kill -TERM "$SESSION_PID" || exit 1
            tries=0
            while [ "$(read_state)" != READING ] && kill -0 "$SESSION_PID" 2>/dev/null && [ "$tries" -lt 100 ]; do
                sleep 1
                tries=$((tries + 1))
            done
            [ "$(read_state)" = READING ]
        else
            if [ -f "$RUN_DIR/network-state" ] || [ -f "$RUN_DIR/rtc-owned" ]; then
                . "$DASHBOARD_DIR/power-cycle.sh" && network_cleanup || exit 1
            fi
            restore_gui && state READING
        fi
        ;;
    --status)
        printf 'mode=%s\n' "$(read_state)"
        session_alive && printf 'session_pid=%s\n' "$SESSION_PID"
        [ ! -f "$RUN_DIR/session-mode" ] || printf 'session_mode=%s\n' "$(cat "$RUN_DIR/session-mode")"
        [ ! -s "$GUI_PAUSED" ] || printf 'paused_gui_pids=%s\n' "$(cut -d ' ' -f 1 "$GUI_PAUSED" | tr '\n' ' ')"
        "$INITCTL" status lab126_gui
        "$INITCTL" status x
        ;;
    *)
        interval=${2:-300}
        case "$interval" in ''|*[!0-9]*|0) log 'ERROR: interval must be a positive integer.'; exit 1 ;; esac
        [ -n "${1:-$DEFAULT_URL}" ] || { log 'Use --start (cached) or --start-auto (network).'; exit 1; }
        launch_session http "${1:-$DEFAULT_URL}" "$interval" && wait_for_dashboard
        ;;
esac
