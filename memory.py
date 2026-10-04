"""Persistentes Memory-System für den Telegram-Bot.

Speichert UserState, Session-IDs, Conversation-History und Job-Logs
in JSON-Dateien unter ./data/. Überlebt Neustarts des Bots.
"""
import json
import os
import logging
from pathlib import Path
from datetime import datetime

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from bot import UserState, Job

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
USERSTATES_FILE = DATA_DIR / "userstates.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
HISTORY_FILE = DATA_DIR / "history.json"

# --- Initialisierung ---
def init_memory():
    """Erstellt data-Verzeichnis und Dateien falls nicht vorhanden."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f in (USERSTATES_FILE, SESSIONS_FILE, HISTORY_FILE):
        if not f.exists():
            f.write_text("{}", encoding="utf-8")

def _load(path: Path) -> dict:
    """Lädt JSON-Datei, gibt leeres Dict zurück bei Fehler."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save(path: Path, data: dict):
    """Speichert Dict als JSON-Datei."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# --- UserStates persistent ---
def save_user_state(user_id: int, state):
    """Speichert alle Einstellungen eines Users."""
    init_memory()
    data = _load(USERSTATES_FILE)
    data[str(user_id)] = {
        "permission_mode": state.permission_mode,
        "model": state.model,
        "system_prompt_append": state.system_prompt_append,
        "working_dir": state.working_dir,
        "add_dirs": state.add_dirs,
        "allowed_tools": state.allowed_tools,
        "disallowed_tools": state.disallowed_tools,
        "tools": state.tools,
        "session_id": state.session_id,
        "continue_session": state.continue_session,
        "worktree": state.worktree,
        "safe_mode": state.safe_mode,
        "language": getattr(state, "language", "de"),
        "updated_at": datetime.utcnow().isoformat(),
    }
    _save(USERSTATES_FILE, data)

def load_user_state(user_id: int) -> dict | None:
    """Lädt gespeicherte UserState-Daten. Gibt None zurück wenn nicht vorhanden."""
    init_memory()
    data = _load(USERSTATES_FILE)
    return data.get(str(user_id))

def list_user_states() -> dict:
    """Gibt alle gespeicherten UserStates zurück."""
    init_memory()
    return _load(USERSTATES_FILE)

# --- Sessions persistent ---
def save_session(user_id: int, session_id: str):
    """Speichert eine Claude-Session-ID für einen User."""
    init_memory()
    data = _load(SESSIONS_FILE)
    data[str(user_id)] = {
        "session_id": session_id,
        "updated_at": datetime.utcnow().isoformat(),
    }
    _save(SESSIONS_FILE, data)

def load_session(user_id: int) -> str | None:
    """Lädt gespeicherte Session-ID."""
    init_memory()
    data = _load(SESSIONS_FILE)
    entry = data.get(str(user_id))
    return entry.get("session_id") if entry else None

def delete_session(user_id: int):
    """Entfernt gespeicherte Session."""
    init_memory()
    data = _load(SESSIONS_FILE)
    data.pop(str(user_id), None)
    _save(SESSIONS_FILE, data)

# --- Conversation-History ---
def add_history_entry(user_id: int, role: str, content: str, job_id: str | None = None):
    """Fügt einen Eintrag zur Conversation-History hinzu."""
    init_memory()
    data = _load(HISTORY_FILE)
    key = str(user_id)
    if key not in data:
        data[key] = {"entries": []}

    entry = {
        "role": role,  # "user" oder "assistant"
        "content": content[:5000],  # Länger speichern für Kontext
        "job_id": job_id,
        "timestamp": datetime.utcnow().isoformat(),
    }
    data[key]["entries"].append(entry)

    # Behalte die letzten 500 Einträge pro User (~volle Konversation)
    if len(data[key]["entries"]) > 500:
        data[key]["entries"] = data[key]["entries"][-500:]

    _save(HISTORY_FILE, data)

def load_history(user_id: int, limit: int = 20) -> list:
    """Lädt die letzten N Konversations-Einträge."""
    init_memory()
    data = _load(HISTORY_FILE)
    entries = data.get(str(user_id), {}).get("entries", [])
    return entries[-limit:]

def build_context_from_history(user_id: int, max_entries: int = 20, max_chars: int = 8000) -> str:
    """Baut einen Kontext-String aus der History (für neue Jobs)."""
    entries = load_history(user_id, max_entries)
    if not entries:
        return ""
    lines = []
    total = 0
    # Neueste zuerst sammeln, dann umkehren für chronologische Reihenfolge
    for e in reversed(entries):
        role = "User" if e["role"] == "user" else "Assistant"
        content = e.get("content", "")[:1500]
        line = f"{role}: {content}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)
    lines.reverse()
    return "\n\n".join(lines)

def clear_history(user_id: int):
    """Löscht die gesamte Conversation-History eines Users."""
    init_memory()
    data = _load(HISTORY_FILE)
    data.pop(str(user_id), None)
    _save(HISTORY_FILE, data)

# --- Job-Logs ---
def save_job_log(user_id: int, job_id: str, status: str, output: str | None = None):
    """Speichert Job-Ergebnisse für späteres Nachschlagen."""
    init_memory()
    data = _load(DATA_DIR / "jobs.json") if (DATA_DIR / "jobs.json").exists() else {}
    key = str(user_id)
    if key not in data:
        data[key] = {}

    data[key][job_id] = {
        "status": status,
        "output": (output or "")[:5000] if output else None,
        "finished_at": datetime.utcnow().isoformat(),
    }
    _save(DATA_DIR / "jobs.json", data)

def load_job_log(user_id: int, job_id: str) -> dict | None:
    """Lädt gespeicherten Job-Log."""
    init_memory()
    data = _load(DATA_DIR / "jobs.json") if (DATA_DIR / "jobs.json").exists() else {}
    user_jobs = data.get(str(user_id), {})
    return user_jobs.get(job_id)

def list_job_logs(user_id: int) -> list:
    """Listet alle Job-Logs eines Users."""
    init_memory()
    data = _load(DATA_DIR / "jobs.json") if (DATA_DIR / "jobs.json").exists() else {}
    user_jobs = data.get(str(user_id), {})
    return [
        {"job_id": jid, **info}
        for jid, info in user_jobs.items()
    ]