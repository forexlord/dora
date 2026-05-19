# Dora

**Dora** is a local Windows voice assistant. Say **“Dora”** or **“hey Dora”**, then ask for apps, volume, battery, or chat. Speech runs offline (Vosk); understanding and chat use local [Ollama](https://ollama.com).

**Creator:** Recovery Eyo — software engineer, Nigeria.

---

## Install (Windows — no git, no coding)

### What you need

- **Windows 10 or 11**
- **Internet** for the one-time installer (downloads speech model + AI)
- **Microphone** allowed for apps when Windows asks

The installer will try to install **Python 3.10+** (via winget) and **Ollama** if they are missing.

### Steps

1. Open the **[Releases](https://github.com/forexlord/voice-assistant/releases)** page on GitHub.
2. Download **`Dora-windows.zip`** (or the latest release ZIP).
3. **Extract** the ZIP to any folder (e.g. `Downloads\Dora`).
4. Double-click **`Install-Dora.bat`**.
5. Wait until you see **“Installation complete!”** (first time can take **10–20 minutes** while models download).
6. Double-click the **Dora** shortcut on your **Desktop**.

Say **“Dora”** when you hear that Dora is ready.

### Optional: start when you sign in to Windows

Run the installer again from an **Administrator** or normal PowerShell window:

```powershell
cd "C:\path\to\extracted\Dora"
powershell -ExecutionPolicy Bypass -File install.ps1 -AddToStartup
```

Or after install:

```powershell
& "$env:LOCALAPPDATA\Dora\app\venv\Scripts\dora.exe" --install-startup
```

---

## After install

| Item | Location |
|------|----------|
| Installed app | `%LOCALAPPDATA%\Dora\app` |
| Start shortcut | `%LOCALAPPDATA%\Dora\Start Dora.bat` |
| Desktop | **Dora** |
| Logs | `%LOCALAPPDATA%\Dora\dora.log` |

### Examples

- *“Dora”* → *“Open Chrome”*
- *“What is my volume status?”* → real volume from Windows
- *“Mute my audio”* / *“Unmute”*
- *“What is my battery percentage?”*
- *“Who is your creator?”*
- *“Thank you, that was helpful”* → ends the session

### Uninstall

1. Delete shortcuts: Desktop **Dora**, Start menu **Dora** folder.
2. Remove startup (if used):  
   `"%LOCALAPPDATA%\Dora\app\venv\Scripts\dora.exe" --uninstall-startup`
3. Delete folder: `%LOCALAPPDATA%\Dora`

---

## Settings

Edit:

`%LOCALAPPDATA%\Dora\app\config.json`

Common options:

- `wake_word` — default `dora`
- `ollama_model` — default `phi` (run `ollama pull <name>` if you change it)
- `speak_responses` — `true` / `false`
- `show_status_overlay` — floating status card

Restart Dora after changes.

---

## Troubleshooting

### Installer says Python is missing

Install [Python 3.10+](https://www.python.org/downloads/) and check **“Add Python to PATH”**, then run **`Install-Dora.bat`** again.

### “Ollama not found”

1. Install from [ollama.com](https://ollama.com).
2. Open a terminal and run: `ollama pull phi`
3. Run **`Install-Dora.bat`** again, or start **Dora** from the desktop.

### Dora does not hear me

**Settings → Privacy & security → Microphone** — allow desktop apps / Python.

### Slow or wrong answers

- Keep the **Ollama** app running in the tray.
- Use a smaller chat model in config: `"ollama_chat_model": "phi3:mini"` (after `ollama pull phi3:mini`).

### Re-run setup (re-download models)

```powershell
& "$env:LOCALAPPDATA\Dora\app\venv\Scripts\python.exe" "$env:LOCALAPPDATA\Dora\app\scripts\first_run_setup.py"
```

---

## For developers (optional)

If you work on the source repo with git:

```powershell
git clone https://github.com/forexlord/voice-assistant.git
cd voice-assistant
.\Install-Dora.bat
```

Or manual dev setup:

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .
$env:DORA_HOME = (Get-Location).Path
dora
```

### Publishing a release ZIP (maintainers)

Create a ZIP of the repo **without** `venv/`, `models/`, `.git/`, then attach to GitHub Releases as `Dora-windows.zip`. Users only need **`Install-Dora.bat`** + **`install.ps1`** + project files inside the ZIP.

---

## License

Add your license before publishing (e.g. MIT).

---

## Credits

**Dora** — Windows voice assistant  
**Recovery Eyo** — creator
