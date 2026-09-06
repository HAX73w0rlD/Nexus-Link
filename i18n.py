"""Mehrsprachigkeit für den Telegram-Bot (Deutsch/Englisch)."""
from typing import Literal

Lang = Literal["de", "en"]

TEXTS = {
    "de": {
        # Start/Help
        "welcome": "🤖 *Claude Code Bot Fudasys*\n\nHallo\\! Ich bin dein Claude\\-Code\\-Bot\\.\n\n*Was kann ich?*\n• Code schreiben, lesen, editieren\n• Dateien suchen \\(grep, glob\\)\n• Web suchen \\(wenn erlaubt\\)\n• Kontext über mehrere Nachrichten merken\n• Befehle ausführen \\(Bash\\)\n\n*📋 Befehle* \\(klickbar\\):\n/plan · /auto · /accept · /bypass · /default · /dontask\n/model \\(sonnet/opus/haiku\\) · /mlist\n/cd \\<pfad\\> · /add \\<pfad\\>\n/system \\<prompt\\>\n/status · /stop · /logs\n/new · /resume\n/history · /jobs\n/tools · /permissions\n/read · /write · /ls · /grep · /exec\n/doctor · /config\n/language · /lang\n\n*Modell:* `{model}`\n*Modus:* {mode}\n*Working\\-Dir:* `{cwd}`\n*Sprache:* {lang_label}\n\n_Schick einfach eine Nachricht – Claude arbeitet im Hintergrund\\._",
        "language_set": "✅ Sprache: <b>Deutsch</b>",
        # Status
        "no_active_job": "ℹ️ Kein aktiver Job.",
        "job_running": "⚠️ Es läuft bereits ein Job. Stoppe ihn erst mit /stop oder warte.\nAktueller Status: {status}",
        "job_started": "🚀 <b>Starte Job...</b>\n\n<i>Modus: {mode} · Modell: {model}</i>",
        "job_stopped": "🛑 Job gestoppt.",
        "job_completed": "✅ Fertig",
        "job_failed": "❌ Fehler",
        "job_aborted": "🛑 Abgebrochen",
        "status_header": "<b>📊 Status</b>\n\n<b>User:</b> <code>{user_id}</code>\n<b>Sprache:</b> {lang}\n<b>Modus:</b> {mode}\n<b>Modell:</b> {model}\n<b>Working-Dir:</b> <code>{cwd}</code>",
        "active_job_info": "\n<b>Aktiver Job:</b>\n• Status: {status}\n• ID: <code>{job_id}</code>\n• Laufzeit: {elapsed}\n• Prompt: <code>{prompt}</code>",
        "no_job_info": "\n<i>Kein aktiver Job.</i>",
        # Logs
        "no_logs": "ℹ️ Noch keine Logs.",
        "logs_header": "<b>📋 Letzte Logs</b>\n\n",
        # History
        "no_history": "📭 Keine History vorhanden.",
        "history_header": "<b>📜 History (letzte {count} Einträge)</b>\n\n",
        "history_role_user": "👤",
        "history_role_assistant": "🤖",
        # Jobs
        "no_jobs": "📭 Keine vergangenen Jobs.",
        "jobs_header": "<b>📋 Letzte {count} Jobs</b>\n\n",
        # Tools
        "tools_header": "<b>🛠️ Tool-Konfiguration</b>\n\n<b>Tools-Set:</b> <code>{tools}</code>\n",
        "tools_allowed": "<b>Erlaubt:</b> {tools}\n",
        "tools_disallowed": "<b>Verboten:</b> {tools}\n",
        "tools_help": "\n<i>Setzen mit /tools set &lt;liste&gt; (z.B. <code>/tools set Read,Edit</code>)</i>\n<i>Erlauben: <code>/tools allow Bash(git *)</code></i>\n<i>Verbieten: <code>/tools deny Bash(rm *)</code></i>",
        # Permissions
        "perm_header": "<b>🔐 Tool-Permissions</b>\n\n",
        "perm_allowed": "<b>Erlaubt ({count}):</b>\n",
        "perm_disallowed": "<b>Verboten ({count}):</b>\n",
        "perm_reset_done": "🔄 <b>Permissions auf Defaults zurückgesetzt</b>",
        "perm_help": "\n<i>Defaults zurücksetzen mit</i> <code>/permissions reset</code>\n<i>Erlauben: <code>/tools allow Bash(git *)</code></i>\n<i>Verbieten: <code>/tools deny Bash(rm *)</code></i>",
        # Models
        "models_header": "<b>📋 Modelle</b>\n\nAktuell: <b>{current}</b>\nWähle ein Modell:",
        # Modes
        "mode_set": "✅ <b>Permission-Mode:</b> {label}",
        "model_set": "✅ Modell: <b>{model}</b>",
        # Working dir
        "cd_set": "📂 Working-Dir: <code>{path}</code>",
        "cd_invalid": "❌ Pfad existiert nicht: <code>{path}</code>",
        "add_set": "✅ Hinzugefügt: <code>{path}</code>",
        "add_invalid": "❌ Pfad existiert nicht: <code>{path}</code>",
        "add_dirs_header": "<b>📁 Freigegebene Verzeichnisse:</b>\n",
        "add_dirs_empty": "ℹ️ Keine zusätzlichen Verzeichnisse. Nutze <code>/add /pfad</code>.",
        # System prompt
        "system_current": "<b>Aktueller System-Prompt:</b>\n<code>{prompt}</code>\n\nLeeren mit <code>/system clear</code>",
        "system_empty": "ℹ️ Kein System-Prompt gesetzt.",
        "system_cleared": "🗑️ System-Prompt gelöscht.",
        "system_set": "✅ System-Prompt gesetzt: <code>{prompt}</code>",
        # New/Resume
        "new_session": "🆕 <b>Neue Session.</b> Kontext zurückgesetzt.",
        "resume_info": "🔄 <b>Session fortsetzen?</b>\n\nSession-ID: <code>{sid}</code>\n\nSchick einfach eine Nachricht, um fortzufahren.",
        "resume_none": "ℹ️ Keine vorherige Session vorhanden.",
        # Errors
        "start_failed": "❌ <b>Fehler beim Start:</b>\n<code>{error}</code>",
        "doctor_failed": "❌ Doctor fehlgeschlagen: <code>{error}</code>",
        "exec_timeout": "⏱️ Timeout nach 30s",
        "exec_error": "❌ Fehler: <code>{error}</code>",
        "exec_no_output": "(keine Ausgabe)",
        "exec_format": "<b>💻 $ {cmd}</b>\n\n<pre>{output}</pre>",
        # Read/Write
        "read_usage": "ℹ️ Verwendung: <code>/read /pfad/zur/datei</code>",
        "read_not_found": "❌ Datei nicht gefunden: <code>{path}</code>",
        "read_format": "<b>📄 {path}</b>\n\n<pre>{content}</pre>",
        "read_error": "❌ Fehler beim Lesen: <code>{error}</code>",
        "write_usage": "ℹ️ Verwendung: <code>/write /pfad/zur/datei &lt;inhalt&gt;</code>\nTipp: Bei langem Inhalt erst <code>/read</code> prüfen.",
        "write_done": "✅ <b>geschrieben:</b> <code>{path}</code>\n<i>{chars} Zeichen</i>",
        "write_error": "❌ Fehler beim Schreiben: <code>{error}</code>",
        "ls_usage": "ℹ️ Verwendung: <code>/ls [pfad]</code>",
        "ls_dir_not_found": "❌ Verzeichnis nicht gefunden: <code>{path}</code>",
        "ls_error": "❌ Fehler: <code>{error}</code>",
        "grep_usage": "ℹ️ Verwendung: <code>/grep pattern [pfad]</code>",
        "grep_no_results": "🔍 Keine Treffer für <code>{pattern}</code>",
        "grep_results": "<b>🔍 Treffer für '{pattern}'</b>\n\n",
        "grep_more": "\n\n<i>... und {count} weitere Treffer</i>",
        "truncated": "\n\n<i>... (gekürzt)</i>",
        # Permission flow
        "perm_required": "🔐 *TOOL-PERMISSION ERFORDERLICH*",
        "perm_tool": "→ Tool: `{tool}`",
        "perm_pattern": "→ Pattern: `{pattern}`",
        "perm_input": "→ Input: `{input}`",
        "perm_command": "\n*Freigabe-Befehl:*\n`/tools allow {pattern}`\n",
        "perm_choose": "\n*Oder wähle unten eine Option:*\n",
        # Models help
        "models_help": "<b>Modell:</b> {current}\n\nVerfügbare Modelle findest du mit /mlist",
        "model_invalid": "❌ Unbekanntes Modell. Wähle aus der Liste (siehe /mlist).",
        "model_changed_active": "✅ Modell: <b>{model}</b>\n⚠️ Aktiver Job wird mit dem neuen Modell neu gestartet…",
        # Language
        "lang_select": "🌐 <b>Sprache / Language</b>\n\nAktuell / Current: <b>{current}</b>",
    },
    "en": {
        # Start/Help
        "welcome": "🤖 *Claude Code Bot Fudasys*\n\nHello\\! I'm your Claude Code bot\\.\n\n*What do I do?*\n• Write, read and edit code\n• Search files \\(grep, glob\\)\n• Search the web \\(when allowed\\)\n• Remember context across messages\n• Run commands \\(Bash\\)\n\n*📋 Commands* \\(clickable\\):\n/plan · /auto · /accept · /bypass · /default · /dontask\n/model \\(sonnet/opus/haiku\\) · /mlist\n/cd \\<path\\> · /add \\<path\\>\n/system \\<prompt\\>\n/status · /stop · /logs\n/new · /resume\n/history · /jobs\n/tools · /permissions\n/read · /write · /ls · /grep · /exec\n/doctor · /config\n/language · /lang\n\n*Model:* `{model}`\n*Mode:* {mode}\n*Working\\-Dir:* `{cwd}`\n*Language:* {lang_label}\n\n_Just send a message – Claude works in the background\\._",
        "language_set": "✅ Language: <b>English</b>",
        # Status
        "no_active_job": "ℹ️ No active job.",
        "job_running": "⚠️ A job is already running. Stop it first with /stop or wait.\nCurrent status: {status}",
        "job_started": "🚀 <b>Starting job...</b>\n\n<i>Mode: {mode} · Model: {model}</i>",
        "job_stopped": "🛑 Job stopped.",
        "job_completed": "✅ Done",
        "job_failed": "❌ Error",
        "job_aborted": "🛑 Aborted",
        "status_header": "<b>📊 Status</b>\n\n<b>User:</b> <code>{user_id}</code>\n<b>Language:</b> {lang}\n<b>Mode:</b> {mode}\n<b>Model:</b> {model}\n<b>Working-Dir:</b> <code>{cwd}</code>",
        "active_job_info": "\n<b>Active job:</b>\n• Status: {status}\n• ID: <code>{job_id}</code>\n• Runtime: {elapsed}\n• Prompt: <code>{prompt}</code>",
        "no_job_info": "\n<i>No active job.</i>",
        # Logs
        "no_logs": "ℹ️ No logs yet.",
        "logs_header": "<b>📋 Recent Logs</b>\n\n",
        # History
        "no_history": "📭 No history available.",
        "history_header": "<b>📜 History (last {count} entries)</b>\n\n",
        "history_role_user": "👤",
        "history_role_assistant": "🤖",
        # Jobs
        "no_jobs": "📭 No past jobs.",
        "jobs_header": "<b>📋 Last {count} Jobs</b>\n\n",
        # Tools
        "tools_header": "<b>🛠️ Tool Configuration</b>\n\n<b>Tools-Set:</b> <code>{tools}</code>\n",
        "tools_allowed": "<b>Allowed:</b> {tools}\n",
        "tools_disallowed": "<b>Denied:</b> {tools}\n",
        "tools_help": "\n<i>Set with /tools set &lt;list&gt; (e.g. <code>/tools set Read,Edit</code>)</i>\n<i>Allow: <code>/tools allow Bash(git *)</code></i>\n<i>Deny: <code>/tools deny Bash(rm *)</code></i>",
        # Permissions
        "perm_header": "<b>🔐 Tool Permissions</b>\n\n",
        "perm_allowed": "<b>Allowed ({count}):</b>\n",
        "perm_disallowed": "<b>Denied ({count}):</b>\n",
        "perm_reset_done": "🔄 <b>Permissions reset to defaults</b>",
        "perm_help": "\n<i>Reset to defaults with</i> <code>/permissions reset</code>\n<i>Allow: <code>/tools allow Bash(git *)</code></i>\n<i>Deny: <code>/tools deny Bash(rm *)</code></i>",
        # Models
        "models_header": "<b>📋 Models</b>\n\nCurrent: <b>{current}</b>\nSelect a model:",
        # Modes
        "mode_set": "✅ <b>Permission Mode:</b> {label}",
        "model_set": "✅ Model: <b>{model}</b>",
        # Working dir
        "cd_set": "📂 Working-Dir: <code>{path}</code>",
        "cd_invalid": "❌ Path not found: <code>{path}</code>",
        "add_set": "✅ Added: <code>{path}</code>",
        "add_invalid": "❌ Path not found: <code>{path}</code>",
        "add_dirs_header": "<b>📁 Shared directories:</b>\n",
        "add_dirs_empty": "ℹ️ No additional directories. Use <code>/add /path</code>.",
        # System prompt
        "system_current": "<b>Current system prompt:</b>\n<code>{prompt}</code>\n\nClear with <code>/system clear</code>",
        "system_empty": "ℹ️ No system prompt set.",
        "system_cleared": "🗑️ System prompt cleared.",
        "system_set": "✅ System prompt set: <code>{prompt}</code>",
        # New/Resume
        "new_session": "🆕 <b>New session.</b> Context cleared.",
        "resume_info": "🔄 <b>Resume session?</b>\n\nSession-ID: <code>{sid}</code>\n\nJust send a message to continue.",
        "resume_none": "ℹ️ No previous session available.",
        # Errors
        "start_failed": "❌ <b>Start failed:</b>\n<code>{error}</code>",
        "doctor_failed": "❌ Doctor failed: <code>{error}</code>",
        "exec_timeout": "⏱️ Timeout after 30s",
        "exec_error": "❌ Error: <code>{error}</code>",
        "exec_no_output": "(no output)",
        "exec_format": "<b>💻 $ {cmd}</b>\n\n<pre>{output}</pre>",
        # Read/Write
        "read_usage": "ℹ️ Usage: <code>/read /path/to/file</code>",
        "read_not_found": "❌ File not found: <code>{path}</code>",
        "read_format": "<b>📄 {path}</b>\n\n<pre>{content}</pre>",
        "read_error": "❌ Read error: <code>{error}</code>",
        "write_usage": "ℹ️ Usage: <code>/write /path/to/file &lt;content&gt;</code>\nTip: For long content, check with <code>/read</code> first.",
        "write_done": "✅ <b>written:</b> <code>{path}</code>\n<i>{chars} characters</i>",
        "write_error": "❌ Write error: <code>{error}</code>",
        "ls_usage": "ℹ️ Usage: <code>/ls [path]</code>",
        "ls_dir_not_found": "❌ Directory not found: <code>{path}</code>",
        "ls_error": "❌ Error: <code>{error}</code>",
        "grep_usage": "ℹ️ Usage: <code>/grep pattern [path]</code>",
        "grep_no_results": "🔍 No matches for <code>{pattern}</code>",
        "grep_results": "<b>🔍 Matches for '{pattern}'</b>\n\n",
        "grep_more": "\n\n<i>... and {count} more matches</i>",
        "truncated": "\n\n<i>... (truncated)</i>",
        # Permission flow
        "perm_required": "🔐 *TOOL PERMISSION REQUIRED*",
        "perm_tool": "→ Tool: `{tool}`",
        "perm_pattern": "→ Pattern: `{pattern}`",
        "perm_input": "→ Input: `{input}`",
        "perm_command": "\n*Command to allow:*\n`/tools allow {pattern}`\n",
        "perm_choose": "\n*Or choose an option below:*\n",
        # Models help
        "models_help": "<b>Model:</b> {current}\n\nSee available models with /mlist",
        "model_invalid": "❌ Unknown model. Choose from list (see /mlist).",
        "model_changed_active": "✅ Model: <b>{model}</b>\n⚠️ Active job will be restarted with new model…",
        # Language
        "lang_select": "🌐 <b>Language / Sprache</b>\n\nCurrent / Aktuell: <b>{current}</b>",
    },
}

LANG_NAMES = {"de": "🇩🇪 Deutsch", "en": "🇬🇧 English"}

def t(key: str, lang: str = "de", **kwargs) -> str:
    """Gibt lokalisierten Text zurück, mit Fallback auf Deutsch."""
    text = TEXTS.get(lang, TEXTS["de"]).get(key) or TEXTS["de"].get(key, key)
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError):
        return text

def get_lang(user_state) -> str:
    """Gibt die Sprache des Users zurück (Default: de)."""
    return getattr(user_state, "language", "de")
