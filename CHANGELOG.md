# Changelog

Alle wichtigen Änderungen werden hier dokumentiert.

## [1.0.2] - 2026-09-25

### Added
- Erweiterte Modellverwaltung und automatische Kategorisierung nach Fähigkeiten (Text, Code, Bilder, Videos, Audio, Embeddings).
- Unterscheidung der Ansprechmethode (Claude Code CLI vs Open Code / Direct API) mit visuellen Emojis.
- Asynchrone Erreichbarkeitsprüfung (`model_checker.py`) und automatisches Ausblenden defekter/nicht erreichbarer Modelle per Knopf ("🧹 Defekte ausblenden").
- Interaktive Kategorie-Filter-Tabs im Telegram-Modellmenü (🌐, 💬, 💻, 🎨, 🎬).
- "👁️ Alle einblenden"-Button zum Wiederherstellen verborgener Modelle.
- Mehrsprachige Text-Strings (DE/EN) für alle Modellverwaltungsaktionen.
- Unit-Tests (`test_models.py`) und Ruff Linter-Konfiguration (`pyproject.toml`).

## [1.0.0] - 2026-09-06

### Added
- Initial release
- Telegram Bot für Claude Code Fernsteuerung
- Live-Streaming der Claude-Antworten
- Tool-Freigabe per Inline-Buttons
- Persistentes Memory für Sessions und Settings
- Provider-unabhängig (OpenAI-kompatibel)
- Modell-Auswahl mit Auto-Detection
- Session fortsetzen
- Dateiverwaltung (/read, /write, /ls, /grep, /exec)
- Multi-Language Support (DE/EN)

### Features
- `/new` - Neue Session starten
- `/resume` - Session fortsetzen
- `/history` - Sessions-History anzeigen
- `/model` - Modell wechseln
- `/mlist` - Verfügbare Modelle anzeigen
- `/permissions` - Tool-Berechtigungen verwalten
