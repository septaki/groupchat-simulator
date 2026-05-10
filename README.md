# GroupChat Simulator / 群友水群模拟器

Multi-Agent AI group chat powered by **DeepSeek API**. One webpage + one Python backend. Chat with multiple AI characters simultaneously in a single chat room — like a group chat with your AI friends.

基于 **DeepSeek API** 的多 AI 角色群聊。一个网页 + 一个 Python 后端，和多个 AI 角色在同一个聊天室里对话，就像和朋友水群一样。

## Demo

![screenshot](https://via.placeholder.com/800x400/1a1a2e/e0e0e0?text=GroupChat+Simulator+Screenshot)

## How It Works

```
Browser (index.html)
    ↕ WebSocket
Python (server.py)
    ↕ OpenAI-compatible API
DeepSeek API (deepseek-v4-pro / deepseek-v4-flash)
    ↕
Each agent = independent API call with its own system prompt
```

Each AI character is a separate DeepSeek API request with:
- Its own **system prompt** (from `setting.md`)
- **Conversation history** (shared chat log)
- **Tools**: read/write memory, send emotes, read setting files, update mood

## Prerequisites

1. **Python 3.9+** installed
2. A **DeepSeek API key** — get one at [platform.deepseek.com](https://platform.deepseek.com) (pricing: ~¥2 per million input tokens)

## Quick Start

### 1. Install dependencies

```bash
pip install fastapi uvicorn openai python-multipart
```

Or use the requirements file:

```bash
pip install -r chinese/requirements.txt
```

### 2. Set your API key

Open the server file for your language:

- **Chinese version**: `chinese/server.py`
- **English version**: `english/server.py`

Find line 55 and replace with your key:

```python
DEEPSEEK_KEY = "sk-your-deepseek-api-key-here"
```

### 3. (Optional) Choose your model

In the same file, you can pick:

```python
DEFAULT_MODEL = "deepseek-v4-pro"   # Full power, recommended
# DEFAULT_MODEL = "deepseek-v4-flash"  # Faster & cheaper
```

This can also be changed later in the settings panel.

### 4. Run

```bash
cd chinese   # or english
python server.py
```

Open `http://localhost:8000` in your browser.

**Windows users**: double-click `start.bat` instead.

### 5. Mobile access

On the same WiFi network, open the URL shown in the startup message (e.g. `http://192.168.x.x:8000`). Allow the Windows Firewall prompt on first access.

## Features

- **Multi-Agent Chat**: 1~N AI characters online simultaneously
- **Three Modes**:
  - Free Chat — all agents reply to you
  - Watch Mode — agents chat with each other, you spectate
  - RPG Mode — one agent becomes the Game Master, runs an adventure for you
- **Persona System**: Each agent has an independent directory with settings, memory, mood state, and emotes
- **Emote Stickers**: AI can send emote images (SVG defaults included, custom upload supported)
- **Conversation Management**: Sidebar with chat list, auto-save every 5 messages, switch between conversations
- **Full Visual Customization**: Bubble style/color/opacity, font size/color per agent, avatars (presets + custom crop), chat backgrounds, frame colors
- **Password Protection**: Optional access password for shared networks
- **Mobile Responsive**: Works on phone browsers with pinch-to-zoom image cropping

## Cost Estimate (DeepSeek API)

| Scenario | Tokens per round | Cost |
|---|---|---|
| You + 2 agents reply | ~5,000 | ~¥0.01 |
| Watch mode (4 rounds × 2 agents) | ~15,000 | ~¥0.04 |
| RPG session (10 rounds) | ~40,000 | ~¥0.10 |
| Heavy evening chat (~100 exchanges) | ~300,000 | ~¥0.60 |

DeepSeek is ~10-30× cheaper than comparable APIs. You can also switch agents offline in settings to save costs.

## Customization

### Adding a new agent

Create a directory under `agents/` with a `setting.md`:

```
agents/my-character/
  setting.md
  emotes/          (optional)
```

`setting.md` format:

```
color: #f472b6     # bubble color (hex)
avatar: 🌸          # avatar emoji

# Character Name — Brief Description

## Identity
Who you are...

## Personality
How you behave...

## Voice
How you speak...

## Rules
1. Never mention AI/LLM
2. Never mention money amounts
```

Restart the server. The new agent appears automatically.

### Changing emotes

Replace the `.svg` files in `agents/{name}/emotes/`, or use the settings panel to upload custom images (gif/png/jpg supported). Supported moods: happy, sad, shy, angry, surprised, cute, love, thinking.

### Adding detailed setting files

You can add these optional files to any agent directory (readable by the agent via the `read_setting_file` tool):

- `detailed-setting.txt` — expanded persona
- `about-user.txt` — information about the user
- `backstory.txt` — shared history
- `instructions.txt` — behavioral rules
- `nsfw-diary.txt` — intimate content (loaded only in NSFW mode)

## Versions

| Folder | UI Language | AI Prompt Language |
|---|---|---|
| `chinese/` | 🇨🇳 Chinese | Chinese |
| `english/` | 🇬🇧 English | Chinese (AI characters speak Chinese) |

Both are functionally identical.

## Project Structure

```
├── README.md
├── chinese/                  # 🇨🇳 Chinese UI version
│   ├── server.py             # Backend (FastAPI + WebSocket)
│   ├── index.html            # Frontend (single-file, zero deps)
│   ├── generate_emotes.py    # Default emote SVG generator
│   ├── start.bat             # Windows launcher
│   ├── stop.bat              # Server killer
│   └── agents/
│       ├── agent-1/          # Each agent is a directory
│       │   ├── setting.md    # Persona (loaded as system prompt)
│       │   └── emotes/       # Emote images (SVG/PNG/GIF)
│       ├── agent-2/
│       └── agent-3/
├── english/                  # 🇬🇧 English UI version
│   └── ... (same structure)
```

Runtime files (auto-generated, git-ignored):
- `settings.json` — global config
- `conversations/` — chat archives
- `memory.md` / `state.md` — per-agent, auto-maintained

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.9+, FastAPI, WebSocket |
| AI | DeepSeek API (OpenAI-compatible endpoint) |
| Frontend | Vanilla HTML + CSS + JavaScript (zero npm dependencies) |
| Storage | JSON files + browser localStorage |

## Troubleshooting

**"The supported API model names are deepseek-v4-pro or deepseek-v4-flash"**
→ You're using an outdated model name. Go to Settings → Global → Model and select `deepseek-v4-pro` or `deepseek-v4-flash`.

**Agents not replying**
→ Check the Settings panel → Agent Toggle. Make sure agents are switched "Online".

**Mobile keyboard covers input bar**
→ This is a known issue with some Android browsers (e.g. Via). WeChat and Edge work correctly.

**Port 8000 already in use**
→ Run `stop.bat` (Windows) or `taskkill /IM python.exe /F` to kill the old server.

## License

MIT — feel free to use, modify, and distribute.
