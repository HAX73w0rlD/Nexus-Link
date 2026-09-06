# 🎯 Nexus-Link

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/License-Proprietary-red.svg" alt="License">
  <img src="https://img.shields.io/badge/Telegram-Bot-green.svg" alt="Telegram">
  <img src="https://img.shields.io/badge/Claude-Code-purple.svg" alt="Claude">
</p>

> **Control Claude Code from anywhere via Telegram.**
> This bot allows you to remote control the Claude Code CLI - on the go, from the couch, or any other location.

---

## ✨ Features

| Feature | Description |
|---------|------------|
| 📡 **Live Streaming** | Real-time Claude responses directly in Telegram |
| 🔒 **Tool Approval** | Security prompts with inline buttons (`✅ Yes` / `❌ No` / `✅ Always`) |
| 💾 **Persistent Memory** | Settings, sessions and history are preserved |
| 🌍 **Universal Provider** | Works with any OpenAI-compatible API endpoint |
| 🔄 **Resume Session** | Context is preserved between messages |
| 📁 **File Management** | `/read`, `/write`, `/ls`, `/grep`, `/exec` |

---

## 🚀 Quick Start

### 1. Requirements

- Python 3.10 or higher
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- Telegram User-ID ([@userinfobot](https://t.me/userinfobot))
- API endpoint + Key (Anthropic, OpenAI, Ollama, or custom gateway)

### 2. Installation

```bash
# Clone repository
git clone https://github.com/HAX73w0rlD/Nexus-Link.git
cd Nexus-Link

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Telegram (Required)
TELEGRAM_TOKEN=your_bot_token_from_botfather
ALLOWED_USER_ID=your_telegram_user_id

# Provider (Required)
PROVIDER=my-provider
BASE_URL=https://api.anthropic.com
API_KEY=sk-ant-your-key
```

### 4. Start

```bash
./manage.sh start
```

---

## 📋 Commands

| Command | Description |
|---------|------------|
| `/new` | Start new session |
| `/resume` | Resume session |
| `/history` | View session history |
| `/model` | Change model |
| `/mlist` | List available models |
| `/permissions` | Manage tool permissions |
| `/read <file>` | Read file |
| `/write <file>` | Write file |
| `/ls <dir>` | List directory |
| `/grep <pattern>` | Search in files |
| `/exec <cmd>` | Execute bash command |

---

## 🔧 Provider Configuration

Nexus-Link supports **any** OpenAI-compatible API endpoint:

| Provider | BASE_URL Example | Note |
|----------|-----------------|------|
| **Anthropic** | `https://api.anthropic.com` | Direct with Anthropic |
| **OpenAI** | `https://api.openai.com/v1` | OpenAI API |
| **Ollama** | `http://localhost:11434` | Local models |
| **Custom Gateway** | `http://localhost:20128` | Custom proxy/gateway |

---

## 🏗️ Architecture

```
Nexus-Link/
├── bot.py          # Main logic (Telegram Bot)
├── providers.py    # API Provider abstraction
├── memory.py       # Persistence (Sessions, Settings)
├── i18n.py         # Internationalization
├── manage.sh       # Start/Stop script
├── .env            # Credentials (not in Git!)
└── .env.example    # Template for .env
```

---

## 🛡️ Security

- **User Authentication**: Only defined user IDs have access
- **Tool Approval**: Critical tools require explicit confirmation
- **Environment Separation**: API keys are only stored in `.env` (never in Git!)

---

## 📄 License

> **Copyright (c) 2026 Fudasys**
>
> This project is **proprietary** and not licensed for commercial use.
> Any modifications or forks must credit the creator **Fudasys** with a link to [github.com/HAX73w0rlD](https://github.com/HAX73w0rlD).
>
> For questions: Open an issue.

---

📄 Deutsche Version: [README.de.md](./README.de.md)

---

<p align="center">
  <sub>Made with ❤️ by <a href="https://github.com/HAX73w0rlD">Fudasys</a></sub>
</p>
