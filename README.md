# J.A.R.V.I.S. — Personal AI Desktop Assistant

A personal desktop AI assistant built with Python, designed to bring local AI conversations, voice interaction, browser control, and desktop automation into one application.

JARVIS uses a locally running Ollama model for AI-powered responses and provides a desktop interface for interacting with the assistant.

> **Project status:** Early development. Features and security controls are still being tested and improved.

## Features

- **Local AI conversations** — Uses Ollama with the `qwen2.5:3b` model.
- **Desktop interface** — A custom dark-themed Tkinter GUI.
- **Voice interaction** — Microphone input and spoken responses.
- **Variable-length recording** — Click **SPEAK**, then **STOP** when you're finished; recordings are capped at 60 seconds.
- **Browser control** — Opens Brave when available, with a default-browser fallback.
- **Web search** — Searches Google and YouTube.
- **Website shortcuts** — Opens commonly used websites.
- **Desktop automation** — Launches supported applications and opens common folders.
- **Safe arithmetic** — Evaluates basic mathematical expressions using a restricted calculator.
- **Security policy prototype** — A separate safeguards module defines allowed, approval-required, and blocked actions.
- **Unit tests** — Checks the security policy and action classification.

## Tech Stack

| Technology | Purpose |
|---|---|
| Python 3.10 | Core application |
| Tkinter | Desktop GUI |
| PySide6 | Animated orb interface |
| Ollama | Local AI inference |
| Qwen 2.5 3B | Language model |
| Whisper | Speech recognition |
| Edge TTS | Text-to-speech |
| Git and GitHub | Version control and project hosting |

## Project Structure

```text
jarvis/
├── main.py             # Desktop GUI and application controls
├── brain.py            # Command routing and AI integration
├── safeguards.py       # Security policy prototype
├── speech.py           # Speech recognition
├── speech_output.py    # Spoken responses
├── test_security.py    # Security policy tests
├── test_safeguards.py  # Additional safeguards tests
├── voice_test.py       # Voice testing
├── .gitignore          # Files excluded from Git
└── README.md           # Project documentation
```

## Requirements

- Windows 10 or Windows 11
- Python 3.10
- Ollama
- The required Python packages for speech recognition, audio playback, and text-to-speech
- A microphone for voice input
- An internet connection for web searches and online TTS services

JARVIS records from the Windows default microphone. Click **SPEAK** to start
recording and **STOP** to submit your command. The recording stops automatically
after 60 seconds if you do not press **STOP**.

## Getting Started

### 1. Install Ollama

Install Ollama from [ollama.com](https://ollama.com/).

Download the model used by JARVIS:

```powershell
ollama pull qwen2.5:3b
```

Make sure Ollama is running before launching the assistant.

### 2. Set up Python

Open a terminal in the project directory and verify Python:

```powershell
py -3.10 --version
```

Install the Python dependencies required by the project. The dependency list will be documented more precisely as development progresses.

### 3. Launch JARVIS

From the project directory, run:

```powershell
py -3.10 main.py
```

The desktop interface should open if the required dependencies are installed.

## Example Commands

Try commands such as:

- `hello`
- `what time is it`
- `calculate 25 * 4`
- `open calculator`
- `open GitHub`
- `search the web for Python tutorials`
- `search YouTube for music`
- `open Downloads`

Available commands depend on the current implementation and installed applications.

## Run the checks

From the project directory, run:

```powershell
py -3.10 -m unittest discover -v
```

The security checks use Python's test runner, so failures produce a non-zero exit code.

## Security

JARVIS includes an experimental safeguards module intended to classify actions as allowed, requiring approval, or blocked.

The current policy is an application-level control, **not a complete security sandbox**. Passing standalone policy tests does not establish that every action in the running application is protected.

Security improvements planned for future versions include:

- Enforcing policy checks at every action-execution point
- Validating action targets and restricting permissions
- Implementing genuine user approval flows for sensitive actions
- Expanding automated integration tests
- Improving error handling and security logging

Do not use the current prototype to handle sensitive information or perform unattended, high-impact actions.

## Roadmap

- [ ] Improve safeguards and integration tests
- [ ] Add a complete dependency and installation guide
- [ ] Improve speech recognition reliability
- [ ] Expand supported commands
- [ ] Add better conversation history management
- [ ] Document architecture and development decisions
- [ ] Add screenshots and demonstrations

## Copyright

Copyright © 2026 arhaansethi890-tech. All rights reserved.

This project is published for viewing and inspection. No general permission to reuse, modify, or redistribute the code is granted. See the project's copyright notice for details.

## Author

**GitHub:** [@arhaansethi890-tech](https://github.com/arhaansethi890-tech)

This project is under active development. Features, architecture, and documentation may change as it evolves.
