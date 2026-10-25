#!/bin/sh
# Sourced by the owning refresh.sh worker. No daemon or automatic startup.
RTC_ALARM=${DASHBOARD_RTC_ALARM:-/sys/class/rtc/rtc0/wakealarm}
POWER_STATE=${DASHBOARD_POWER_STATE:-/sys/power/state}
NET_SYS=${DASHBOARD_NET_SYS:-/sys/class/net}
WIFI_INTERFACE=${DASHBOARD_WIFI_INTERFACE:-wlan0}
NET_SAVED="$RUN_DIR/network-state"
RTC_OWNED="$RUN_DIR/rtc-owned"
DOWNLOAD="$DASHBOARD_DIR/download.$$.png"

ota_blocked() {
    [ ! -e /usr/bin/otaupd ] && [ ! -e /usr/bin/otav3 ] &&
    [ ! -e /etc/upstart/otaupd.conf ] && [ ! -e /etc/upstart/otav3.conf ] &&
    [ -s "$DASHBOARD_DIR/ota-block.sha256" ] &&
    sha256sum -c "$DASHBOARD_DIR/ota-block.sha256" >> "$LOG_PATH" 2>&1 &&
    [ -z "$(pidof otaupd otav3)" ]
}

wifi_get() { timeout 5 lipc-get-prop "$1" "$2"; }
wifi_set() { timeout 5 lipc-set-prop -i "$1" "$2" "$3" >> "$LOG_PATH" 2>&1; }

network_init() {
    ota_blocked || { log 'ERROR: OTA block verification failed; refusing network mode.'; return 1; }
    original_radio=$(wifi_get com.lab126.cmd wirelessEnable) || return 1
    original_wifi=$(wifi_get com.lab126.wifid enable) || return 1
    case "$original_radio:$original_wifi" in 0:0|0:1|1:0|1:1) ;; *) return 1 ;; esac
    printf '%s\n%s\n' "$original_radio" "$original_wifi" > "$NET_SAVED" || return 1
    log "Network session initialized; original radio=$original_radio wifi=$original_wifi."
}

wifi_enable() {
    log 'WIFI_ENABLE'
    wifi_set com.lab126.cmd wirelessEnable 1 && wifi_set com.lab126.wifid enable 1 || return 1
    deadline=$(($(date +%s) + ${DASHBOARD_WIFI_WAIT:-25}))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        [ ! -e "$RUN_DIR/exit-request" ] || return 1
        if [ "$(wifi_get com.lab126.wifid cmState)" = CONNECTED ]; then
            log 'WIFI_CONNECTED'
            return 0
        fi
        sleep 1 & JOB_PID=$!; wait "$JOB_PID"; JOB_PID=
    done
    log 'WIFI_TIMEOUT: keeping cached image.'
    return 1
}

wifi_disable() {
    wifi_set com.lab126.cmd wirelessEnable 0 && wifi_set com.lab126.wifid enable 0 || return 1
    tries=0
    while [ "$tries" -lt 5 ]; do
        if [ "$(wifi_get com.lab126.cmd wirelessEnable)" = 0 ] &&
           [ "$(wifi_get com.lab126.wifid enable)" = 0 ]; then
            log 'WIFI_DISABLED'
            return 0
        fi
        tries=$((tries + 1))
        sleep 1
    done
    log 'ERROR: Wi-Fi did not turn off; refusing suspend.'
    return 1
}

valid_png() {
    [ -s "$1" ] && [ "$(wc -c < "$1")" -le 2097152 ] || return 1
    header=$(od -An -tx1 -N29 "$1" | tr -d ' \n')
    # PNG + IHDR, exactly 1072x1448, non-interlaced 8-bit grayscale or RGB.
    case "$header" in
        89504e470d0a1a0a0000000d4948445200000430000005a80800000000|\
        89504e470d0a1a0a0000000d4948445200000430000005a80802000000) ;;
        *) return 1 ;;
    esac
    [ "$(tail -c 12 "$1" | od -An -tx1 | tr -d ' \n')" = 0000000049454e44ae426082 ]
}

network_cycle() {
    downloaded=0
    if wifi_enable; then
        log 'FETCH_BEGIN'
        curl --silent --show-error --fail --interface "$WIFI_INTERFACE" \
            --connect-timeout 5 --max-time 20 --max-filesize 2097152 \
            --proto '=http,https' -o "$DOWNLOAD" "$url" >> "$LOG_PATH" 2>&1 &
        JOB_PID=$!
        if wait "$JOB_PID" && valid_png "$DOWNLOAD"; then
            downloaded=1
            log "FETCH_OK sha256=$(sha256sum "$DOWNLOAD" | cut -d ' ' -f 1)"
        else
            log 'FETCH_FAILED_OR_INVALID: keeping cached image.'
        fi
        JOB_PID=
    fi
    # Also runs on connection/download failure. Never sleep with cycle-owned Wi-Fi on.
    wifi_disable || return 1
    if [ "$downloaded" -eq 1 ]; then
        # Decode/render before committing the new cache: malformed PNGs cannot replace it.
        if render_image "$DOWNLOAD"; then
            mv "$DOWNLOAD" "$IMAGE_PATH" || return 1
            log 'CYCLE_RENDERED'
        else
            log 'PNG_DECODE_FAILED: restoring cached image.'
            render_image || return 1
        fi
    fi
    rm -f "$DOWNLOAD"
}

