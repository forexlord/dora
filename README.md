# Dora

**Dora** is a local Windows voice assistant. Say **“Dora”** or **“hey Dora”**, then ask for apps, volume, battery, or chat. Speech runs offline (Vosk); understanding and chat use a **local GGUF model** (Phi-3 Mini via llama.cpp — no Ollama required).

**Creator:** Recovery Eyo — software engineer, Nigeria.

---

## Install (Windows — no git, no coding)

### What you need

- **Windows 10 or 11**
- **Internet** for the one-time installer (downloads speech model + AI)
- **Microphone** allowed for apps when Windows asks

The installer will try to install **Python 3.10+** (via winget) if it is missing. It then downloads **Vosk**, a **llama.cpp** runtime for Windows, and the **Phi-3** model (~2.4 GB). **No Ollama, no Visual Studio, no extra apps.**

### Steps

1. Open the **[Releases](https://github.com/forexlord/dora/releases)** page on GitHub.
2. Download **`Dora-windows.zip`** (or the latest release ZIP).
3. **Extract** the ZIP to any folder (e.g. `Downloads\Dora`).
4. Double-click **`Install-Dora.bat`** (run from the **extracted ZIP or git folder**, not only from AppData).
5. Wait until you see **“Installation complete!”** (first time can take **10–20 minutes** while models download).

You can also re-run **`Install-Dora.bat`** from the installed folder later; the installer will find your git clone or download the latest code from GitHub automatically.
6. Double-click the **Dora** shortcut on your **Desktop**.

Say **“Dora”** when you hear that Dora is ready.

**Dora starts in the background when you sign in to Windows** (no need to open the desktop shortcut every time). To turn that off:

```powershell
& "$env:LOCALAPPDATA\Dora\app\venv\Scripts\dora.exe" --uninstall-startup
```

To re-enable sign-in startup:

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
- `llm_model_path` — path to the `.gguf` file (default Phi-3 Mini Q4)
- `llm_model_url` — download URL if the file is missing
- `speak_responses` — `true` / `false`
- `show_status_overlay` — floating status card

Restart Dora after changes.

---

## Troubleshooting

### Installer says Python is missing

Install [Python 3.10+](https://www.python.org/downloads/) and check **“Add Python to PATH”**, then run **`Install-Dora.bat`** again.

### “Language model not found” or download failed

1. Check internet connection and disk space (~3 GB free).
2. Re-run setup:

```powershell
& "$env:LOCALAPPDATA\Dora\app\venv\Scripts\python.exe" "$env:LOCALAPPDATA\Dora\app\scripts\first_run_setup.py"
```

3. Or download a Phi-3 Mini GGUF manually, place it at the path in `llm_model_path`, and restart Dora.

### Dora does not hear me

**Settings → Privacy & security → Microphone** — allow desktop apps / Python.

### Chat does not work / “language model not running”

1. Re-run **`Install-Dora.bat`** once (downloads `tools/llama-cpp` + the GGUF if missing).
2. First startup can take **several minutes** while the model loads into RAM — wait for **“Language model is ready.”**
3. Use **PowerShell** or double-click installers — not Git Bash (`$env:LOCALAPPDATA` is PowerShell syntax).

### Slow answers

- First startup loads the full model; later questions are faster while Dora stays open.
- Lower `llm_n_ctx` (e.g. `2048`) in config for slightly faster CPU inference.
- Set `llm_n_threads` to your CPU core count if `0` (auto) is slow.

### Re-run setup (re-download models)

```powershell
& "$env:LOCALAPPDATA\Dora\app\venv\Scripts\python.exe" "$env:LOCALAPPDATA\Dora\app\scripts\first_run_setup.py"
```

---

## Permissions (automatic — users do not edit this)

Dora creates `permissions.json` automatically. By default (`trust_mapped_apps: false`), Dora asks once by voice before opening each new app, then remembers your choice in `permissions.json`. You never need to edit that file by hand.

Set `trust_mapped_apps: true` in `config.json` only if you want apps found on your PC to open without that first voice confirmation (less strict, more convenient).

## Optional: Whisper speech engine

Default STT is Vosk (offline, included in the installer). For Whisper instead:

```powershell
pip install -e ".[whisper]"
```

Then set `"stt_engine": "whisper"` in `config.json`.

## For developers

See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture, mixin contracts, and PR guidelines.

```powershell
pip install -e ".[dev]"
pytest
ruff check core tests
mypy core
```

Configuration is typed in `core/config.py` (`DoraConfig`). Unknown keys are logged and ignored; invalid values fail at startup. Legacy `ollama_*` keys are migrated automatically.

Key settings:

| Key | Purpose |
|-----|---------|
| `wake_word` / `wake_phrases` | Wake detection |
| `chat_memory_turns` | Multi-turn chat context (default 4) |
| `trust_mapped_apps` | `false` = voice confirm per new app (default); `true` = auto-allow discovered apps |
| `stt_engine` | `vosk` (default) or `whisper` |
| `llm_model_path` | Local GGUF file |
| `warmup_llm_on_start` | Pre-load model at startup |

If you work on the source repo with git:

```powershell
git clone https://github.com/forexlord/dora.git
cd voice-assistant
.\Install-Dora.bat
```

Or manual dev setup:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .
$env:DORA_HOME = (Get-Location).Path
python scripts\first_run_setup.py
dora
```

### Publishing a release ZIP (maintainers)

Create a ZIP of the repo **without** `venv/`, `models/`, `.git/`, then attach to GitHub Releases as `Dora-windows.zip`. Users only need **`Install-Dora.bat`** + **`install.ps1`** + project files inside the ZIP.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Credits

**Dora** — Windows voice assistant  
**Recovery Eyo** — creator
