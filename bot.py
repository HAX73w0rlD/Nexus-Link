import os
import re
import asyncio
import json
import uuid
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from memory import init_memory, save_user_state, load_user_state, save_session, load_session, delete_session, add_history_entry, load_history, clear_history, save_job_log, load_job_log, list_job_logs, build_context_from_history
from i18n import t as _, get_lang, LANG_NAMES
from providers import load_config, get_model_list
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Rauschfilter: nur die internal-Code-Sachen filtern
NOISE_PATTERNS = [
    "unrecognized_model",
    "query_source",
    "generate_session_title",
]

# Config
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "0"))  # 0 = unlimited
STREAM_UPDATE_INTERVAL = 0.5  # Telegram edit throttle
LOG_POLL_INTERVAL = 3  # Wie oft `claude logs` aufgerufen wird
WORKING_DIR = os.path.dirname(os.path.abspath(__file__))

# Memory initialisieren beim Start
init_memory()

# Provider-Konfiguration laden
PROVIDER_NAME, PROVIDERS, CURRENT_PROVIDER = load_config()
MODELS = CURRENT_PROVIDER.get_model_list()
logger.info(f"Provider: {PROVIDER_NAME}, Modell: {CURRENT_PROVIDER.model}")

# --- Permission-Modi ---
PERMISSION_MODES = ["default", "acceptEdits", "auto", "bypassPermissions", "plan", "dontAsk"]
PERMISSION_MODE_LABELS = {
    "default": "Default (fragt bei Bedarf)",
    "acceptEdits": "Accept Edits (Edits automatisch)",
    "auto": "Auto (alles automatisch)",
    "bypassPermissions": "Bypass (alle Permissions)",
    "plan": "Plan (nur planen, nicht ausführen)",
    "dontAsk": "Don't Ask (Permission-Prompts ablehnen)",
}

# --- Globaler State ---
class Job:
    """Repräsentiert einen laufenden Claude-Job."""
    def __init__(self, user_id: int, prompt: str, flags: list, message_id: int):
        self.id = str(uuid.uuid4())[:8]  # Interne ID (nicht von claude)
        self.user_id = user_id
        self.prompt = prompt
        self.flags = flags
        self.message_id = message_id
        self.status = "starting"  # starting, running, completed, failed, aborted
        self.started_at = time.time()
        self.finished_at = None
        self.session_id = None  # claude session-id (aus Output)
        self.raw_text = ""  # Rohtext von Claude (unverändert)
        self.full_text = ""  # MarkdownV2-konvertierter Text für Anzeige
        self.last_log_lines = []  # Letzte Logs für Anzeige
        self.process = None  # asyncio.subprocess.Process
        self.watcher_task = None
        self.pending_permission = None  # {tool_name, input, prompt_id} für Tool-Freigabe

class UserState:
    """Persistente Einstellungen pro User."""
    def __init__(self):
        self.permission_mode = "default"
        self.model = CURRENT_PROVIDER.model  # Standard-Modell des aktiven Providers
        self.system_prompt_append = ""
        self.working_dir = WORKING_DIR
        self.add_dirs = []
        self.allowed_tools = []
        self.disallowed_tools = []
        self.tools = "default"  # Alle Tools aktiv
        self.session_id = None
        self.continue_session = True  # -c flag
        self.worktree = False
        self.safe_mode = False
        self.language = "de"  # UI-Sprache: "de" oder "en"

user_states: dict[int, UserState] = {}
active_jobs: dict[int, Job] = {}  # user_id -> aktiver Job (max 1)

# Default-Permissions: Diese Tools/Patterns werden automatisch erlaubt.
# Werden beim ersten /config angewendet und können via /tools deny entfernt werden.
DEFAULT_ALLOWED_TOOLS = [
    "Bash(*)",      # Alle Bash-Befehle
    "Edit",         # Dateien editieren
    "Write",        # Dateien schreiben
    "Read",         # Dateien lesen
    "Glob",         # Datei-Suche
    "Grep",         # Inhalt-Suche
    "WebSearch",    # Web-Suche
    "WebFetch",     # Web-Inhalte laden
    "TodoWrite",    # Todo-Verwaltung
    "Task",         # Sub-Tasks
    "NotebookEdit", # Notebooks
    "BashOutput",   # Bash-Output lesen
    "KillShell",    # Background-Shells beenden
]

def get_user_state(user_id: int) -> UserState:
    if user_id not in user_states:
        user_states[user_id] = UserState()
        # Geladene Einstellungen aus Memory übernehmen
        saved = load_user_state(user_id)
        state = user_states[user_id]
        if saved:
            state.permission_mode = saved.get("permission_mode", "default")
            state.model = saved.get("model", "auto")
            state.system_prompt_append = saved.get("system_prompt_append", "")
            state.working_dir = saved.get("working_dir", WORKING_DIR)
            state.add_dirs = saved.get("add_dirs", [])
            state.allowed_tools = saved.get("allowed_tools", [])
            state.disallowed_tools = saved.get("disallowed_tools", [])
            state.tools = saved.get("tools", "default")
            state.session_id = saved.get("session_id")
            state.continue_session = saved.get("continue_session", True)
            state.worktree = saved.get("worktree", False)
            state.safe_mode = saved.get("safe_mode", False)
            state.language = saved.get("language", "de")
            # Wenn Liste leer oder fast leer ist (nur WebSearch): Defaults laden
            # Migration: Alte Userstates, die nur ein Tool haben, werden auf Defaults erweitert
            if len(state.allowed_tools) < 5:
                logger.info(f"User {user_id}: {len(state.allowed_tools)} allowed tools - lade Defaults")
                for t in DEFAULT_ALLOWED_TOOLS:
                    if t not in state.allowed_tools and t not in state.disallowed_tools:
                        state.allowed_tools.append(t)
                save_user_state(user_id, state)
        else:
            # Erste Anmeldung: Default-Permissions automatisch setzen
            for t in DEFAULT_ALLOWED_TOOLS:
                if t not in state.allowed_tools:
                    state.allowed_tools.append(t)
            save_user_state(user_id, state)
    return user_states[user_id]

# --- Permission-Mode zu CLI-Flags ---
def permission_mode_to_flags(mode: str) -> list:
    if mode == "default":
        return []
    return ["--permission-mode", mode]

def build_claude_command(job: Job, state: UserState) -> list:
    """Baut den claude Befehl zusammen (asynchron, nicht --bg)."""
    cmd = ["claude"]

    # Provider-spezifische Environment-Variablen
    # werden in start_claude_job via env= gesetzt

    # Output-Format für stream-json (wir parsen später)
    cmd += ["--output-format", "stream-json"]
    cmd += ["--verbose"]  # notwendig für stream-json
    cmd += ["--include-partial-messages"]

    # Print-Modus (non-interactive, mit Output)
    cmd += ["-p", job.prompt]

    # Permission-Mode
    cmd += permission_mode_to_flags(state.permission_mode)

    # Modell
    if state.model:
        cmd += ["--model", state.model]

    # System prompt: nur das, was der User explizit will
    if state.system_prompt_append:
        cmd += ["--append-system-prompt", state.system_prompt_append]

    # Verzeichnisse
    for d in state.add_dirs:
        cmd += ["--add-dir", d]

    # Tools: "default" NICHT explizit setzen — sonst überschreibt es das
    # eingebaute Default-Set der CLI (inkl. WebSearch, WebFetch, Read, Edit, ...).
    # Nur explizite Sets (z.B. "Read,Edit") werden übergeben.
    if state.tools and state.tools != "default":
        cmd += ["--tools", state.tools]
    # Erlaubte Tools: nur setzen, wenn explizit konfiguriert.
    # Andernfalls nutzt claude CLI ihre Defaults (inkl. WebSearch/WebFetch).
    if state.allowed_tools:
        for t in state.allowed_tools:
            cmd += ["--allowedTools", t]
    if state.disallowed_tools:
        for t in state.disallowed_tools:
            cmd += ["--disallowedTools", t]

    # Session fortsetzen
    # Wir benutzen IMMER --resume <id> wenn eine Session-ID bekannt ist,
    # weil -c die "zuletzt in diesem CWD aktive" Session nimmt – das ist
    # nach einem Bot-Neustart oder wenn der User vorher /new genutzt hat,
    # eine ANDERE Session als die, die wir fortsetzen wollen.
    if state.session_id and state.continue_session:
        cmd += ["--resume", state.session_id]

    # Worktree
    if state.worktree:
        cmd += ["-w"]

    # Safe mode
    if state.safe_mode:
        cmd += ["--safe-mode"]

    return cmd

# --- Job starten ---
def build_provider_env() -> dict:
    """Baut die Environment-Variablen für den aktiven Provider (generisch)."""
    env = os.environ.copy()

    # Alle Claude-Code-Gateway-Variablen setzen, die der jeweilige Provider
    # benötigen könnte. base_url zeigt auf einen beliebigen API-Endpoint.
    if CURRENT_PROVIDER.base_url:
        env["ANTHROPIC_BASE_URL"] = CURRENT_PROVIDER.base_url

    if CURRENT_PROVIDER.api_key:
        # Auth-Token (Anthropic-kompatibler Gateway)
        env["ANTHROPIC_AUTH_TOKEN"] = CURRENT_PROVIDER.api_key
        # Auch als klassischer API-Key setzen (viele Endpoints akzeptieren beides)
        env["ANTHROPIC_API_KEY"] = CURRENT_PROVIDER.api_key

    env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] = "1"

    # Optional: Modell über Umgebungsvariable erzwingen
    if CURRENT_PROVIDER.model:
        env["CLAUDE_MODEL"] = CURRENT_PROVIDER.model

    return env

