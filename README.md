# WhisperFree (WhisperFlow)

WhisperFree is a Windows-first desktop companion that turns push-to-talk speech into clean text ready to paste anywhere. Hold `CTRL+WIN` to record, release to stop, and OpenAI's transcription API (`gpt-transcribe` by default) turns your speech into text that WhisperFree pastes into whichever field has focus. A small overlay shows recording status, and a Voquill-style control panel manages your history, dictionary, and settings.

Note: Supports Python 3.11 and 3.12 on Windows.

![WhisperFree control panel](/assets/demo.png)

## Features
- **Push-to-talk** - hold `CTRL+WIN` to record and release to transcribe, with debounce so recording only starts when both keys are held.
- **Dictation sounds** - a rising two-note chime when you press the hotkey and a falling one when you release it.
- **OpenAI transcription** - `gpt-transcribe` by default; `gpt-4o-mini-transcribe` (cheapest) or legacy `whisper-1` can be picked in Settings.
- **Paste anywhere** - copies the transcript, sends `Ctrl+V`, optionally presses `Enter`, then restores your previous clipboard.
- **Control panel** with a sidebar and four pages:
  - **Home** - greeting, stat cards (total words, day streak, average words/min), and your 5 most recent transcriptions.
  - **History** - searchable, day-grouped history with a copy button per entry; large histories render lazily so the page stays responsive.
  - **Dictionary** - **Terms** are spelling hints (names, product words, acronyms) sent to the transcriber to improve recognition (as `keywords` for `gpt-transcribe`, as a glossary prompt for older models). **Replacements** are whole-word, case-insensitive "when I say X, paste Y" rules applied after transcription; a blank replacement removes the phrase entirely.
  - **Settings** - General, Audio, Transcription, and OpenAI sections.
- **Launch on startup** - optional; registers WhisperFree to start when you sign in to Windows.
- **Recording overlay** - an always-on-top indicator at the bottom of the screen that expands on hover and collapses to a thin line when idle.
- **Runs from the tray** - closing the control panel keeps WhisperFree running; quit from the tray icon.

## Getting Started
1. **Install prerequisites**
   Python 3.11 or 3.12, and Git (optional).
2. **Clone or download**
   ```powershell
   git clone https://github.com/KRagula/WhisperFlow.git
   cd WhisperFlow
   ```
3. **Create and activate a virtual environment**
   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
4. **Add your OpenAI API key**
   Either copy `.env.example` to `.env` and set `OPENAI_API_KEY`, or launch the app and paste the key into Settings -> OpenAI, then click **Test** or **Save key**.
5. **Launch WhisperFree**
   ```powershell
   python -m whisperfree.app
   ```
   A tray icon appears; right-click it to open the control panel or quit.

To build a standalone Windows executable, run `python build.py` (PyInstaller); the output goes to `dist/WhisperFree/`.

## Settings
Changes in the control panel apply immediately, with no Save button and no restart. The one exception is the API key, which is only stored after **Save key** or a successful **Test**, so a half-typed key is never saved.

- **General**
  - **Launch on startup** - writes (or removes) the `WhisperFree` value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Running from source it launches `pythonw.exe run_whisperfree.pyw` from the repo root; a PyInstaller build launches the built executable.
  - **Show recording overlay** - show or hide the on-screen indicator.
  - **Play sounds** - the press/release chimes.
  - **Press Enter after pasting** - append a newline after each transcription.
- **Audio**
  - **Microphone** - populated from PortAudio; **Refresh** picks up devices plugged in mid-session. If the chosen device disappears, WhisperFree falls back to the system default.
  - **Input gain** - boost or reduce microphone volume.
- **Transcription**
  - **Model** - `gpt-transcribe` (recommended, $0.0045/min), `gpt-4o-mini-transcribe` (cheapest, $0.003/min), or legacy `whisper-1` ($0.006/min). Configs still on the old `whisper-1` default are moved to `gpt-transcribe` automatically.
  - **Language** - auto-detect, or pin the language you speak.
- **OpenAI** - API key with **Show**, **Test**, and **Save key**.

Paste retry counts can be tuned in `config.json`.

## Where Your Data Lives
Everything stays under `~/.whisperfree/` on your machine:
- `config.json` - settings
- `history.jsonl` - transcription history (plain text)
- `dictionary.json` - dictionary terms and replacement rules
- `.env` - your OpenAI API key, if saved from the Settings page (a repo-root `.env` also works)
- `whisperfree.log` - application log

## How a Dictation Works
1. **Hold `CTRL+WIN`** - the start chime plays, the overlay switches to recording, and audio is captured at 16 kHz mono.
2. **Release** - recording stops, the stop chime plays, and the audio is packaged as a WAV in memory.
3. **Transcribe** - the WAV goes to the selected OpenAI model along with your dictionary terms.
4. **Clean up** - dictionary replacement rules are applied to the text.
5. **Paste** - WhisperFree puts the text on the clipboard, sends `Ctrl+V` (and `Enter` if enabled), then restores your previous clipboard.
6. **Record** - the entry is added to History and the Home stats update; the overlay returns to idle.

Failures such as no speech, API errors, or a paste that didn't go through show a short toast on the overlay instead of interrupting you.

## Security & Privacy
- Audio is sent to OpenAI for transcription and held in memory only for the duration of the request; recordings are never written to disk.
- Transcription history is stored locally as plain text in `~/.whisperfree/history.jsonl`. Delete the file to clear it.
- Your API key is read from the environment or a `.env` file. Saving it from the Settings page writes it to `~/.whisperfree/.env`. `.env` is git-ignored; never commit it.
- Clipboard contents are restored after each paste.

## Project Layout
```
WhisperFlow/
  README.md
  requirements.txt
  .env.example
  run_whisperfree.pyw     # windowless launcher used by Launch on startup
  build.py                # PyInstaller build
  assets/
    app_icon.ico
    demo.png
  whisperfree/
    app.py                # controller: hotkey -> record -> transcribe -> paste
    config.py             # settings + migrations
    models.py             # transcription models and languages
    hotkeys.py            # Ctrl+Win push-to-talk listener
    audio.py              # microphone capture
    sounds.py             # press/release chimes
    transcribe.py         # OpenAI transcription client
    dictionary.py         # terms + replacement rules
    history.py            # history store, streak and WPM stats
    paste.py              # clipboard + Ctrl+V
    startup.py            # Launch on startup (Windows Run key)
    overlay.py            # recording overlay
    ui/                   # control panel (theme, window, home, history, dictionary, settings, widgets)
    utils/                # logging, level metering
  tests/
```

## Running Tests
```powershell
py -3.11 -m pytest tests -q
```

## Troubleshooting
- **Nothing happens when I close the control panel** - that's expected; WhisperFree keeps running in the tray. Right-click the tray icon -> Quit to exit.
- **Missing microphone** - choose "System Default" or click Refresh; WhisperFree falls back automatically when a named device vanishes.
- **API errors** - open Settings -> OpenAI and click **Test** to check the key. If your account can't use the selected model, switch models in Settings -> Transcription.
- **Launch on startup doesn't start the app** - make sure WhisperFree isn't disabled in Task Manager -> Startup apps. Turning the toggle off and on again clears that flag.
- **Slow transcription** - check your network connection and OpenAI's service status.

## Stretch Ideas
- Streaming partial captions while holding the hotkey.
- Cross-platform hotkey and paste layers.
