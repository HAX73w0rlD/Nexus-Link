"""Modell-Verwaltung und Kategorisierung für Nexus-Link.

Unterstützt Kategorisierung nach Fähigkeiten (Text, Code, Bilder, Videos, Audio),
Steuerungs- bzw. Ansprechmethode (Claude Code CLI vs Open Code / Direct API)
und Status-Management (funktionsfähig, defekt, ausgeblendet).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Kategorien & Emojis ---
CATEGORY_EMOJIS = {
    "text": "💬",
    "code": "💻",
    "image": "🎨",
    "video": "🎬",
    "audio": "🎙️",
    "embed": "🧬",
    "all": "🌐",
}

CATEGORY_NAMES = {
    "de": {
        "all": "Alle Modelle",
        "text": "Text & Wissen",
        "code": "Code & Programmiersprachen",
        "image": "Bildgenerierung",
        "video": "Videogenerierung",
        "audio": "Audio & Sprache",
        "embed": "Embeddings",
    },
    "en": {
        "all": "All Models",
        "text": "Text & Knowledge",
        "code": "Code & Programming",
        "image": "Image Generation",
        "video": "Video Generation",
        "audio": "Audio & Speech",
        "embed": "Embeddings",
    },
}

INVOCATION_TYPES = {
    "claude_code": {"name": "Claude Code CLI", "emoji": "🤖"},
    "opencode": {"name": "Open Code / API", "emoji": "⚡"},
    "direct_api": {"name": "Direct API", "emoji": "🌐"},
}

MODEL_STATUS_FILE = Path("data/model_status.json")


class ModelInfo:
    """Repräsentiert ein Modell mit seinen Metadaten, Fähigkeiten und Status."""

    def __init__(
        self,
        model_id: str,
        label: str | None = None,
        categories: list[str] | None = None,
        invocation_type: str | None = None,
        provider_name: str = "",
        description: str = "",
        status: str = "unknown",  # "working", "non_working", "unknown", "hidden"
        error_message: str | None = None,
        last_checked: str | None = None,
    ):
        self.id = model_id
        self.label = label or model_id
        self.provider_name = provider_name
        self.description = description
        self.status = status
        self.error_message = error_message
        self.last_checked = last_checked

        # Automatische Ermittlung von Kategorien wenn nicht angegeben
        self.categories = categories or detect_categories(model_id, label)
        # Automatische Ermittlung der Ansprechmethode wenn nicht angegeben
        self.invocation_type = invocation_type or detect_invocation_type(model_id)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "categories": self.categories,
            "invocation_type": self.invocation_type,
            "provider_name": self.provider_name,
            "description": self.description,
            "status": self.status,
            "error_message": self.error_message,
            "last_checked": self.last_checked,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelInfo":
        return cls(
            model_id=data.get("id", ""),
            label=data.get("label"),
            categories=data.get("categories"),
            invocation_type=data.get("invocation_type"),
            provider_name=data.get("provider_name", ""),
            description=data.get("description", ""),
            status=data.get("status", "unknown"),
            error_message=data.get("error_message"),
            last_checked=data.get("last_checked"),
        )

    def get_category_emojis(self) -> str:
        """Liefert eine Zeichenkette von Emojis für die Kategorien des Modells."""
        emojis = [CATEGORY_EMOJIS.get(cat, "❓") for cat in self.categories]
        return " ".join(emojis)

    def get_invocation_emoji(self) -> str:
        """Liefert das Emoji für die Ansprechmethode."""
        info = INVOCATION_TYPES.get(self.invocation_type, {})
        return info.get("emoji", "⚙️")


# --- Heuristiken für automatische Erkennung ---

def detect_categories(model_id: str, label: str | None = None) -> list[str]:
    """Erkennt Fähigkeiten/Kategorien anhand von Modell-ID und Name."""
    text_lower = f"{model_id} {label or ''}".lower()
    categories = set()

    # Bildgenerierung / Vision
    if any(k in text_lower for k in [
        "dall-e", "midjourney", "flux", "stable-diffusion", "sdxl",
        "imagen", "image", "vision", "picture", "draw", "recraft"
    ]):
        categories.add("image")

    # Videogenerierung
    if any(k in text_lower for k in [
        "sora", "runway", "pika", "video", "luma", "cogvideo",
        "hunyuan-video", "svd", "anim"
    ]):
        categories.add("video")

    # Audio / Sprache
    if any(k in text_lower for k in [
        "whisper", "tts", "audio", "speech", "voice", "music", "bark", "suno"
    ]):
        categories.add("audio")

    # Embeddings
    if any(k in text_lower for k in ["embed", "embedding", "vector", "ada-002"]):
        categories.add("embed")

    # Code / Programmiersprachen
    if any(k in text_lower for k in [
        "code", "coder", "dev", "deepseek-coder", "qwen-coder", "codellama",
        "starcoder", "claude", "gpt-4", "sonnet", "opus", "o1", "o3", "deepseek"
    ]):
        categories.add("code")

    # Standard / Text & Wissen
    # Alle Modelle, die keine rein visuellen/audio-spezifischen sind oder allgemeine LLMs
    if not categories or any(k in text_lower for k in [
        "gpt", "claude", "llama", "mistral", "qwen", "gemini", "text", "chat",
        "deepseek", "gemma", "command", "auto", "phi"
    ]):
        categories.add("text")

    return sorted(list(categories))


def detect_invocation_type(model_id: str) -> str:
    """Bestimmt, wie das Modell angesprochen werden soll (Claude Code vs Open Code)."""
    mid_lower = model_id.lower()

    # Claude Code CLI (Anthropic / Sonnet / Opus / Haiku)
    if "claude" in mid_lower or "anthropic" in mid_lower or mid_lower.startswith("auto"):
        return "claude_code"

    # Sonst Open Code / Direct API
    return "opencode"


# --- Persistentes Status-Management ---

def load_model_statuses() -> dict[str, dict]:
    """Lädt gespeicherte Modell-Statusdaten (funktionsfähig / defekt / hidden)."""
    if not MODEL_STATUS_FILE.exists():
        return {}
    try:
        with open(MODEL_STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Fehler beim Laden von model_status.json: {e}")
        return {}


def save_model_statuses(statuses: dict[str, dict]):
    """Speichert Modell-Statusdaten."""
    try:
        MODEL_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MODEL_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(statuses, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Fehler beim Speichern von model_status.json: {e}")


def update_model_status(
    model_id: str,
    status: str,
    error_message: str | None = None,
    hide_if_failed: bool = False
):
    """Aktualisiert den Status eines einzelnen Modells."""
    from datetime import datetime
    statuses = load_model_statuses()
    now_str = datetime.utcnow().isoformat()

    entry = statuses.get(model_id, {})
    entry["status"] = status
    entry["last_checked"] = now_str
    if error_message:
        entry["error_message"] = error_message
    elif status == "working":
        entry["error_message"] = None

    if hide_if_failed and status == "non_working":
        entry["status"] = "hidden"

    statuses[model_id] = entry
    save_model_statuses(statuses)


def hide_non_working_models(model_ids: list[str]) -> int:
    """Setzt alle als 'non_working' erkannten Modelle auf 'hidden'.

    Gibt die Anzahl der ausgeblendeten Modelle zurück.
    """
    statuses = load_model_statuses()
    count = 0
    for mid in model_ids:
        entry = statuses.get(mid, {})
        if entry.get("status") == "non_working":
            entry["status"] = "hidden"
            statuses[mid] = entry
            count += 1
    if count > 0:
        save_model_statuses(statuses)
    return count


def unhide_all_models() -> int:
    """Setzt alle 'hidden' Modelle zurück auf 'unknown' / 'non_working'."""
    statuses = load_model_statuses()
    count = 0
    for mid, entry in statuses.items():
        if entry.get("status") == "hidden":
            entry["status"] = "unknown"
            count += 1
    if count > 0:
        save_model_statuses(statuses)
    return count