async def start_claude_job(job: Job, state: UserState) -> tuple[bool, str]:
    """Startet einen claude -p Subprocess (asynchron, läuft bis fertig)."""
    cmd = build_claude_command(job, state)
    env = build_provider_env()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=state.working_dir,
            env=env,
        )
        job.process = proc
        job.status = "running"
        return True, ""

    except FileNotFoundError:
        return False, "claude CLI nicht gefunden. Ist Claude Code installiert?"
    except Exception as e:
        logger.exception("Fehler beim Starten")
        return False, f"Unerwarteter Fehler: {e}"

# --- Watcher: Liest direkt aus proc.stdout (Live-Streaming) ---
async def watch_job(job: Job, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liest stdout vom claude-Prozess zeilenweise und aktualisiert Telegram."""
    proc = job.process
    if not proc:
        return

    last_edit_time = 0
    stderr_lines = []

    # Lese parallel stderr (für Fehlermeldungen)
    async def read_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            err = line.decode(errors="replace").rstrip()
            if err and not any(p in err for p in NOISE_PATTERNS):
                stderr_lines.append(err)
                job.last_log_lines.append(f"⚠️ {err[:200]}")
                if len(job.last_log_lines) > 100:
                    job.last_log_lines = job.last_log_lines[-100:]

    stderr_task = asyncio.create_task(read_stderr())

    try:
        # Hauptschleife: Lese stdout in großen Blöcken und splitte nach Newlines
        # (readline() hat einen 64KB-Limit, der bei langen JSON-Zeilen crasht)
        buffer = ""
        while True:
            chunk = await proc.stdout.read(1024 * 1024)  # 1MB pro Read
            if not chunk:
                # Prozess beendet
                break
            buffer += chunk.decode(errors="replace")
            while "\n" in buffer:
                line_str, buffer = buffer.split("\n", 1)
                line_str = line_str.rstrip()
                if not line_str:
                    continue

                # Versuche JSON zu parsen (stream-json Format)
                try:
                    event = json.loads(line_str)
                    await handle_stream_event(job, event, context)
                except json.JSONDecodeError:
                    # Plain text log
                    if not any(p in line_str for p in NOISE_PATTERNS):
                        job.last_log_lines.append(line_str[:200])
                        if len(job.last_log_lines) > 100:
                            job.last_log_lines = job.last_log_lines[-100:]

                # Telegram-Update throttled
                now = time.time()
                if now - last_edit_time >= STREAM_UPDATE_INTERVAL:
                    await update_telegram_message(job, update, context)
                    last_edit_time = now

        # Warte auf Prozess-Ende
        await proc.wait()
        stderr_task.cancel()
        try:
            await stderr_task
        except asyncio.CancelledError:
            pass

        # Job-Status setzen
        if job.status == "running":
            if proc.returncode == 0:
                job.status = "completed"
            else:
                job.status = "failed"
                if stderr_lines:
                    job.last_log_lines.append(f"❌ Exit-Code {proc.returncode}: {stderr_lines[-1][:200]}")

        # Finalisieren
        await finalize_job(job, update, context)

    except asyncio.CancelledError:
        logger.info(f"Watcher für Job {job.id} abgebrochen")
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
    except Exception as e:
        logger.exception(f"Watcher-Fehler: {e}")
        job.status = "failed"
        job.last_log_lines.append(f"❌ Watcher-Fehler: {e}")
        await finalize_job(job, update, context)

async def handle_stream_event(job: Job, event: dict, context: ContextTypes.DEFAULT_TYPE):
    """Verarbeitet ein einzelnes stream-json Event."""
    etype = event.get("type", "")

    if etype == "content_block_start":
        block = event.get("content_block", {})
        if block.get("type") == "tool_use":
            tool_name = block.get("name", "?")
            job.last_log_lines.append(f"🛠️ Tool-Aufruf: {tool_name}")
            # Permission-Prompt?
            if job.pending_permission is None and "permission" in str(event).lower():
                job.pending_permission = {
                    "tool_name": tool_name,
                    "tool_input": block.get("input", {}),
                    "id": block.get("id"),
                }
            # NEU: Auto-Erkennung fehlender Tools → User fragen
            state = get_user_state(job.user_id)
            tool_lower = tool_name.lower()
            allowed_set = {t.lower() for t in state.allowed_tools}
            if state.tools and tool_lower not in allowed_set:
                # Tool wird benutzt, ist aber NICHT erlaubt → nachfragen
                if job.pending_permission is None:
                    job.pending_permission = {
                        "tool_name": tool_name,
                        "tool_input": block.get("input", {}),
                        "id": block.get("id"),
                        "auto_ask": True,
                    }
                    job.last_log_lines.append(f"❓ Tool '{tool_name}' nicht erlaubt – frage nach…")

    elif etype == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            job.raw_text += text
            # Letzte Logs für Anzeige
            if len(job.last_log_lines) == 0 or not job.last_log_lines[-1].startswith("💬"):
                job.last_log_lines.append("💬 " + text[:200])
            else:
                # Append to last line
                last = job.last_log_lines[-1]
                if len(last) < 500:
                    job.last_log_lines[-1] = last + text[:200]
            # Live-Konvertierung: Rohtext → MarkdownV2
            job.full_text = markdown_to_markdownv2(job.raw_text)

    elif etype == "message_start":
        # Session-ID extrahieren (robust gegen String-message)
        msg = event.get("message")
        if isinstance(msg, dict) and msg.get("id"):
            job.session_id = msg["id"]
    elif etype in ("session_start", "session_id"):
        # Manche stream-json-Versionen geben Session-ID explizit aus
        sid = event.get("session_id") or event.get("id")
        if sid:
            job.session_id = sid
    elif etype == "result":
        # Finale Session-ID (manche Versionen geben sie hier)
        sid = event.get("session_id") or event.get("sessionId")
        if sid:
            job.session_id = sid
    elif etype == "system" and event.get("subtype") == "init":
        # Aktuelle claude-CLI (>=2.x) emittiert genau dieses Event am Anfang
        # und enthält die Session-ID als Top-Level-Feld.
        sid = event.get("session_id")
        if sid:
            job.session_id = sid
            # Sofort persistieren, damit auch bei Crashes die ID erhalten bleibt
            try:
                state = get_user_state(job.user_id)
                state.session_id = sid
                save_session(job.user_id, sid)
            except Exception as e:
                logger.warning(f"Session-Persist fehlgeschlagen: {e}")

    elif etype == "message_stop":
        # Finale Konvertierung des rohen Textes
        job.full_text = markdown_to_markdownv2(job.raw_text)
        job.last_log_lines.append("✅ Antwort vollständig")

    elif etype == "error":
        err = event.get("error", {})
        job.last_log_lines.append(f"❌ Fehler: {err.get('message', err)}")
        job.status = "failed"

    elif etype == "permission_request":
        # Claude fragt nach Permission für ein Tool
        tool_name = event.get("tool_name", "?")
        tool_input = event.get("tool_input", {})
        job.pending_permission = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "id": event.get("request_id"),
        }
        # Klare Anzeige: Tool + Eingabe
        job.last_log_lines.append(f"🔐 PERMISSION: {tool_name}")
        if tool_input:
            input_preview = str(tool_input)[:200]
            job.last_log_lines.append(f"   Input: {input_preview}")
        # Sofort speichern, dass der Bot aktiv auf Permission wartet
        state = get_user_state(job.user_id)
        save_user_state(job.user_id, state)

    elif etype in ("assistant", "user", "system"):
        # Generelle Nachrichten: als Rohtext sammeln und live konvertieren
        # Robust: "message" kann dict ODER String sein (je nach stream-json Version)
        msg = event.get("message")
        if isinstance(msg, dict):
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text and text not in job.raw_text:
                            job.raw_text += text
                            job.full_text = markdown_to_markdownv2(job.raw_text)

async def update_telegram_message(job: Job, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aktualisiert die Telegram-Nachricht mit dem aktuellen Stand."""
    try:
        # Header mit Status
        elapsed = int(time.time() - job.started_at)
        elapsed_str = format_duration(elapsed)

        if job.status == "starting":
            text = f"🔄 *Job wird gestartet...*"
        elif job.status == "running":
            status = "🟢 läuft"
            if job.pending_permission:
                status = "🔐 wartet auf Freigabe"
            # Header ohne MarkdownV2-Sonderzeichen, damit nichts kaputt geht
            text = f"Claude {status} · {elapsed_str}\n"

            # KLARE PERMISSION-ANZEIGE (oben, immer sichtbar)
            if job.pending_permission:
                perm = job.pending_permission
                tool_name = perm.get("tool_name", "?")
                tool_input = perm.get("tool_input", {})
                # Tool-Pattern für /tools allow Befehl
                tool_pattern = tool_name
                if tool_input and isinstance(tool_input, dict):
                    # Versuche spezifischeres Pattern (z.B. Bash(python3 *))
                    cmd = tool_input.get("command") or tool_input.get("cmd")
                    if cmd:
                        first_word = str(cmd).split()[0] if cmd else ""
                        if first_word:
                            tool_pattern = f"{tool_name}({first_word} *)"
                text += f"\n\n🔐 *TOOL-PERMISSION ERFORDERLICH*\n"
                text += f"→ Tool: `{tool_name}`\n"
                text += f"→ Pattern: `{tool_pattern}`\n"
                if tool_input:
                    input_str = str(tool_input)[:200]
                    text += f"→ Input: `{input_str}`\n"
                text += f"\n*Freigabe-Befehl:*\n"
                text += f"`/tools allow {tool_pattern}`\n"
                text += f"\n*Oder wähle unten eine Option:*\n"

            # Live-Text anzeigen (MarkdownV2-konvertiert)
            if job.full_text:
                preview = job.full_text[-2000:]
                text += f"\n{preview}"

        else:
            return  # Kein Update mehr

        # Inline-Buttons: Stop + Status
        keyboard = [
            [
                InlineKeyboardButton("🛑 Stop", callback_data=f"stop:{job.user_id}"),
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh:{job.user_id}"),
            ]
        ]
        # Permission-Buttons: IMMER anzeigen wenn pending (auch im auto-Mode sichtbar)
        if job.pending_permission:
            tool_name = job.pending_permission.get("tool_name", "Tool")
            # Klare Beschriftung mit Tool-Name
            keyboard.append([
                InlineKeyboardButton(f"✅ Ja ({tool_name})", callback_data=f"perm_allow:{job.user_id}"),
                InlineKeyboardButton("❌ Nein", callback_data=f"perm_deny:{job.user_id}"),
                InlineKeyboardButton(f"✅ Immer {tool_name}", callback_data=f"perm_always:{job.user_id}"),
            ])

        # Telegram-Limit: 4096 Zeichen pro Nachricht.
        # Statt zu kürzen: In bis zu 3 Teilnachrichten aufteilen, wenn nötig.
        if len(text) > 4000:
            # Erste ~3950 Zeichen in die bestehende Statusnachricht editieren
            # (mit Hinweis auf Fortsetzung), Rest als Folge-Nachrichten senden.
            first_part = text[:3950]
            rest = text[3950:]
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=job.message_id,
                    text=first_part + "\n\n… (Fortsetzung folgt)",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            except Exception as e:
                logger.warning(f"Split-Edit-Update fehlgeschlagen: {e!r}")
            # Rest in bis zu 2 weiteren Telegram-Nachrichten
            for chunk in [rest[i:i+3950] for i in range(0, len(rest), 3950)][:2]:
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=chunk,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                except Exception as e:
                    logger.warning(f"Split-Send fehlgeschlagen: {e!r}")
            return

        # Normaler Fall: passt in eine Nachricht
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=job.message_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.warning(f"Update fehlgeschlagen: {e!r}")
                logger.warning(f"Gesendeter Text (Auszug): {text[-500:]!r}")
    except Exception as e:
        logger.warning(f"update_telegram_message Fehler: {e!r}")

async def finalize_job(job: Job, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Schließt den Job ab und zeigt das finale Ergebnis."""
    job.finished_at = time.time()
    if job.status == "running":
        job.status = "completed"

    elapsed = int(job.finished_at - job.started_at)
    elapsed_str = format_duration(elapsed)

    # Speichere Session-ID im User-State + Memory
    state = get_user_state(job.user_id)
    if job.session_id:
        state.session_id = job.session_id
        save_session(job.user_id, job.session_id)

    # Folge-Nachrichten sollen die Session fortsetzen.
    # (continue_session=False entsteht nur durch /new — das ist explizit.)
    state.continue_session = True

    # Speichere User-State ins Memory
    save_user_state(job.user_id, state)

    # Speichere Antwort in History (Prompt wurde bereits beim Start gespeichert)
    if job.raw_text:
        add_history_entry(job.user_id, "assistant", job.raw_text, job.id)

    # Speichere Job-Log
    save_job_log(job.user_id, job.id, job.status, job.raw_text)

    # Finalen Text formatieren: immer vom Rohtext ausgehen, sicher konvertieren.
    if job.raw_text:
        text = markdown_to_markdownv2(job.raw_text)
        job.full_text = text
    else:
        # Fallback: markdownv2-sicher (keine unescapten ( ))
        text = markdown_to_markdownv2(job.full_text) or "_Keine Antwort erhalten_"

    keyboard_rows = []

    status_emoji = {
        "completed": "✅",
        "failed": "❌",
        "aborted": "🛑",
    }
    emoji = status_emoji.get(job.status, "❓")

    final_text = f"{emoji} *Fertig* · {elapsed_str}\n\n{text}"

    # Telegram-Limit: 4096 Zeichen pro Nachricht.
    # Lange Antworten werden in mehrere Nachrichten aufgeteilt statt gekürzt.
    try:
        if len(final_text) > 4000:
            # Erste ~3950 Zeichen in die bestehende Nachricht editieren
            first_part = final_text[:3950] + "\n\n_... (Fortsetzung folgt)_"
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=job.message_id,
                text=first_part,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(keyboard_rows),
            )
            # Rest als Folge-Nachrichten senden
            rest = final_text[3950:]
            while rest:
                chunk = rest[:3950]
                rest = rest[3950:]
                suffix = "\n\n_... (weiter)_" if rest else ""
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=chunk + suffix,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True,
                )
        else:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=job.message_id,
                text=final_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(keyboard_rows),
            )
    except Exception as e:
        logger.warning(f"Finale Nachricht fehlgeschlagen: {e!r}")
        logger.warning(f"Gesendeter Text (Auszug): {final_text[-500:]!r}")

    # Job aus active_jobs entfernen
    if active_jobs.get(job.user_id) is job:
        del active_jobs[job.user_id]

def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"
    h, m = divmod(seconds, 3600)
    return f"{h}h {m}m"

# --- Markdown-zu-MarkdownV2 Konverter ---
import html as html_module
import re as re_module

ALLOWED_HTML_TAGS = {"b", "i", "code", "pre", "a", "u", "s", "tg-spoiler"}

# MarkdownV2-Sonderzeichen, die escaped werden müssen
MD2_SPECIAL = r"_*[]()~`>#+-=|{}.!"  # > muss überall escaped werden (auch mitten im Text)


def escape_markdownv2(text: str) -> str:
    """Escaped MarkdownV2-Sonderzeichen, aber nur in reinem Text (nicht in Code-Blocks)."""
    # Strategie: Code-Blöcke und Inline-Code markieren, Text escapen, Code-Inhalte roh lassen
    placeholders = {}

    def protect(match, key_prefix):
        key = f"§§§{key_prefix}{len(placeholders)}§§§"
        placeholders[key] = match.group(0)
        return key

    # 1. Code-Blöcke schützen
    text = re_module.sub(r'```.*?```', lambda m: protect(m, "CB"), text, flags=re_module.DOTALL)
    # 2. Inline-Code schützen
    text = re_module.sub(r'`[^`\n]+`', lambda m: protect(m, "IC"), text)
    # 3. URLs in Links extrahieren: [text](url) -> [text](§§§URL0§§§)
    text = re_module.sub(r'\[([^\]]+)\]\(([^\)]+)\)',
        lambda m: protect(re_module.match(r'\[[^\]]+\]\([^\)]+\)', m.group(0)).group(0).replace(m.group(2), f"§§§URL{len(placeholders)}§§§"), "L")
        if False else f"[{m.group(1)}](§§§URL{len(placeholders)}§§§)".replace(f"§§§URL{len(placeholders)-1}§§§", f"§§§URL{len(placeholders)}§§§"),
        text)
    # (einfacher: schütze URL-Teile separat)
    # ... stattdessen: URL-Teile in-place schützen
    # Vereinfachung: Wir schützen nur Code und escapen danach

    # 4. Sonderzeichen escapen
    for char in MD2_SPECIAL:
        text = text.replace(char, f"\\{char}")

    # 5. Markdown → MarkdownV2 Mapping (vorher!)
    # Wir müssen vor dem Escapen konvertieren, aber nach dem Schutz der Codes.

    # Zurücksetzen und mit anderer Reihenfolge nochmal
    return text  # Wird in der nächsten Phase neu gemacht


def markdown_to_markdownv2(text: str) -> str:
    """Konvertiert normales Markdown zu Telegram-MarkdownV2."""
    if not text:
        return ""

    # Schutz-Platzhalter für Bereiche, die nicht escaped werden dürfen
    protected = {}
    counter = [0]

    def protect(content: str) -> str:
        key = f"\x00PROT{counter[0]}\x00"
        counter[0] += 1
        protected[key] = content
        return key

    # 1. Code-Blöcke (```...```) schützen + zu MarkdownV2
    def code_block_repl(m):
        lang = m.group(1) or ""
        content = m.group(2)
        return protect(f"```{lang}\n{content}\n```")
    text = re_module.sub(r'```(\w*)\n(.*?)\n```', code_block_repl, text, flags=re_module.DOTALL)

    # 2. Inline-Code (`...`) schützen
    text = re_module.sub(r'`([^`\n]+)`', lambda m: protect(f"`{m.group(1)}`"), text)

    # 2b. Überschriften: #/##/### vor der Fett/Kursiv-Verarbeitung zu *Bold* umwandeln,
    #     damit Telegram sie anzeigt (Telegram hat keine echten Header-Entities).
    def header_repl(m):
        content = m.group(1)
        # Sonderzeichen im Header-Inhalt escapen (sie stehen dann innerhalb von *...*)
        for ch in MD2_SPECIAL:
            content = content.replace(ch, f"\\{ch}")
        return protect(f"*{content}*")
    text = re_module.sub(r'(?m)^#{1,6}\s+(.+)$', header_repl, text)

    # 3. Zuerst unilateraler Unterstrich-Kursiv schützen (_x_ NICHT in Variablennamen).
    #    Vor Bold, damit _kursiv_ innerhalb von **fett _kursiv_** korrekt verschachtelt bleibt.
    def esc_inner(s: str) -> str:
        for ch in MD2_SPECIAL:
            s = s.replace(ch, f"\\{ch}")
        return s

    text = re_module.sub(r'(?<![A-Za-z0-9_])_([^_\n]+?)_(?![A-Za-z0-9_])', lambda m: protect(f"_{esc_inner(m.group(1))}_"), text)

    # 4. Fett/Italic (Stern)/Durchgestrichen übersetzen. WICHTIG: Telegram verlangt, dass
    #    Spezialzeichen AUCH INNERHALB einer Fett/Kursiv-Entity escapet werden
    #    (z. B. *Wichtig!* -> *Wichtig\!*). Deshalb wird der innere Text zuerst
    #    escaped, bevor er als Platzhalter geschützt wird.
    text = re_module.sub(r'\*\*([^\*\n]+?)\*\*', lambda m: protect(f"*{esc_inner(m.group(1))}*"), text)
    text = re_module.sub(r'__([^_\n]+?)__', lambda m: protect(f"*{esc_inner(m.group(1))}*"), text)
    text = re_module.sub(r'(?<!\*)\*([^\*\n]+?)\*(?!\*)', lambda m: protect(f"_{esc_inner(m.group(1))}_"), text)
    text = re_module.sub(r'~~([^~\n]+?)~~', lambda m: protect(f"~{esc_inner(m.group(1))}~"), text)

    # 4. Sonderzeichen escapen (geschützte Bereiche sind Platzhalter, bleiben unberührt)
    for char in MD2_SPECIAL:
        text = text.replace(char, f"\\{char}")

    # 5. Platzhalter in UMGEREHRTER Reihenfolge wieder einsetzen, damit ein Code-
    #    Platzhalter, der innerhalb eines Fett-Platzhalters steckt, korrekt ersetzt wird.
    for key, content in reversed(list(protected.items())):
        text = text.replace(key, content)

    return text

def markdown_to_html(text: str) -> str:
    """Konvertiert Markdown zu Telegram-HTML."""
    if not text:
        return ""

    # 1. Code-Blöcke (``` ... ```) -> <pre>...</pre> (zuerst, da greedy)
    def code_block_repl(m):
        content = m.group(2)
        # Inhalt escapen, aber Newlines behalten
        return f"<pre>{html_module.escape(content)}</pre>"
    text = re_module.sub(r'```(\w*)\n(.*?)\n```', code_block_repl, text, flags=re_module.DOTALL)

    # 2. Inline-Code ` ... ` -> <code>...</code> (vor bold/italic, damit ** in code nicht falsch geparst wird)
    text = re_module.sub(r'`([^`\n]+)`', lambda m: f"<code>{html_module.escape(m.group(1))}</code>", text)

    # 3. Headers: ### Header -> <b>Header</b>
    text = re_module.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re_module.MULTILINE)

    # 4. Bold **text** -> <b>text</b>
    text = re_module.sub(r'\*\*([^\*\n]+?)\*\*', r'<b>\1</b>', text)
    # Auch __text__ für Bold
    text = re_module.sub(r'__([^_\n]+?)__', r'<b>\1</b>', text)

    # 5. Italic *text* -> <i>text</i> (nach Bold, damit * nicht doppelt matched)
    text = re_module.sub(r'\*([^\*\n]+?)\*', r'<i>\1</i>', text)
    text = re_module.sub(r'(?<![A-Za-z0-9])_([^_\n]+?)_(?![A-Za-z0-9])', r'<i>\1</i>', text)

    # 6. Links [text](url) -> <a href="url">text</a>
    text = re_module.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', text)

    return text


def sanitize_html(text: str) -> str:
    """Erlaubt nur Telegram-HTML-Tags, alles andere wird escaped."""
    if not text:
        return ""

    # Wenn schon valides HTML enthalten ist, nicht doppelt verarbeiten
    # Wir extrahieren erlaubte Tags, escapen den Rest
    pattern = re_module.compile(
        r'<(/?)(b|i|code|pre|a|u|s|tg-spoiler)([^>]*)>',
        re_module.IGNORECASE
    )

    result = []
    last_end = 0

    for match in pattern.finditer(text):
        # Vorherigen Text escapen
        before = text[last_end:match.start()]
        result.append(html_module.escape(before, quote=False))

        closing = match.group(1) == "/"
        tag = match.group(2).lower()
        attrs = match.group(3)

        if closing:
            result.append(f"</{tag}>")
        else:
            # Nur href-Attribut bei <a> erlauben
            if tag == "a":
                href_match = re_module.search(r'href\s*=\s*"([^"]*)"', attrs)
                if href_match:
                    href = html_module.escape(href_match.group(1), quote=True)
                    result.append(f'<a href="{href}">')
                else:
                    # Ohne href wird der <a> zu <b>
                    result.append("<b>")
            else:
                result.append(f"<{tag}>")

        last_end = match.end()

    # Rest escapen
    result.append(html_module.escape(text[last_end:], quote=False))
    return "".join(result)


def has_markdown(text: str) -> bool:
    """Heuristik: Enthält der Text Markdown-Formatierung?"""
    if not text:
        return False
    md_patterns = [
        r'```',  # Code-Block
        r'`[^`\n]+`',  # Inline-Code
        r'\*\*[^\*]+\*\*',  # Bold
        r'\[[^\]]+\]\([^\)]+\)',  # Link
    ]
    for p in md_patterns:
        if re_module.search(p, text):
            return True
    return False


# --- Copy-Buttons ---
import html

def extract_copy_buttons(text: str) -> list:
    """Extrahiert Copy-Buttons für Dateinamen, Pfade und Code-Snippets."""
    buttons = []
    seen = set()

    # 1. Inline-Code mit Dateipfaden
    file_pattern = r'`(/[\w/._-]+)`'
    for match in re.finditer(file_pattern, text):
        filepath = match.group(1)
        if len(filepath) < 50 and filepath not in seen:
            seen.add(filepath)
            filename = filepath.split('/')[-1]
            if filename:
                buttons.append(InlineKeyboardButton(f"📋 {filename}", copy_text=CopyTextButton(filepath)))

    # 2. HTML <code>-Tags mit Pfaden
    for match in re.finditer(r'<code>(/[\w/._-]+)</code>', text):
        filepath = match.group(1)
        if len(filepath) < 50 and filepath not in seen:
            seen.add(filepath)
            filename = filepath.split('/')[-1]
            if filename:
                buttons.append(InlineKeyboardButton(f"📋 {filename}", copy_text=CopyTextButton(filepath)))

    # 3. Code-Blöcke (kompletter Inhalt)
    for i, match in enumerate(re.finditer(r'```(?:\w*)\n(.*?)\n```', text, re.DOTALL)):
        code = match.group(1).strip()
        if 20 < len(code) < 500 and code not in seen:
            seen.add(code[:50])
            preview = code.split('\n')[0][:30] or f"Code {i+1}"
            buttons.append(InlineKeyboardButton(f"📄 {preview}", copy_text=CopyTextButton(code)))

    # 4. ls-Output: Dateinamen mit Endung in eigenen Zeilen
    file_extensions = r'\.(py|md|json|js|ts|txt|sh|yaml|yml|toml|css|html|go|rs|java|cpp|c|h|rb|php|sql)'
    for match in re.finditer(rf'(?:^|\s)([\w./_-]+{file_extensions})(?:\s|$)', text, re.MULTILINE):
        filename = match.group(1)
        if len(filename) < 40 and filename not in seen and "/" not in filename.replace("./", ""):
            seen.add(filename)
            buttons.append(InlineKeyboardButton(f"📄 {filename}", copy_text=CopyTextButton(filename)))

    return buttons[:8]

# --- Bot-Handler ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)
    lang = state.language
    # MarkdownV2-Escape für Working-Dir (Slashes & Punkte)
    cwd_escaped = state.working_dir.replace("\\", "\\\\").replace(".", "\\.").replace("-", "\\-")
    model_escaped = state.model.replace("\\", "\\\\").replace(".", "\\.").replace("-", "\\-")
    # Mode-String escapen (z.B. "Default (fragt bei Bedarf)")
    mode_raw = PERMISSION_MODE_LABELS.get(state.permission_mode, state.permission_mode)
    mode_escaped = mode_raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace(".", "\\.")
    text = _("welcome", lang,
             model=model_escaped,
             mode=mode_escaped,
             cwd=cwd_escaped,
             lang_label=LANG_NAMES.get(lang, lang))
    keyboard = [
        [
            InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang:de"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
        ]
    ]
    try:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.warning(f"Start-Message Markdown-Fehler: {e}")
        # Fallback auf HTML
        text_html = text.replace("\\", "").replace("*", "<b>").replace("</b>", "**", 1)
        text_html = re_module.sub(r"\*([^*]+)\*", r"<b>\1</b>", text_html)
        text_html = re_module.sub(r"_([^_]+)_", r"<i>\1</i>", text_html)
        await update.message.reply_text(text_html, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt die Befehlsübersicht – ohne Session zu starten oder Status zu ändern."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)
    lang = state.language
    if lang == "de":
        text = (
            "<b>📋 Befehle</b>\n\n"
            "<b>Session:</b>\n"
            "/new – Neue Session starten\n"
            "/resume – Session fortsetzen\n"
            "/stop – Aktiven Job stoppen\n"
            "/logs – Job-Logs anzeigen\n\n"
            "<b>Einstellungen:</b>\n"
            "/model – Modell wechseln\n"
            "/mlist – Modelle anzeigen\n"
            "/provider – Provider wechseln\n"
            "/cd – Arbeitsverzeichnis ändern\n"
            "/add – Verzeichnis hinzufügen\n"
            "/system – System-Prompt ändern\n\n"
            "<b>Modi:</b>\n"
            "/plan – Plan-Modus\n"
            "/auto – Auto-Modus\n"
            "/accept – Accept-Edits\n"
            "/bypass – Bypass-Permissions\n"
            "/default – Default-Modus\n"
            "/dontask – Dont-Ask-Modus\n\n"
            "<b>Tools:</b>\n"
            "/tools – Tool-Berechtigungen\n"
            "/permissions – Permission-Modi\n\n"
            "<b>Dateien:</b>\n"
            "/read · /write · /ls · /grep · /exec\n\n"
            "<b>Sonstiges:</b>\n"
            "/status – Status anzeigen\n"
            "/config – Config anzeigen\n"
            "/doctor – Diagnose\n"
            "/language – Sprache wechseln\n"
            "/menu – Diese Hilfe"
        )
    else:
        text = (
            "<b>📋 Commands</b>\n\n"
            "<b>Session:</b>\n"
            "/new – New session\n"
            "/resume – Resume session\n"
            "/stop – Stop active job\n"
            "/logs – Show job logs\n\n"
            "<b>Settings:</b>\n"
            "/model – Switch model\n"
            "/mlist – List models\n"
            "/provider – Switch provider\n"
            "/cd – Change working dir\n"
            "/add – Add directory\n"
            "/system – Change system prompt\n\n"
            "<b>Modes:</b>\n"
            "/plan – Plan mode\n"
            "/auto – Auto mode\n"
            "/accept – Accept edits\n"
            "/bypass – Bypass permissions\n"
            "/default – Default mode\n"
            "/dontask – Dont-ask mode\n\n"
            "<b>Tools:</b>\n"
            "/tools – Tool permissions\n"
            "/permissions – Permission modes\n\n"
            "<b>Files:</b>\n"
            "/read · /write · /ls · /grep · /exec\n\n"
            "<b>Other:</b>\n"
            "/status – Show status\n"
            "/config – Show config\n"
            "/doctor – Diagnostics\n"
            "/language – Switch language\n"
            "/menu – This help"
        )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_menu(update, context)

async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wechselt die UI-Sprache (de/en)."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)
    if context.args and context.args[0] in ("de", "en"):
        state.language = context.args[0]
        save_user_state(update.effective_user.id, state)
        await update.message.reply_text(_("language_set", state.language), parse_mode=ParseMode.HTML)
        return
    text = _("lang_select", state.language, current=LANG_NAMES.get(state.language, state.language))
    keyboard = [
        [
            InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang:de"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
        ]
    ]
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    job = active_jobs.get(update.effective_user.id)
    state = get_user_state(update.effective_user.id)

    text = "<b>📊 Status</b>\n\n"
    text += f"<b>Permission-Mode:</b> {PERMISSION_MODE_LABELS.get(state.permission_mode, state.permission_mode)}\n"
    text += f"<b>Modell:</b> {state.model}\n"
    text += f"<b>Working Dir:</b> <code>{html.escape(state.working_dir)}</code>\n"
    if state.add_dirs:
        text += f"<b>Add-Dirs:</b> {', '.join(f'<code>{html.escape(d)}</code>' for d in state.add_dirs)}\n"
    if state.system_prompt_append:
        text += f"<b>System-Prompt:</b> <code>{html.escape(state.system_prompt_append[:100])}</code>\n"
    if state.session_id:
        text += f"<b>Session-ID:</b> <code>{state.session_id[:8]}...</code>\n"
    if state.worktree:
        text += f"<b>Worktree:</b> aktiv\n"

    if job:
        elapsed = int(time.time() - job.started_at)
        text += f"\n<b>Aktiver Job:</b>\n"
        text += f"• Status: {job.status}\n"
        text += f"• ID: <code>{job.id or '...'}</code>\n"
        text += f"• Laufzeit: {format_duration(elapsed)}\n"
        text += f"• Prompt: <code>{html.escape(job.prompt[:100])}</code>\n"
    else:
        text += "\n<i>Kein aktiver Job.</i>\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    job = active_jobs.get(update.effective_user.id)
    if not job:
        await update.message.reply_text("ℹ️ Kein aktiver Job.", parse_mode=ParseMode.HTML)
        return
    await stop_job(job, update, context)
    await update.message.reply_text("🛑 Job gestoppt.", parse_mode=ParseMode.HTML)

async def stop_job(job: Job, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stoppt einen laufenden Job durch Killen des Prozesses."""
    job.status = "aborted"
    # Watcher-Task abbrechen (kümmert sich um Prozess-Kill)
    if job.watcher_task and not job.watcher_task.done():
        job.watcher_task.cancel()
    elif job.process and job.process.returncode is None:
        # Watcher läuft nicht, direkt killen
        try:
            job.process.terminate()
            await asyncio.wait_for(job.process.wait(), timeout=5)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                job.process.kill()
            except ProcessLookupError:
                pass
    if active_jobs.get(job.user_id) is job:
        del active_jobs[job.user_id]

async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    job = active_jobs.get(update.effective_user.id)
    if not job:
        await update.message.reply_text("ℹ️ Kein aktiver Job.", parse_mode=ParseMode.HTML)
        return
    if not job.last_log_lines:
        await update.message.reply_text("ℹ️ Noch keine Logs.", parse_mode=ParseMode.HTML)
        return
    text = "<b>📋 Letzte Logs</b>\n\n"
    for line in job.last_log_lines[-30:]:
        text += f"<code>{html.escape(line[:200])}</code>\n"
    if len(text) > 4000:
        text = text[:3950] + "\n\n<i>... (gekürzt)</i>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)
    # Alten Job stoppen
    job = active_jobs.get(update.effective_user.id)
    if job:
        await stop_job(job, update, context)
    # Session zurücksetzen
    state.session_id = None
    state.continue_session = False
    delete_session(update.effective_user.id)
    clear_history(update.effective_user.id)
    save_user_state(update.effective_user.id, state)
    await update.message.reply_text("🆕 <b>Neue Session.</b> Kontext zurückgesetzt.", parse_mode=ParseMode.HTML)

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)
    state.continue_session = True
    if not state.session_id:
        saved = load_session(update.effective_user.id)
        if saved:
            state.session_id = saved
    save_user_state(update.effective_user.id, state)
    if not state.session_id:
        await update.message.reply_text("ℹ️ Keine vorherige Session vorhanden.", parse_mode=ParseMode.HTML)
        return
    text = f"🔄 <b>Session fortsetzen?</b>\n\nSession-ID: <code>{state.session_id[:8]}...</code>\n\nSchick einfach eine Nachricht, um fortzufahren."
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# Deutsche Aliase
cmd_neuein = cmd_new
cmd_reset = cmd_new
cmd_history_reset = cmd_new

async def cmd_cd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    if not context.args:
        await update.message.reply_text("ℹ️ Verwendung: <code>/cd /pfad/zum/projekt</code>", parse_mode=ParseMode.HTML)
        return
    new_dir = " ".join(context.args).strip()
    if not os.path.isabs(new_dir):
        new_dir = os.path.abspath(new_dir)
    if not os.path.isdir(new_dir):
        await update.message.reply_text(f"❌ Pfad existiert nicht: <code>{html.escape(new_dir)}</code>", parse_mode=ParseMode.HTML)
        return
    state = get_user_state(update.effective_user.id)
    state.working_dir = new_dir
    save_user_state(update.effective_user.id, state)
    await update.message.reply_text(f"📂 Working-Dir: <code>{html.escape(new_dir)}</code>", parse_mode=ParseMode.HTML)

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    if not context.args:
        state = get_user_state(update.effective_user.id)
        if state.add_dirs:
            text = "<b>📁 Freigegebene Verzeichnisse:</b>\n"
            for d in state.add_dirs:
                text += f"• <code>{html.escape(d)}</code>\n"
        else:
            text = "ℹ️ Keine zusätzlichen Verzeichnisse. Nutze <code>/add /pfad</code>."
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    new_dir = " ".join(context.args).strip()
    if not os.path.isabs(new_dir):
        new_dir = os.path.abspath(new_dir)
    if not os.path.isdir(new_dir):
        await update.message.reply_text(f"❌ Pfad existiert nicht: <code>{html.escape(new_dir)}</code>", parse_mode=ParseMode.HTML)
        return
    state = get_user_state(update.effective_user.id)
    if new_dir not in state.add_dirs:
        state.add_dirs.append(new_dir)
    save_user_state(update.effective_user.id, state)
    await update.message.reply_text(f"✅ Hinzugefügt: <code>{html.escape(new_dir)}</code>", parse_mode=ParseMode.HTML)

async def cmd_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)
    if not context.args:
        if state.system_prompt_append:
            await update.message.reply_text(
                f"<b>Aktueller System-Prompt:</b>\n<code>{html.escape(state.system_prompt_append)}</code>\n\n"
                f"Leeren mit <code>/system clear</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text("ℹ️ Kein System-Prompt gesetzt.", parse_mode=ParseMode.HTML)
        return
    if context.args[0] == "clear":
        state.system_prompt_append = ""
        save_user_state(update.effective_user.id, state)
        await update.message.reply_text("🗑️ System-Prompt gelöscht.", parse_mode=ParseMode.HTML)
        return
    state.system_prompt_append = " ".join(context.args)
    save_user_state(update.effective_user.id, state)
    await update.message.reply_text(
        f"✅ System-Prompt gesetzt: <code>{html.escape(state.system_prompt_append[:100])}</code>",
        parse_mode=ParseMode.HTML
    )

async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt Modellauswahl oder wechselt das Modell."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    # Prüfe auf Refresh-Argument
    if context.args and context.args[0].lower() == "refresh":
        from providers import save_cached_models
        save_cached_models(CURRENT_PROVIDER.name, [])
        await update.message.reply_text("🔄 Cache geleert. Modelle werden neu geladen...")
        # Lösche User-State um API-Neuladen zu forcieren
        state = get_user_state(update.effective_user.id)
        state.model = CURRENT_PROVIDER.model
        save_user_state(update.effective_user.id, state)
        return

    state = get_user_state(update.effective_user.id)
    # Modelle live vom Provider abrufen
    models = CURRENT_PROVIDER.get_model_list()

    if not context.args:
        # Zeige Modellauswahl als Buttons
        text = f"<b>📋 Modelle</b> (Provider: <code>{PROVIDER_NAME}</code>)\n\nAktuell: <b>{state.model}</b>\nWähle ein Modell:"
        keyboard = []
        for i in range(0, len(models), 2):
            row = []
            for model_id, label in models[i:i+2]:
                prefix = "✅ " if model_id == state.model else ""
                row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"model:{model_id}"))
            keyboard.append(row)
        # Refresh-Button hinzufügen
        keyboard.append([InlineKeyboardButton("🔄 Modelle neu laden", callback_data="models:refresh")])
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    new_model = context.args[0].lower()
    valid_ids = [m for m, _ in models]
    if new_model not in valid_ids:
        await update.message.reply_text(
            "❌ Unbekanntes Modell. Wähle aus der Liste (siehe /mlist).",
            parse_mode=ParseMode.HTML
        )
        return
    state.model = new_model
    save_user_state(update.effective_user.id, state)
    # Falls eine Session läuft, muss sie neu gestartet werden, damit das neue Modell greift
    if update.effective_user.id in active_jobs:
        await update.message.reply_text(
            f"✅ Modell: <b>{new_model}</b>\n⚠️ Aktiver Job wird mit dem neuen Modell neu gestartet…",
            parse_mode=ParseMode.HTML
        )
        await stop_job(active_jobs[update.effective_user.id], update, context)
        new_job = Job(update.effective_user.id, "[Modellwechsel – bitte wiederhole deine letzte Nachricht]", [], None)
        active_jobs[update.effective_user.id] = new_job
        new_job.watcher_task = asyncio.create_task(watch_job(new_job, update, context))
    else:
        await update.message.reply_text(f"✅ Modell: <b>{new_model}</b>", parse_mode=ParseMode.HTML)

