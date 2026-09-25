"""Health verification and model status management for Nexus-Link."""

import logging
import asyncio
import httpx
from typing import Dict, List, Tuple, Optional
from models import update_model_status, load_model_statuses, hide_non_working_models

logger = logging.getLogger(__name__)


async def check_single_model_health(
    base_url: str,
    api_key: str,
    model_id: str,
    timeout: float = 6.0
) -> Tuple[bool, Optional[str]]:
    """Prüft ob ein Modell über die API erreichbar und nutzbar ist.

    Sendet einen minimalistischen Request (z.B. max_tokens=1) an /chat/completions.
    """
    if not base_url:
        return False, "Keine Base URL konfiguriert"

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Verschiedene Payload-Varianten ausprobieren
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                return True, None

            # Bei manchen Modellen/Gateways (z.B. rein Vision/Embeddings) gibt chat/completions 400 zurück,
            # aber mit spezifischer Fehlermeldung, die bestätigt, dass das Modell existiert.
            err_text = resp.text[:300]
            if resp.status_code == 400 and ("invalid" not in err_text.lower() and "not found" not in err_text.lower()):
                # Modell ist erreichbar, verlangt aber ggf. andere Parameter
                return True, None

            return False, f"HTTP {resp.status_code}: {err_text}"
    except httpx.TimeoutException:
        return False, "Timeout bei API-Anfrage"
    except Exception as e:
        return False, str(e)


async def verify_all_models_health(
    provider_config,
    model_ids: List[str],
    auto_hide: bool = False
) -> Dict[str, dict]:
    """Prüft die Funktionsfähigkeit aller übergebenen Modelle parallel.

    Gibt ein Dictionary mit den Testergebnissen pro Modell zurück.
    """
    tasks = []
    for mid in model_ids:
        tasks.append(
            check_single_model_health(
                provider_config.base_url,
                provider_config.api_key,
                mid
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    summary = {}
    non_working = []

    for mid, res in zip(model_ids, results):
        if isinstance(res, Exception):
            status = "non_working"
            err = str(res)
        else:
            is_working, err = res
            status = "working" if is_working else "non_working"

        update_model_status(mid, status, err, hide_if_failed=auto_hide)
        if status == "non_working":
            non_working.append(mid)

        summary[mid] = {
            "status": "hidden" if (auto_hide and status == "non_working") else status,
            "error": err,
        }

    if auto_hide and non_working:
        hide_non_working_models(non_working)

    return summary
