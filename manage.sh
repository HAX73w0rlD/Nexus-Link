#!/bin/bash

# Dynamisches Ermitteln des Projektverzeichnisses
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
BOT_SCRIPT="bot.py"
PID_FILE="$PROJECT_DIR/.bot.pid"

cd "$PROJECT_DIR" || { echo "Projektverzeichnis nicht gefunden: $PROJECT_DIR"; exit 1; }

# Killt alle Bot-Instanzen (nicht nur die im PID-File)
kill_all_bots() {
    # Pgrep findet alle python3 bot.py Prozesse (auch sich selbst nicht)
    pids=$(pgrep -f "venv/bin/python3 bot\.py" 2>/dev/null | grep -v "^$$\$")
    if [ -n "$pids" ]; then
        echo "$pids" | while read -r pid; do
            kill "$pid" 2>/dev/null
        done
        # Kurz warten, dann prüfen und ggf. SIGKILL
        sleep 2
        pids=$(pgrep -f "venv/bin/python3 bot\.py" 2>/dev/null | grep -v "^$$\$")
        if [ -n "$pids" ]; then
            echo "$pids" | while read -r pid; do
                kill -9 "$pid" 2>/dev/null
            done
            sleep 1
        fi
    fi
    # PID-File aufräumen
    rm -f "$PID_FILE"
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

start_bot() {
    if is_running; then
        echo "Bot läuft bereits (PID: $(cat "$PID_FILE"))."
        exit 0
    fi

    if [ ! -d "$VENV_DIR" ]; then
        echo "Virtuelle Umgebung nicht gefunden in $VENV_DIR."
        exit 1
    fi

    # Vor dem Start sicherstellen, dass keine alten Instanzen laufen
    kill_all_bots

    echo "Starte Telegram-Bot..."
    source "$VENV_DIR/bin/activate"
    # Starte mit setsid damit der Prozess vom Terminal getrennt wird
    # und $! die echte Python-PID liefert
    setsid "$VENV_DIR/bin/python3" "$BOT_SCRIPT" > bot.log 2>&1 &
    BOT_PID=$!
    # PID nach 1s nochmal lesen falls noch Subprozess-Wechsel
    sleep 2
    # Suche nur nach python3-Prozessen (nicht nach bash/sh)
    ACTUAL_PID=$(ps -ef | grep "python3 bot.py" | grep -v grep | awk '{print $2}' | head -1)
    if [ -n "$ACTUAL_PID" ]; then
        echo "$ACTUAL_PID" > "$PID_FILE"
        echo "Bot wurde im Hintergrund gestartet (PID: $ACTUAL_PID)."
    else
        echo "FEHLER: Bot konnte nicht gestartet werden."
        exit 1
    fi
}

stop_bot() {
    # Erst alle Instanzen killen
    local was_running=false
    if is_running; then
        was_running=true
    fi
    kill_all_bots
    if [ "$was_running" = false ]; then
        echo "Es läuft aktuell kein Bot."
    fi
    rm -f "$PID_FILE"
    echo "Bot wurde gestoppt."
}

status_bot() {
    # Prüfe ob überhaupt ein Bot-Prozess läuft
    local pids=$(ps -ef | grep "python3 bot.py" | grep -v grep | awk '{print $2}')
    if [ -n "$pids" ]; then
        local count=$(echo "$pids" | wc -l)
        if [ "$count" -gt 1 ]; then
            echo "Bot läuft aktiv (PID: $(echo $pids | head -1), $count Instanzen!)"
        else
            echo "Bot läuft aktiv (PID: $(echo $pids))."
        fi
    else
        echo "Bot ist gestoppt."
    fi
}

case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        stop_bot
        sleep 1
        start_bot
        ;;
    status)
        status_bot
        ;;
    *)
        echo "Verwendung: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
