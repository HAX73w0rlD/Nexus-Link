# 🎯 Nexus-Link

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/License-Private-red.svg" alt="License">
  <img src="https://img.shields.io/badge/Telegram-Bot-green.svg" alt="Telegram">
  <img src="https://img.shields.io/badge/Claude-Code-purple.svg" alt="Claude">
</p>

> **Steuere Claude Code von überall per Telegram.**  
> Dieser Bot ermöglicht es dir, die Claude Code CLI fernzusteuern – von unterwegs, vom Sofa oder jedem beliebigen Ort.

---

## ✨ Features

| Feature | Beschreibung |
|---------|-------------|
| 📡 **Live-Streaming** | Echtzeit-Antworten von Claude direkt in Telegram |
| 🔒 **Tool-Freigabe** | Sicherheitsabfragen mit Inline-Buttons (`✅ Ja` / `❌ Nein` / `✅ Immer`) |
| 💾 **Persistentes Memory** | Einstellungen, Sessions und History bleiben erhalten |
| 🌍 **Universal-Provider** | Funktioniert mit jedem OpenAI-kompatiblen API-Endpoint |
| 🔄 **Session fortsetzen** | Kontext bleibt zwischen Nachrichten erhalten |
| 📁 **Dateiverwaltung** | `/read`, `/write`, `/ls`, `/grep`, `/exec` |

---

## 🚀 Quick Start

### 1. Voraussetzungen

- Python 3.10 oder höher
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installiert
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- Telegram User-ID ([@userinfobot](https://t.me/userinfobot))
- API-Endpoint + Key (Anthropic, OpenAI, Ollama, oder eigener Gateway)

### 2. Installation

```bash
# Repository klonen
git clone https://github.com/HAX73w0rlD/Nexus-Link.git
cd Nexus-Link

# Virtuelle Umgebung erstellen
python3 -m venv venv
source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt
```

### 3. Konfiguration

```bash
cp .env.example .env
```

Bearbeite `.env`:

```env
# Telegram (Pflicht)
TELEGRAM_TOKEN=your_bot_token_from_botfather
ALLOWED_USER_ID=your_telegram_user_id

# Provider (optional)
PROVIDER=my-provider
BASE_URL=https://api.anthropic.com
API_KEY=sk-ant-your-key
```

### 4. Starten

```bash
./manage.sh start
```

---

## 📋 Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `/new` | Neue Session starten |
| `/resume` | Session fortsetzen |
| `/history` | Sessions-History anzeigen |
| `/model` | Modell wechseln |
| `/mlist` | Verfügbare Modelle auflisten |
| `/permissions` | Tool-Berechtigungen verwalten |
| `/read <file>` | Datei lesen |
| `/write <file>` | Datei schreiben |
| `/ls <dir>` | Verzeichnis auflisten |
| `/grep <pattern>` | In Dateien suchen |
| `/exec <cmd>` | Bash-Befehl ausführen |

---

## 🔧 Provider-Konfiguration

Nexus-Link unterstützt **jeden** OpenAI-kompatiblen API-Endpoint:

| Anbieter | BASE_URL Beispiel | Hinweis |
|----------|------------------|---------|
| **Anthropic** | `https://api.anthropic.com` | Direkt mit Anthropic |
| **OpenAI** | `https://api.openai.com/v1` | OpenAI API |
| **Ollama** | `http://localhost:11434` | Lokale Modelle |
| **Custom Gateway** | `http://localhost:20128` | Eigener Proxy/Gateway |

---

## 🏗️ Architektur

```
Nexus-Link/
├── bot.py          # Hauptlogik (Telegram Bot)
├── providers.py    # API-Provider Abstraktion
├── memory.py       # Persistenz (Sessions, Settings)
├── i18n.py         # Internationalisierung
├── manage.sh       # Start/Stop Script
├── .env            # Zugangsdaten (nicht in Git!)
└── .env.example    # Template für .env
```

---

## 🛡️ Sicherheit

- **User-Authentifizierung**: Nur definierte User-IDs haben Zugriff
- **Tool-Freigabe**: Kritische Tools erfordern explizite Bestätigung
- **Environment-Trennung**: API-Keys werden nur in `.env` gespeichert (nie in Git!)

---

## 📄 Lizenz

> **Copyright (c) 2026 Fudasys**
>
> Dieses Projekt ist **proprietär** und nicht für kommerzielle Nutzung freigegeben.
> Jede Abwandlung oder Forks müssen den Creator **Fudasys** mit Link zu [github.com/HAX73w0rlD](https://github.com/HAX73w0rlD) nennen.
>
> Bei Fragen: Erstelle ein Issue.

---

<p align="center">
  <sub>Made with ❤️ by <a href="https://github.com/HAX73w0rlD">Fudasys</a></sub>
</p>
