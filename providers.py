"""Provider-Konfiguration für den Telegram-Bot.

Lädt config.yaml und stellt die Provider-Definitionen bereit.
Jede Sektion (außer "provider") wird als eigener Provider registriert.
Modelle werden dynamisch vom konfigurierten Gateway/Provider abgerufen.
"""
import os
import json
import httpx
import asyncio
import logging
from pathlib import Path
from typing import Any

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

logger = logging.getLogger(__name__)


class ProviderConfig:
    """Ein Provider (beliebiger Name, vollständig konfigurierbar via config.yaml)."""

    def __init__(self, name: str, data: dict):
        self.name = name
        self.api_key = data.get("api_key", "")
        self.base_url = data.get("base_url", "")
        self.model = data.get("model", "auto")
        # Models können als Liste von Dicts (id, label) oder Tupeln (id, label) kommen
        raw = data.get("models", [])
        models = []
        for m in raw:
            if isinstance(m, dict):
                mid = m.get("id", "")
                label = m.get("label", mid)
                models.append((mid, label))
            elif isinstance(m, (list, tuple)) and len(m) == 2:
                models.append((m[0], m[1]))
        self.models = models

    def __repr__(self):
        return f"ProviderConfig(name={self.name!r}, model={self.model!r}, base_url={self.base_url!r})"

    def get_model_list(self, force_refresh: bool = False) -> list[tuple[str, str]]:
        """Gibt die Liste der verfügbaren Modelle zurück.

        Reihenfolge:
        1. Explizit konfigurierte Models (aus config.yaml)
        2. Gecachte Models (von früherem API-Abruf)
        3. API-Abruf (dynamisch)
        4. Fallback auf ["auto", "Auto"]
        """
        # 1. Explizit konfigurierte Models
        if self.models:
            return self.models

        # 2. Cache prüfen (wenn nicht force_refresh)
        if not force_refresh:
            cached = load_cached_models(self.name)
            if cached:
                return cached

        # 3. API-Abruf
        models = self.fetch_models()
        if models:
            # Cache speichern
            save_cached_models(self.name, models)
            return models

        # 4. Fallback
        return [("auto", "🌐 Auto")] if not force_refresh else []

    def fetch_models(self) -> list[tuple[str, str]]:
        """Versucht Modelle vom API-Endpoint abzurufen ( /models oder /model ).

        Unterstützt verschiedene API-Formate:
        - OpenAI-Format: {"data": [{"id": "...", "display_name": "..."}, ...]}
        - OmniRoute-Format: {"models": [{"id": "...", "label": "..."}, ...]}
        - Einfache Liste: ["model-id-1", "model-id-2", ...]
        - Auto-Routing-Katalog: ["auto/...", "auto/...", ...]
        """
        if not self.base_url:
            return []

        base = self.base_url.rstrip("/")
        endpoints = [f"{base}/models", f"{base}/models?flat=true"]
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # OmniRoute unterstützt oft einen speziellen Catalog-Endpoint
        catalog_endpoints = [
            f"{base}/models/catalog",
            f"{base}/catalog",
            f"{base}/routing/catalog",
        ]

        all_endpoints = endpoints + catalog_endpoints

        for url in all_endpoints:
            try:
                r = httpx.get(url, headers=headers, timeout=8.0)
                if r.status_code == 200:
                    data = r.json()
                    items = []

                    # Verschiedene API-Formate parsen
                    if isinstance(data, dict) and "data" in data:
                        # OpenAI-Format
                        items = data["data"]
                    elif isinstance(data, dict) and "models" in data:
                        # OmniRoute-Format
                        items = data["models"]
                    elif isinstance(data, dict) and "catalog" in data:
                        # OmniRoute Auto-Routing-Katalog
                        catalog = data["catalog"]
                        if isinstance(catalog, list):
                            items = catalog
                        elif isinstance(catalog, dict) and "models" in catalog:
                            items = catalog["models"]
                    elif isinstance(data, list):
                        # Einfache Liste
                        items = data
                    elif isinstance(data, dict) and "routes" in data:
                        # Alternative Routing-Formate
                        items = data["routes"]

                    models = []
                    for item in items:
                        mid = ""
                        label = ""
                        if isinstance(item, dict):
                            mid = item.get("id", item.get("model", item.get("route", "")))
                            label = item.get("label", item.get("display_name", item.get("description", mid)))
                        elif isinstance(item, str):
                            mid = item
                            label = item
                        if mid:
                            models.append((mid, label))

                    if models:
                        return models
            except httpx.TimeoutException:
                continue
            except httpx.ConnectError:
                continue
            except Exception:
                continue
        return []