# MODELS wird jetzt aus dem aktiven Provider geladen (siehe oben)
# Fallback-Liste falls Provider keine Modelle liefert
if not MODELS:
    MODELS = [("auto", "🌐 Auto")]

async def cmd_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wechselt den aktiven Provider zur Laufzeit (ohne Neustart)."""
    global PROVIDER_NAME, PROVIDERS, CURRENT_PROVIDER, MODELS
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)

    if not context.args:
        # Verfügbare Provider als Buttons anzeigen
        text = f"<b>📡 Provider</b>\n\nAktuell: <code>{PROVIDER_NAME}</code>\nWähle einen Provider:"
        keyboard = []
        names = list(PROVIDERS.keys())
        for i in range(0, len(names), 2):
            row = []
            for name in names[i:i+2]:
                prefix = "✅ " if name == PROVIDER_NAME else ""
                row.append(InlineKeyboardButton(f"{prefix}{name}", callback_data=f"provider:{name}"))
            keyboard.append(row)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    new_provider = context.args[0].lower()
    if new_provider not in PROVIDERS:
        await update.message.reply_text(
            f"❌ Unbekannter Provider <code>{new_provider}</code>.\n"
            f"Verfügbar: {', '.join(PROVIDERS.keys())}",
            parse_mode=ParseMode.HTML
        )
        return

    # Provider wechseln (alle globalen Variablen aktualisieren)
    PROVIDER_NAME = new_provider
    CURRENT_PROVIDER = PROVIDERS[new_provider]
    MODELS = CURRENT_PROVIDER.get_model_list()
    if not MODELS:
        MODELS = [("auto", "🌐 Auto")]
    state.model = CURRENT_PROVIDER.model or "auto"
    save_user_state(update.effective_user.id, state)
    logger.info(f"Provider gewechselt zu: {PROVIDER_NAME} (Modell: {state.model})")
    await update.message.reply_text(
        f"✅ <b>Provider gewechselt</b> zu <code>{PROVIDER_NAME}</code>\n"
        f"Standard-Modell: <b>{state.model}</b>\n"
        f"Verfügbare Modelle: /mlist",
        parse_mode=ParseMode.HTML
    )


async def cmd_modelliste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt die verfügbare Modelliste des aktuellen Providers an."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    try:
        state = get_user_state(update.effective_user.id)
        models = CURRENT_PROVIDER.get_model_list()

        if not models:
            await update.message.reply_text(
                "⚠️ <b>Keine Modelle gefunden</b>\n\n"
                f"Provider: <code>{PROVIDER_NAME}</code>\n"
                "Die API hat keine Modelle zurückgegeben.\n"
                "Verwende <code>/models refresh</code> um es erneut zu versuchen.",
                parse_mode=ParseMode.HTML
            )
            return

        text = f"<b>📋 Modelle</b> (Provider: <code>{PROVIDER_NAME}</code>)\n\nAktuell: <b>{state.model}</b>\nWähle ein Modell:"

        keyboard = []
        for i in range(0, len(models), 2):
            row = []
            for model_id, label in models[i:i+2]:
                prefix = "✅ " if model_id == state.model else ""
                row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"model:{model_id}"))
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("🔄 Modelle neu laden", callback_data="models:refresh")])

        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.exception(f"Fehler in cmd_modelliste: {e}")
        await update.message.reply_text(
            f"❌ <b>Fehler beim Laden der Modelle</b>\n\n{html.escape(str(e))}",
            parse_mode=ParseMode.HTML
        )


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias für /models - zeigt Modelle mit Option zum Refresh."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    # Refresh-Argument
    if context.args and context.args[0].lower() == "refresh":
        from providers import save_cached_models
        try:
            save_cached_models(CURRENT_PROVIDER.name, [])
            state = get_user_state(update.effective_user.id)
            state.model = CURRENT_PROVIDER.model
            save_user_state(update.effective_user.id, state)
        except Exception:
            pass

    # Rufe die normale Modelliste auf
    await cmd_modelliste(update, context)

# Permission-Modi
async def _set_mode(update: Update, mode: str):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)
    state.permission_mode = mode
    save_user_state(update.effective_user.id, state)
    label = PERMISSION_MODE_LABELS.get(mode, mode)
    await update.message.reply_text(f"✅ <b>Permission-Mode:</b> {html.escape(label)}", parse_mode=ParseMode.HTML)

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_mode(update, "plan")

async def cmd_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_mode(update, "auto")

async def cmd_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_mode(update, "acceptEdits")

async def cmd_bypass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_mode(update, "bypassPermissions")

async def cmd_default(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_mode(update, "default")

async def cmd_dontask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_mode(update, "dontAsk")

async def cmd_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt alle aktiven Tool-Permissions (erlaubt/verboten)."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)

    # Reset auf Defaults
    if context.args and context.args[0] == "reset":
        state.allowed_tools = list(DEFAULT_ALLOWED_TOOLS)
        state.disallowed_tools = []
        save_user_state(update.effective_user.id, state)
        await update.message.reply_text(
            "🔄 <b>Permissions auf Defaults zurückgesetzt</b>",
            parse_mode=ParseMode.HTML
        )
        return

    text = "<b>🔐 Tool-Permissions</b>\n\n"
    text += f"<b>Erlaubt ({len(state.allowed_tools)}):</b>\n"
    if state.allowed_tools:
        for t in state.allowed_tools:
            text += f"  ✅ <code>{html.escape(t)}</code>\n"
    else:
        text += "  <i>(keine)</i>\n"

    text += f"\n<b>Verboten ({len(state.disallowed_tools)}):</b>\n"
    if state.disallowed_tools:
        for t in state.disallowed_tools:
            text += f"  ❌ <code>{html.escape(t)}</code>\n"
    else:
        text += "  <i>(keine)</i>\n"

    text += f"\n<b>Tools-Set:</b> <code>{state.tools}</code>\n"
    text += f"\n<i>Defaults zurücksetzen mit</i> <code>/permissions reset</code>\n"
    text += f"<i>Erlauben: <code>/tools allow Bash(git *)</code></i>\n"
    text += f"<i>Verbieten: <code>/tools deny Bash(rm *)</code></i>"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)
    text = "<b>🛠️ Tool-Konfiguration</b>\n\n"
    text += f"<b>Tools-Set:</b> <code>{state.tools}</code>\n"
    if state.allowed_tools:
        text += f"<b>Erlaubt:</b> {', '.join(f'<code>{t}</code>' for t in state.allowed_tools)}\n"
    if state.disallowed_tools:
        text += f"<b>Verboten:</b> {', '.join(f'<code>{t}</code>' for t in state.disallowed_tools)}\n"
    text += "\n<i>Setzen mit /tools set &lt;liste&gt; (z.B. <code>/tools set Read,Edit</code>)</i>\n"
    text += "<i>Erlauben: <code>/tools allow Bash(git *)</code></i>\n"
    text += "<i>Verbieten: <code>/tools deny Bash(rm *)</code></i>"
    if not context.args:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    if context.args[0] == "set" and len(context.args) > 1:
        state.tools = ",".join(context.args[1:])
        save_user_state(update.effective_user.id, state)
        await update.message.reply_text(f"✅ Tools-Set: <code>{state.tools}</code>", parse_mode=ParseMode.HTML)
    elif context.args[0] == "allow" and len(context.args) > 1:
        tool = " ".join(context.args[1:])
        if tool not in state.allowed_tools:
            state.allowed_tools.append(tool)
        save_user_state(update.effective_user.id, state)
        await update.message.reply_text(f"✅ Erlaubt: <code>{tool}</code>", parse_mode=ParseMode.HTML)
    elif context.args[0] == "deny" and len(context.args) > 1:
        tool = " ".join(context.args[1:])
        if tool not in state.disallowed_tools:
            state.disallowed_tools.append(tool)
        save_user_state(update.effective_user.id, state)
        await update.message.reply_text(f"🚫 Verboten: <code>{tool}</code>", parse_mode=ParseMode.HTML)

async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    state = get_user_state(update.effective_user.id)
    text = "<b>⚙️ Konfiguration</b>\n\n"
    text += f"• <b>Permission-Mode:</b> {state.permission_mode}\n"
    text += f"• <b>Modell:</b> {state.model}\n"
    text += f"• <b>Working-Dir:</b> <code>{html.escape(state.working_dir)}</code>\n"
    text += f"• <b>Tools:</b> <code>{state.tools}</code>\n"
    text += f"• <b>Allowed:</b> {len(state.allowed_tools)} Tools\n"
    text += f"• <b>Disallowed:</b> {len(state.disallowed_tools)} Tools\n"
    text += f"• <b>Add-Dirs:</b> {len(state.add_dirs)}\n"
    text += f"• <b>Worktree:</b> {'✅' if state.worktree else '❌'}\n"
    text += f"• <b>Safe-Mode:</b> {'✅' if state.safe_mode else '❌'}\n"
    text += f"• <b>Session:</b> <code>{state.session_id[:8] + '...' if state.session_id else 'keine'}</code>\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_doctor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "doctor",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            timeout=30,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = (stdout or stderr).decode(errors="replace")
        if len(output) > 3500:
            output = output[:3450] + "\n\n... (gekürzt)"
        await update.message.reply_text(f"<b>🩺 Claude Doctor</b>\n\n<pre>{html.escape(output)}</pre>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Doctor fehlgeschlagen: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

# --- Datei-Manipulation-Befehle ---
async def cmd_read(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liest eine Datei und zeigt den Inhalt."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    if not context.args:
        await update.message.reply_text("ℹ️ Verwendung: <code>/read /pfad/zur/datei</code>", parse_mode=ParseMode.HTML)
        return
    filepath = " ".join(context.args).strip()
    if not os.path.isabs(filepath):
        state = get_user_state(update.effective_user.id)
        filepath = os.path.join(state.working_dir, filepath)
    if not os.path.isfile(filepath):
        await update.message.reply_text(f"❌ Datei nicht gefunden: <code>{html.escape(filepath)}</code>", parse_mode=ParseMode.HTML)
        return
    try:
        content = Path(filepath).read_text(encoding="utf-8")
        if len(content) > 3500:
            content = content[:3450] + "\n\n... (gekürzt)"
        await update.message.reply_text(
            f"<b>📄 {html.escape(filepath)}</b>\n\n<pre>{html.escape(content)}</pre>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler beim Lesen: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)

async def cmd_write(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Schreibt Inhalt in eine Datei."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "ℹ️ Verwendung: <code>/write /pfad/zur/datei &lt;inhalt&gt;</code>\n"
            "Tipp: Bei langem Inhalt erst <code>/read</code> prüfen, dann in mehreren Nachrichten schreiben.",
            parse_mode=ParseMode.HTML
        )
        return
    filepath = context.args[0].strip()
    content = " ".join(context.args[1:])
    if not os.path.isabs(filepath):
        state = get_user_state(update.effective_user.id)
        filepath = os.path.join(state.working_dir, filepath)
    try:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        Path(filepath).write_text(content, encoding="utf-8")
        await update.message.reply_text(
            f"✅ <b>geschrieben:</b> <code>{html.escape(filepath)}</code>\n"
            f"<i>{len(content)} Zeichen</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler beim Schreiben: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)

async def cmd_ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liste Dateien in einem Verzeichnis."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    path = context.args[0] if context.args else "."
    if not os.path.isabs(path):
        state = get_user_state(update.effective_user.id)
        path = os.path.join(state.working_dir, path)
    if not os.path.isdir(path):
        await update.message.reply_text(f"❌ Verzeichnis nicht gefunden: <code>{html.escape(path)}</code>", parse_mode=ParseMode.HTML)
        return
    try:
        entries = sorted(os.listdir(path))
        dirs = [d + "/" for d in entries if os.path.isdir(os.path.join(path, d))]
        files = [f for f in entries if os.path.isfile(os.path.join(path, f))]
        lines = ["📁 " + html.escape(path), ""]
        for d in dirs:
            lines.append(f"  📂 {html.escape(d)}")
        for f in files:
            size = os.path.getsize(os.path.join(path, f))
            lines.append(f"  📄 {html.escape(f)} ({size} bytes)")
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3950] + "\n\n... (gekürzt)"
        await update.message.reply_text(f"<pre>{text}</pre>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)

async def cmd_grep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Durchsucht Dateien nach einem Pattern."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    if not context.args:
        await update.message.reply_text("ℹ️ Verwendung: <code>/grep pattern [pfad]</code>", parse_mode=ParseMode.HTML)
        return
    pattern = context.args[0]
    path = context.args[1] if len(context.args) > 1 else "."
    if not os.path.isabs(path):
        state = get_user_state(update.effective_user.id)
        path = os.path.join(state.working_dir, path)
    try:
        matches = []
        for root, dirs, files in os.walk(path):
            for fname in files:
                fpath = os.path.join(root, fname)
                if any(fpath.endswith(ext) for ext in [".py", ".md", ".txt", ".json", ".sh", ".yaml", ".yml", ".toml"]):
                    try:
                        content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                        for i, line in enumerate(content.splitlines(), 1):
                            if pattern.lower() in line.lower():
                                matches.append(f"{fpath}:{i}: {line.rstrip()}")
                    except:
                        pass
        if not matches:
            await update.message.reply_text(f"🔍 Keine Treffer für <code>{html.escape(pattern)}</code>", parse_mode=ParseMode.HTML)
            return
        text = f"<b>🔍 Treffer für '{html.escape(pattern)}'</b>\n\n"
        text += "\n".join(f"<code>{html.escape(m[:200])}</code>" for m in matches[:30])
        if len(matches) > 30:
            text += f"\n\n<i>... und {len(matches) - 30} weitere Treffer</i>"
        if len(text) > 4000:
            text = text[:3950] + "\n\n... (gekürzt)"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt die letzte Conversation-History."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    limit = int(context.args[0]) if context.args and context.args[0].isdigit() else 10
    limit = min(limit, 50)
    entries = load_history(update.effective_user.id, limit)
    if not entries:
        await update.message.reply_text("📭 Keine History vorhanden.", parse_mode=ParseMode.HTML)
        return
    text = f"<b>📜 History (letzte {len(entries)} Einträge)</b>\n\n"
    for e in entries:
        role = "👤" if e["role"] == "user" else "🤖"
        ts = e.get("timestamp", "")[:16]
        content = e.get("content", "")[:300]
        text += f"{role} <code>{ts}</code>\n{html.escape(content)}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt vergangene Jobs und deren Status."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    jobs = list_job_logs(update.effective_user.id)
    if not jobs:
        await update.message.reply_text("📭 Keine vergangenen Jobs.", parse_mode=ParseMode.HTML)
        return
    text = f"<b>📋 Letzte {min(len(jobs), 20)} Jobs</b>\n\n"
    for j in jobs[-20:]:
        status = j.get("status", "?")
        ts = j.get("finished_at", "")[:16]
        output = (j.get("output") or "")[:100]
        text += f"• <b>{status}</b> · <code>{ts}</code>\n  {html.escape(output)}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Führt einen Bash-Befehl aus."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    if not context.args:
        await update.message.reply_text("ℹ️ Verwendung: <code>/exec befehl</code>", parse_mode=ParseMode.HTML)
        return
    cmd_str = " ".join(context.args)
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", cmd_str,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=get_user_state(update.effective_user.id).working_dir,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = (stdout or stderr).decode(errors="replace")
        if len(output) > 3500:
            output = output[:3450] + "\n\n... (gekürzt)"
        if not output.strip():
            output = "(keine Ausgabe)"
        await update.message.reply_text(
            f"<b>💻 $ {html.escape(cmd_str)}</b>\n\n<pre>{html.escape(output)}</pre>",
            parse_mode=ParseMode.HTML
        )
    except asyncio.TimeoutError:
        await update.message.reply_text("⏱️ Timeout nach 30s", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)

# --- Haupt-Nachrichten-Handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    user_id = update.effective_user.id
    state = get_user_state(user_id)

    # Wenn aktiver Job läuft, warnen
    if user_id in active_jobs:
        job = active_jobs[user_id]
        await update.message.reply_text(
            f"⚠️ Es läuft bereits ein Job. Stoppe ihn erst mit /stop oder warte.\n"
            f"Aktueller Status: {job.status}",
            parse_mode=ParseMode.HTML
        )
        return

    # Status-Nachricht
    status_msg = await update.message.reply_text(
        f"🚀 <b>Starte Job...</b>\n\n<i>Modus: {state.permission_mode} · Modell: {state.model}</i>",
        parse_mode=ParseMode.HTML
    )

    # Job erstellen
    prompt = update.message.text
    job = Job(user_id, prompt, [], status_msg.message_id)
    active_jobs[user_id] = job

    # Prüfe ob Session fortgesetzt werden soll
    saved_session = load_session(user_id)
    if saved_session and state.continue_session:
        # Setze Session-ID aus Memory, damit --resume genutzt wird
        state.session_id = saved_session
    elif not state.continue_session:
        # /new wurde aufgerufen - keine alte Session
        state.session_id = None

    # Falls keine Session fortgesetzt wird, baue Kontext aus History
    if not state.session_id:
        ctx = build_context_from_history(user_id, max_entries=10, max_chars=4000)
        if ctx:
            # Voranstellen des Kontexts mit klarer Markierung
            prompt = f"[Bisheriger Kontext dieser Konversation]\n\n{ctx}\n\n[Neue Nachricht]\n{prompt}"

    # Prompt sofort in History speichern (Backup falls Job crasht)
    add_history_entry(user_id, "user", prompt, job.id)

    # Starten
    success, err = await start_claude_job(job, state)
    if not success:
        job.status = "failed"
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"❌ <b>Fehler beim Start:</b>\n<code>{html.escape(err)}</code>",
            parse_mode=ParseMode.HTML
        )
        del active_jobs[user_id]
        return

    # Watcher starten
    job.watcher_task = asyncio.create_task(watch_job(job, update, context))

# --- Callback-Handler (Buttons) ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PROVIDER_NAME, PROVIDERS, CURRENT_PROVIDER, MODELS
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    user_id = update.effective_user.id
    logger.warning(f"🔔 CB empfangen: data={data!r}, user_id={user_id}, ALLOWED={ALLOWED_USER_ID}")
    if user_id != ALLOWED_USER_ID:
        await query.answer("Nicht erlaubt")
        return
    await query.answer()

    # Copy-Button: leerer data = automatisch von Telegram gehandhabt
    if not data:
        return

    # Action-Buttons
    if ":" not in data:
        return
    action, value = data.split(":", 1)

    state = get_user_state(user_id)
    job = active_jobs.get(user_id)

    if action == "stop":
        if job:
            await stop_job(job, update, context)
            await query.answer("🛑 Job gestoppt")
            try:
                await query.edit_message_text("🛑 <b>Job gestoppt</b>", parse_mode=ParseMode.HTML)
            except Exception:
                pass
        else:
            await query.answer("ℹ️ Kein aktiver Job", show_alert=True)
    elif action == "refresh":
        if job:
            await update_telegram_message(job, update, context)
            await query.answer("🔄 Aktualisiert")
        else:
            await query.answer("ℹ️ Kein aktiver Job", show_alert=True)
    elif action == "models" and value == "refresh":
        # Modelle neu laden - Cache löschen und neue Liste senden
        from providers import save_cached_models
        try:
            save_cached_models(CURRENT_PROVIDER.name, [])
            state = get_user_state(user_id)
            state.model = CURRENT_PROVIDER.model
            save_user_state(user_id, state)
        except Exception:
            pass

        # Neue Liste abrufen
        models = CURRENT_PROVIDER.get_model_list()

        if models:
            text = f"<b>📋 Modelle</b> (Provider: <code>{PROVIDER_NAME}</code>)\n\nAktuell: <b>{state.model}</b>\nWähle ein Modell:"
            keyboard = []
            for i in range(0, len(models), 2):
                row = []
                for model_id, label in models[i:i+2]:
                    prefix = "✅ " if model_id == state.model else ""
                    row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"model:{model_id}"))
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("🔄 Modelle neu laden", callback_data="models:refresh")])
        else:
            text = f"<b>📋 Modelle</b> (Provider: <code>{PROVIDER_NAME}</code>)\n\n⚠️ Keine Modelle vom Provider erhalten."
            keyboard = [[InlineKeyboardButton("🔄 Erneut versuchen", callback_data="models:refresh")]]

        # Nachricht senden (nicht editieren, um "not modified" Fehler zu vermeiden)
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.answer("🔄 Modelle neu geladen")
    elif action == "new":
        state = get_user_state(user_id)
        if job:
            await stop_job(job, update, context)
        state.session_id = None
        await query.answer("🆕 Neue Session")
    elif action == "logs" and job:
        # Logs in Chat senden
        text = "<b>📋 Logs</b>\n\n"
        for line in job.last_log_lines[-30:]:
            text += f"<code>{html.escape(line[:200])}</code>\n"
        if len(text) > 4000:
            text = text[:3950] + "\n\n<i>... (gekürzt)</i>"
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML)
    elif data.startswith("model:"):
        new_model = data.split(":", 1)[1]
        state = get_user_state(user_id)
        models = CURRENT_PROVIDER.get_model_list()
        if any(m == new_model for m, _ in models):
            state.model = new_model
            save_user_state(user_id, state)
            await query.answer(f"✅ Modell: {new_model}")
            # Liste neu anzeigen mit aktualisiertem Haken
            text = f"<b>📋 Modelle</b>\n\nAktuell: <b>{new_model}</b>\nWähle ein Modell:"
            keyboard = []
            for i in range(0, len(models), 2):
                row = []
                for model_id, label in models[i:i+2]:
                    prefix = "✅ " if model_id == new_model else ""
                    row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"model:{model_id}"))
                keyboard.append(row)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                logger.warning(f"Model-Button Edit-Fehler: {e}")
                # Fallback: neue Nachricht, damit du das Ergebnis siehst
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Modell gewechselt zu <b>{new_model}</b>\n(Original-Nachricht konnte nicht aktualisiert werden)",
                    parse_mode=ParseMode.HTML
                )
    elif data.startswith("provider:"):
        # Provider-Wechsel per Button
        new_provider = data.split(":", 1)[1]
        if new_provider in PROVIDERS:
            PROVIDER_NAME = new_provider
            CURRENT_PROVIDER = PROVIDERS[new_provider]
            MODELS = CURRENT_PROVIDER.get_model_list()
            if not MODELS:
                MODELS = [("auto", "🌐 Auto")]
            state.model = CURRENT_PROVIDER.model or "auto"
            save_user_state(user_id, state)
            await query.answer(f"✅ Provider: {new_provider}")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Provider gewechselt zu <code>{new_provider}</code>\nModell: <b>{state.model}</b>",
                parse_mode=ParseMode.HTML
            )
    elif data.startswith("lang:"):
        # Sprach-Umschalter
        new_lang = data.split(":", 1)[1]
        if new_lang in ("de", "en"):
            state.language = new_lang
            save_user_state(user_id, state)
            await query.answer("✅")
            # Willkommen in neuer Sprache anzeigen
            cwd_escaped = state.working_dir.replace("\\", "\\\\").replace(".", "\\.").replace("-", "\\-")
            model_escaped = state.model.replace("\\", "\\\\").replace(".", "\\.").replace("-", "\\-")
            mode_raw = PERMISSION_MODE_LABELS.get(state.permission_mode, state.permission_mode)
            mode_escaped = mode_raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace(".", "\\.")
            text = _("welcome", new_lang,
                     model=model_escaped,
                     mode=mode_escaped,
                     cwd=cwd_escaped,
                     lang_label=LANG_NAMES.get(new_lang, new_lang))
            keyboard = [
                [
                    InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang:de"),
                    InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
                ]
            ]
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                logger.warning(f"Lang-Button Edit-Fehler: {e}")
                text_html = re_module.sub(r"\*([^*]+)\*", r"<b>\1</b>", text.replace("\\", ""))
                text_html = re_module.sub(r"_([^_]+)_", r"<i>\1</i>", text_html)
                await context.bot.send_message(chat_id=user_id, text=text_html, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    elif action in ("perm_allow", "perm_deny", "perm_always") and job and job.pending_permission:
        # Tool-Freigabe
        perm = job.pending_permission
        if action == "perm_allow":
            job.last_log_lines.append(f"✅ Erlaubt: {perm['tool_name']}")
            job.pending_permission = None
        elif action == "perm_deny":
            job.last_log_lines.append(f"❌ Abgelehnt: {perm['tool_name']}")
            # Stoppe den Job
            await stop_job(job, update, context)
            job.pending_permission = None
        elif action == "perm_always":
            tool = perm["tool_name"]
            # Pattern: Tool + erstes Wort des Inputs (z.B. Bash(python3 *))
            tool_input = perm.get("tool_input", {})
            pattern = tool
            if tool_input and isinstance(tool_input, dict):
                cmd = tool_input.get("command") or tool_input.get("cmd")
                if cmd:
                    first = str(cmd).split()[0] if cmd else ""
                    if first:
                        pattern = f"{tool}({first} *)"
            if pattern not in state.allowed_tools:
                state.allowed_tools.append(pattern)
            save_user_state(user_id, state)
            job.last_log_lines.append(f"✅ Immer erlaubt: {pattern}")
            job.pending_permission = None
        await update_telegram_message(job, update, context)

# --- Main ---
def main():
    if not TELEGRAM_TOKEN:
        print("FEHLER: TELEGRAM_TOKEN nicht in .env gesetzt!")
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_menu))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("neuein", cmd_new))
    app.add_handler(CommandHandler("reset", cmd_new))
    app.add_handler(CommandHandler("vergiess", cmd_new))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("cd", cmd_cd))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("system", cmd_system))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("provider", cmd_provider))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("auto", cmd_auto))
    app.add_handler(CommandHandler("accept", cmd_accept))
    app.add_handler(CommandHandler("bypass", cmd_bypass))
    app.add_handler(CommandHandler("default", cmd_default))
    app.add_handler(CommandHandler("dontask", cmd_dontask))
    app.add_handler(CommandHandler("tools", cmd_tools))
    app.add_handler(CommandHandler("permissions", cmd_permissions))
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CommandHandler("lang", cmd_language))
    app.add_handler(CommandHandler("sprache", cmd_language))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("models", cmd_models))
    app.add_handler(CommandHandler("mlist", cmd_modelliste))
    app.add_handler(CommandHandler("modelle", cmd_modelliste))
    # Neue Befehle
    app.add_handler(CommandHandler("read", cmd_read))
    app.add_handler(CommandHandler("write", cmd_write))
    app.add_handler(CommandHandler("ls", cmd_ls))
    app.add_handler(CommandHandler("grep", cmd_grep))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
    app.add_handler(CommandHandler("exec", cmd_exec))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("🤖 Claude Code Bot gestartet (Background-Modus + Live-Streaming)")
    app.run_polling(poll_interval=0.5, timeout=30, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