rtc_clear_owned() {
    [ -f "$RTC_OWNED" ] || return 0
    target=$(cat "$RTC_OWNED")
    current=$(cat "$RTC_ALARM") || return 1
    if [ -n "$target" ] && [ "$current" = "$target" ]; then
        echo 0 > "$RTC_ALARM" || return 1
        log "RTC_CANCEL target=$target"
    else
        log 'RTC_RELEASE: expired or changed by another owner; leaving current alarm untouched.'
    fi
    rm -f "$RTC_OWNED"
}

rtc_arm() {
    current=$(cat "$RTC_ALARM") || return 1
    owned=$(cat "$RTC_OWNED" 2>/dev/null)
    case "$current" in
        ''|0) ;;
        *) [ "$current" = "$owned" ] || { log 'ERROR: another owner has an RTC alarm; refusing to overwrite it.'; return 1; } ;;
    esac
    target=$(($(date +%s) + interval))
    printf '%s\n' "$target" > "$RTC_OWNED" || return 1
    echo 0 > "$RTC_ALARM" && echo "$target" > "$RTC_ALARM" || return 1
    [ "$(cat "$RTC_ALARM")" = "$target" ] || return 1
    log "RTC_ARM target=$target interval=$interval"
}

power_wait() {
    charging=$(timeout 5 lipc-get-prop com.lab126.powerd isCharging) || return 1
    carrier=$(cat "$NET_SYS/usb0/carrier" 2>/dev/null)
    if [ "$charging" = 1 ] || [ "$carrier" = 1 ]; then
        rtc_clear_owned || return 1
        log "USB_WAIT interval=$interval"
        sleep "$interval" & JOB_PID=$!; wait "$JOB_PID"; JOB_PID=
    else
        rtc_arm || return 1
        early_wakes=0
        while true; do
            [ ! -e "$RUN_DIR/exit-request" ] || return 1
            sync
            log "SUSPEND_ENTER wall=$(date +%s) uptime=$(cut -d ' ' -f 1 /proc/uptime)"
            [ ! -e "$RUN_DIR/exit-request" ] || return 1
            echo mem > "$POWER_STATE" || return 1
            log "SUSPEND_RESUME wall=$(date +%s) uptime=$(cut -d ' ' -f 1 /proc/uptime)"
            # Let a button release notify the owner before any network activity.
            sleep 1 & JOB_PID=$!; wait "$JOB_PID"; JOB_PID=
            [ ! -e "$RUN_DIR/exit-request" ] || return 1
            if [ "$(date +%s)" -ge "$target" ]; then
                log "RTC_WAKE target=$target"
                return 0
            fi
            charging=$(timeout 5 lipc-get-prop com.lab126.powerd isCharging) || return 1
            carrier=$(cat "$NET_SYS/usb0/carrier" 2>/dev/null)
            if [ "$charging" = 1 ] || [ "$carrier" = 1 ]; then
                rtc_clear_owned || return 1
                log 'USB_WAKE: returning to powered refresh mode.'
                return 0
            fi
            # A stray wake must not create an unlimited download/suspend loop.
            early_wakes=$((early_wakes + 1))
            [ "$early_wakes" -le 3 ] || { log 'ERROR: repeated early wakes; restoring reading.'; return 1; }
            log "EARLY_WAKE count=$early_wakes; waiting for the original RTC target."
        done
    fi
}

network_cleanup() {
    cleaned=0
    rtc_clear_owned || cleaned=1
    rm -f "$DOWNLOAD"
    if [ -f "$NET_SAVED" ]; then
        original_radio=$(sed -n '1p' "$NET_SAVED")
        original_wifi=$(sed -n '2p' "$NET_SAVED")
        case "$original_radio:$original_wifi" in
            0:0|0:1|1:0|1:1)
                wifi_set com.lab126.cmd wirelessEnable "$original_radio" || cleaned=1
                wifi_set com.lab126.wifid enable "$original_wifi" || cleaned=1
                [ "$(wifi_get com.lab126.cmd wirelessEnable)" = "$original_radio" ] || cleaned=1
                [ "$(wifi_get com.lab126.wifid enable)" = "$original_wifi" ] || cleaned=1
                ;;
            *) cleaned=1 ;;
        esac
        if [ "$cleaned" -eq 0 ]; then
            rm -f "$NET_SAVED"
            log "WIFI_RESTORED radio=$original_radio wifi=$original_wifi"
        fi
    fi
    return "$cleaned"
}