def load_config() -> tuple[str, dict[str, ProviderConfig], ProviderConfig]:
    """Lädt die config.yaml und gibt (provider_name, all_providers, current) zurück.

    Falls keine config.yaml existiert, werden ausschließlich ENV-Variablen verwendet.
    Environment-Variablen überschreiben die config.yaml.
    """
    config_path = Path(__file__).parent / "config.yaml"
    config_data: dict[str, Any] = {}

    if config_path.exists():
        if HAS_YAML:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}
            except Exception:
                pass
        else:
            # Fallback: Einfaches YAML-Parsing (nur Ebenen-1)
            try:
                current_section = None
                with open(config_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("provider:"):
                            val = line.split(":", 1)[1].strip().strip('"').strip("'")
                            config_data["provider"] = val
                            continue
                        if line.endswith(":") and not line.startswith(" "):
                            current_section = line[:-1].strip().strip('"').strip("'")
                            config_data[current_section] = config_data.get(current_section, {})
                        elif current_section and ":" in line:
                            key, val = line.split(":", 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if not isinstance(config_data[current_section], dict):
                                config_data[current_section] = {}
                            config_data[current_section][key] = val
            except Exception:
                pass

    # Provider aus config.yaml
    providers: dict[str, ProviderConfig] = {}
    for name, section_data in config_data.items():
        if name == "provider" or not isinstance(section_data, dict):
            continue
        section = dict(section_data)
        key_env_var = f"{name.upper()}_API_KEY"
        if key_env_var in os.environ:
            section["api_key"] = os.environ[key_env_var]
        env_base_url = f"{name.upper()}_BASE_URL"
        if env_base_url in os.environ:
            section["base_url"] = os.environ[env_base_url]
        providers[name] = ProviderConfig(name, section)

    # Zusätzliche Provider nur aus ENV, wenn keine config.yaml existiert
    env_provider = os.getenv("PROVIDER")
    env_base = os.getenv("BASE_URL")
    env_key = os.getenv("API_KEY")

    if not config_data and (env_provider or env_base or env_key):
        name = env_provider or "provider"
        providers[name] = ProviderConfig(name, {
            "base_url": env_base,
            "api_key": env_key,
            "model": "auto",
        })

    # Aktiver Provider bestimmen
    provider_name = (
        os.getenv("PROVIDER")
        or config_data.get("provider")
        or env_provider
        or (list(providers.keys())[0] if providers else "")
    )

    current = providers.get(provider_name)
    if not current:
        available = list(providers.keys()) if providers else "keine"
        raise ValueError(
            f"Provider '{provider_name}' nicht gefunden. "
            f"Verfügbare: {available}\n"
            f"Prüfe config.yaml oder .env (PROVIDER, BASE_URL, API_KEY)"
        )
    return provider_name, providers, current


CACHE_FILE = Path("data/models_cache.json")


def load_cached_models(provider_name: str) -> list[tuple[str, str]]:
    if not CACHE_FILE.exists():
        return []
    try:
        with open(CACHE_FILE, "r") as f:
            all_cache = json.load(f)
        return [tuple(m) for m in all_cache.get(provider_name, [])]
    except Exception:
        return []


def save_cached_models(provider_name: str, models: list[tuple[str, str]]):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        all_cache = {}
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "r") as f:
                all_cache = json.load(f)
        all_cache[provider_name] = models
        with open(CACHE_FILE, "w") as f:
            json.dump(all_cache, f, indent=2)
    except Exception:
        pass


def get_model_list() -> list[tuple[str, str]]:
    """Gibt alle Modelle des aktuellen Providers zurück."""
    _, _, current = load_config()
    return current.get_model_list()


def get_models_with_cache(provider: 'ProviderConfig') -> list[tuple[str, str]]:
    """Gibt Modelle zurück, idealerweise aus dem Cache oder durch API-Abruf."""
    cached = load_cached_models(provider.name)
    if cached:
        return cached
    return provider.fetch_models()
