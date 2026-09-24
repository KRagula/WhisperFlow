# WhisperFree (WhisperFlow)

WhisperFree is a Windows-first desktop companion that turns push-to-talk speech into clean text ready to paste anywhere. Hold `CTRL+WIN` to capture audio, release to stop, and the OpenAI Whisper API handles transcription before WhisperFree pastes the result into the field that currently has focus. A minimal overlay shows recording status while a PyQt6 control panel manages microphones, service options, dictionary, and history.

Note: Currently supports Python 3.11 and Python 3.12. 

![Alt text](/assets/demo.png)

## Features
- Push-to-talk hotkey (`CTRL+WIN`) with debounce so recordings only begin when both keys are held and stop cleanly when released.
- OpenAI Whisper API backend with asynchronous transcription and toast feedback.
- Persistent transcription history with daily grouping and rolling word counts.
- Clipboard pipeline that copies the transcript, sends `Ctrl+V`, optionally presses `Enter`, and restores the previous clipboard.
- PyQt6 system tray UI with microphone selectors, gain control, API testing, and an always-on-top overlay that animates or collapses to a thin idle line.
- Voquill-style control panel with a sidebar and four pages:
  - **Home** - greeting, stat cards (total words, day streak, average words/min), and the 5 most recent transcriptions.
  - **History** - searchable, day-grouped history with a copy button per entry; large histories render lazily so the page stays responsive.
  - **Dictionary** - **Terms** are spelling hints (names, product words, acronyms) sent to Whisper as a prompt to improve recognition; **Replacements** are whole-word, case-insensitive "when I say X, paste Y" rules applied after transcription (a blank replacement removes the phrase entirely).
  - **Settings** - General, Audio, Transcription, and OpenAI sections. Toggles, microphone, gain, and language apply instantly; the API key requires Save (or a successful Test) before it is persisted.
- Launch on startup toggle (Settings -> General) that registers WhisperFree in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.


## Project Layout
```
whisperfree/
  README.md
  requirements.txt
  .env.example
  .gitignore
  run_whisperfree.pyw
  build.py
  whisperfree/
    __init__.py
    app.py
    config.py
    hotkeys.py
    audio.py
    transcribe.py
    paste.py
    overlay.py
    dictionary.py
    startup.py
    models.py
    ui/
      __init__.py
      theme.py
      window.py
      home.py
      history.py
      dictionary.py
      settings.py
      widgets.py
    utils/
      __init__.py
      levels_meter.py
      logger.py
  assets/
    app_icon.ico
  tests/
    ...
```

## Getting Started
1. **Install prerequisites**  
   Python 3.10-3.12, Git (optional). 
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
4. **Configure environment**  
   Copy `.env.example` to `.env` and set `OPENAI_API_KEY` to use the OpenAI Whisper or grammar APIs.
5. **Launch WhisperFree**
   ```powershell
   python -m whisperfree.app
   ```
   A tray icon appears; right-click to open settings or quit.

## Configuration Highlights
- **Microphone selector** - Populated from PortAudio; refresh to pick up devices that appear mid-session. Defaults back to the system device if the chosen device disappears.
- **OpenAI transcription** - Audio is sent to the OpenAI Whisper API for recognition.
- **Input gain slider** - Apply gain live to accommodate quieter microphones.
- **Overlay toggle** - Enable or hide the recording overlay without restarting the app.
- **Dictation sounds** - A rising two-note chime plays when you press the hotkey and a falling one when you release it. Turn it off with Settings -> General -> Play sounds.
- **Paste options** - Toggle `append newline after paste` and tune retry counts in the config file.
- **Dictionary** - Terms and replacement rules persist to `~/.whisperfree/dictionary.json`; edits from the Dictionary page save immediately, no restart required.
- **Launch on startup** - The Settings -> General toggle writes (or removes) the `WhisperFree` value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Running from source it launches `pythonw.exe run_whisperfree.pyw` from the repo root; a PyInstaller build launches the built executable directly.

Settings persist to `~/.whisperfree/config.json`. Edit this file directly if you need to script deployments; most values refresh the next time you open settings, but General/Audio/Transcription/OpenAI settings changes in the control panel apply instantly (the OpenAI API key is the exception - it needs Save or a successful Test before it is written to disk).

WhisperFree keeps its data under `~/.whisperfree/`:
- `config.json` - app settings
- `history.jsonl` - transcription history
- `dictionary.json` - dictionary terms and replacement rules
- `.env` - OpenAI API key (optional; a repo-root `.env` also works)
- `whisperfree.log` - application log

## Runtime Behaviour
1. Hold `CTRL+WIN` - the overlay animates and audio buffers at 16 kHz mono.
2. Release - WhisperFree stops recording, builds a WAV in memory, and sends it to the OpenAI Whisper API for transcription.
3. Paste - The recognized text is sent straight to the active window.
4. Paste - WhisperFree updates the clipboard, issues `Ctrl+V`, optionally presses `Enter`, and restores the previous clipboard contents.
5. Overlay returns to idle and a toast conveys success, fallbacks, or errors.

If an API call fails, WhisperFree surfaces a toast so you can retry once connectivity is restored. Microphone errors, silent recordings, and paste failures are surfaced non-intrusively with retries where sensible.

## Security & Privacy
- Audio is sent to the OpenAI Whisper API for transcription; recordings are held in memory only for the duration of the request.
- No recordings are saved by default (toggle the debug path in code if required).
- Clipboard contents are restored by default after pasting.
- API keys stay in environment variables; nothing secret is written to disk unless you choose to export it.

## Running Tests
```powershell
py -3.11 -m pytest tests -q
```

## Stretch Ideas
- Streaming partial captions while holding the hotkey.
- Cross-platform hotkey/paste layers.

## Troubleshooting
- **Missing microphone** - Choose "System Default" or refresh the list; WhisperFree falls back automatically when a named device vanishes.
- **API errors** - Verify `.env`.
- **Slow transcription** - Check network connectivity and OpenAI service status; API retries are surfaced via toast notifications.
