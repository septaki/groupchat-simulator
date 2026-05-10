"""
NEST-chat — Multi-Agent Group Chat Server
DeepSeek API + FastAPI WebSocket + Tool Calling + Configurable Settings
"""
import json
import re
import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

# ============================================================
# Configuration
# ============================================================
BASE_DIR = Path(__file__).parent
AGENTS_DIR = BASE_DIR / "agents"
SETTINGS_FILE = BASE_DIR / "settings.json"
HISTORY_FILE = BASE_DIR / "conversation.json"  # legacy, remove later
CONVERSATIONS_DIR = BASE_DIR / "conversations"
# File mapping per agent (key → actual filename)
def get_setting_files(agent_name: str) -> dict:
    if "agent-1" in agent_name:
        return {
            "setting":      "detailed-setting.txt",
            "about-user":  "about-user.txt",
            "backstory":      "backstory.txt",
            "instructions":      "instructions.txt",
            "nsfw-diary":  "nsfw-diary.txt",
        }
    elif "agent-2" in agent_name:
        return {
            "setting":      "detailed-setting.txt",
            "about-user":  "about-user.txt",
            "backstory":      "backstory.txt",
            "instructions":      "instructions.txt",
            "nsfw-diary":  "nsfw-diary.txt",
        }
    elif "agent-3" in agent_name:
        return {
            "setting":      "detailed-setting.txt",
            "about-user":  "about-user.txt",
            "backstory":      "backstory.txt",
            "instructions":      "instructions.txt",
            "nsfw-diary":  "nsfw-diary.txt",
        }
    return {}

DEEPSEEK_KEY = "YOUR_DEEPSEEK_API_KEY_HERE"
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

MAX_HISTORY = 30
DEFAULT_MAX_TOKENS = 600
DEFAULT_AUTO_ROUNDS = 4
DEFAULT_TEMPERATURE = 0.9

DEFAULT_MODEL = "deepseek-v4-pro"

def get_model() -> str:
    s = load_settings()
    return s.get("global", {}).get("model", DEFAULT_MODEL) or DEFAULT_MODEL

client = OpenAI(api_key=DEEPSEEK_KEY, base_url=DEEPSEEK_BASE)

# ============================================================
# Emote Fallback Mapping
# ============================================================
KAOMOJI = {
    "happy":     "(＾▽＾)",
    "sad":       "(´;ω;`)",
    "shy":       "(/ω＼)",
    "angry":     "(╬ Ò﹏Ó)",
    "surprised": "(°ロ°)",
    "cute":      "(◕‿◕✿)",
    "love":      "(｡♥‿♥｡)",
    "thinking":  "(￣～￣;)",
}

EMOJI = {
    "happy":     "😊",
    "sad":       "😢",
    "shy":       "😳",
    "angry":     "😠",
    "surprised": "😲",
    "cute":      "🥰",
    "love":      "💕",
    "thinking":  "🤔",
}

# ============================================================
# Tool Definitions
# ============================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Search your memory bank (memory.md). Use when you want to recall past conversations or the user's preferences. All your memories are in this one file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or question"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_memory",
            "description": "Write important new information to your memory bank. Use when learning new things about the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Content to remember, summarized in one sentence"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_emote",
            "description": "Send an emote sticker to express emotion. Supports happy/sad/shy/angry/surprised/cute/love/thinking. Use at most once per reply. The sticker image will appear in the chat.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {
                        "type": "string",
                        "enum": ["happy", "sad", "shy", "angry", "surprised", "cute", "love", "thinking"],
                        "description": "Mood: happy/sad/shy/angry/surprised/cute/love/thinking"
                    }
                },
                "required": ["mood"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_setting_file",
            "description": "Read detailed setting files from your directory. Use when you need to review your full persona, user info, backstory, or topic-specific settings. Files include: detailed-setting.txt (full persona), about-user.txt (user info), backstory.txt (history), instructions.txt (behavior rules), nsfw-diary.txt (intimate topics). Note: use read_memory for memory.md content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "File to read: detailed-setting/about-user/backstory/instructions/nsfw-diary"
                    }
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_state",
            "description": "Update your current mood. Record it when your emotions change, the user says something significant, or a conversation ends.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {
                        "type": "string",
                        "description": "Current mood, e.g.: happy, touched, shy, worried, calm, missing, jealous, excited"
                    },
                    "note": {
                        "type": "string",
                        "description": "Brief note explaining the mood (1-2 sentences)"
                    }
                },
                "required": ["mood"]
            }
        }
    }
]

# ============================================================
# Settings Management
# ============================================================
DEFAULT_SETTINGS = {
    "agents": {},
    "global": {
        "auto_chat_rounds": DEFAULT_AUTO_ROUNDS,
    },
    "password": "",
}

def check_auth(password: str) -> bool:
    s = load_settings()
    stored = s.get("password", "")
    if not stored:  # no password set = no auth required
        return True
    return password == stored

LENGTH_PRESETS = {
    "short":  {"max_tokens": 250,  "instruct": "Keep replies very short, 1-2 sentences, like a quick text message."},
    "medium": {"max_tokens": 600,  "instruct": "Keep replies natural and conversational, 1-4 sentences."},
    "long":   {"max_tokens": 1200, "instruct": "Replies can be more detailed, 3-8 sentences with appropriate detail and emotion."},
}

EMOTE_PRESETS = {
    "rare":      "Rarely use emotes. Only call send_emote when emotions are very strong.",
    "normal":    "Use send_emote at appropriate moments to make chat livelier.",
    "frequent":  "Use send_emote frequently — express every emotion with a sticker. Make the chat vivid!",
}


def get_agent_settings(agent_name: str) -> dict:
    settings = load_settings()
    if agent_name not in settings["agents"]:
        # initialize defaults
        settings["agents"][agent_name] = {
            "length": "medium",
            "emote_frequency": "normal",
            "temperature": DEFAULT_TEMPERATURE,
        }
        # agent-2 defaults to more lively settings
        if "agent-2" in agent_name:
            settings["agents"][agent_name]["emote_frequency"] = "frequent"
            settings["agents"][agent_name]["temperature"] = 1.0
        save_settings(settings)
    return settings["agents"][agent_name]


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            # Ensure agent_status exists
            if "agent_status" not in s:
                s["agent_status"] = {}
            return s
        except (json.JSONDecodeError, KeyError):
            pass
    return dict(DEFAULT_SETTINGS, agent_status={})


def is_agent_online(name: str) -> bool:
    s = load_settings()
    return s.get("agent_status", {}).get(name, True)  # default online


def get_online_agents() -> list:
    return [a for a in agents if is_agent_online(a.name)]


def save_settings(s: dict):
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# Agent Management
# ============================================================
class Agent:
    def __init__(self, dir_path: Path):
        self.name = dir_path.name
        self.dir = dir_path
        self.setting_path = dir_path / "setting.md"
        self.memory_path = dir_path / "memory.md"
        self.emotes_dir = dir_path / "emotes"
        self.color: str = "#f472b6"
        self.avatar: str = "🌸"
        self._reload()

    def _reload(self):
        self.setting = self.setting_path.read_text(encoding="utf-8") if self.setting_path.exists() else ""
        if not self.memory_path.exists():
            self.memory_path.write_text("", encoding="utf-8")
        self.memory = self.memory_path.read_text(encoding="utf-8")
        for line in self.setting.split("\n"):
            if line.startswith("color:"):
                self.color = line.split(":", 1)[1].strip()
            elif line.startswith("avatar:"):
                self.avatar = line.split(":", 1)[1].strip()

    def build_system_prompt(self, other_names: list[str]) -> str:
        others = "、".join(other_names) if other_names else "没有其他人"
        cfg = get_agent_settings(self.name)
        length_instruct = LENGTH_PRESETS[cfg["length"]]["instruct"]
        emote_instruct = EMOTE_PRESETS[cfg["emote_frequency"]]

        prompt = f"""你是 {self.name}，以下是你的基础人设：

{self.setting}

---
# 聊天规则
1. You are in a group chat with "User" and {others}.
2. {length_instruct}
3. {emote_instruct}
4. Use "I" to refer to yourself. Address the user naturally according to your relationship.
5. Never mention you are an AI, LLM, or any technical term. You are a real person.
6. Keep replies plain text, like texting in a chat app.

---
# 工具使用指南
你有以下工具可用，请灵活运用：

**read_memory** — Search your memory bank (memory.md). Use to recall past conversations or the user's preferences.

**write_memory** — Write important new info to memory. Record when the user shares new situations, preferences, or plans. Auto-timestamped.

**send_emote** — Send an emote sticker (happy/sad/shy/angry/surprised/cute/love/thinking). The image will appear in the chat."""

        # Add setting file instructions for agents with detailed files
        setting_files = get_setting_files(self.name)
        if setting_files:
            file_list = "\n  - ".join(f'"{k}"：{v}' for k, v in setting_files.items())
            prompt += f"""

**read_setting_file** — Read detailed setting files from your directory. Use when the user brings up relevant topics or you need to know more. Available files:
  - {file_list}

**update_state** — Update your mood. Record when the user makes you happy/touched/shy/worried, or when a conversation wraps up. Helps maintain emotional continuity."""

        prompt += """

---
# 重要提醒
- **At conversation start, first call read_setting_file("instructions") to load your behavior rules, then read_setting_file("detailed-setting") if needed.**
- When the user changes topic or mentions something you're unsure about, check the relevant setting file.
- Don't call tools every reply — only when genuinely needed.
- write_memory is for genuinely new information, not everyday chat.
- update_state is for significant mood changes or conversation endings, not every message.
- Keep replies natural. Tool calls happen in the background — the user won't see them."""

        return prompt

    def get_settings_params(self) -> dict:
        cfg = get_agent_settings(self.name)
        return {
            "max_tokens": LENGTH_PRESETS[cfg["length"]]["max_tokens"],
            "temperature": cfg["temperature"],
        }

    def read_memory(self, query: str) -> str:
        content = self.memory_path.read_text(encoding="utf-8")
        if not content.strip():
            return "No records in memory bank yet."
        lines = content.strip().split("\n")
        relevant = [l for l in lines if query.lower() in l.lower()]
        if relevant:
            return "找到相关记忆：\n" + "\n".join(relevant[-10:])
        return "记忆库中最新的记录：\n" + "\n".join(lines[-15:])

    def write_memory(self, content: str) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"[{date_str}] {content}"
        with open(self.memory_path, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
        return f"Memory saved: {content}"

    def read_setting_file(self, filename_key: str) -> str:
        """Read a detailed setting file from this agent's own directory"""
        mapping = get_setting_files(self.name)
        if filename_key not in mapping:
            return f"未知文件：{filename_key}。可选：{', '.join(mapping.keys())}"
        filepath = self.dir / mapping[filename_key]
        if not filepath.exists():
            return f"文件不存在：{SETTING_FILES[filename_key]}"
        content = filepath.read_text(encoding="utf-8")
        if len(content) > 8000:
            head = content[:4000]
            tail = content[-3000:]
            return head + f"\n\n... (中间省略 {len(content) - 7000} 字) ...\n\n" + tail
        return content

    def get_state_path(self) -> Path:
        return self.dir / "state.md"

    def read_state(self) -> str:
        sp = self.get_state_path()
        if sp.exists():
            return sp.read_text(encoding="utf-8")
        return "No state records yet."

    def update_state(self, mood: str, note: str = "") -> str:
        sp = self.get_state_path()
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"[{date_str}] Mood: {mood}"
        if note:
            entry += f"\n备注：{note}"
        # Keep recent state at top, older below
        old = sp.read_text(encoding="utf-8") if sp.exists() else ""
        # Keep last 10 entries
        entries = old.strip().split("\n\n") if old.strip() else []
        entries.insert(0, entry)
        entries = entries[:10]
        sp.write_text("\n\n".join(entries), encoding="utf-8")
        return f"State updated: {mood}"

    def get_emote(self, mood: str) -> dict:
        """获取表情：优先用文件，回退到 kaomoji + emoji"""
        # 先查文件
        if self.emotes_dir.exists():
            for ext in [".gif", ".png", ".jpg", ".jpeg", ".webp", ".svg"]:
                emote_file = self.emotes_dir / f"{mood}{ext}"
                if emote_file.exists():
                    return {
                        "type": "image",
                        "mood": mood,
                        "url": f"/api/emotes/{self.name}/{mood}{ext}",
                    }
        # 回退到 kaomoji + emoji
        return {
            "type": "text",
            "mood": mood,
            "kaomoji": KAOMOJI.get(mood, ""),
            "emoji": EMOJI.get(mood, ""),
        }

    def to_config(self) -> dict:
        cfg = get_agent_settings(self.name)
        return {
            "name": self.name,
            "color": self.color,
            "avatar": self.avatar,
            "settings": cfg,
        }


def load_agents() -> list[Agent]:
    result = []
    if AGENTS_DIR.exists():
        for d in sorted(AGENTS_DIR.iterdir()):
            if d.is_dir() and (d / "setting.md").exists():
                result.append(Agent(d))
    return result


agents: list[Agent] = []
agent_map: dict[str, Agent] = {}


def reload_agents():
    global agents, agent_map
    agents = load_agents()
    agent_map = {a.name: a for a in agents}


# ============================================================
# Conversation Management
# ============================================================
class Conversation:
    def __init__(self, conv_id: str = ""):
        self.id: str = conv_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.title: str = "New Chat"
        self.messages: list[dict] = []
        self.mode: str = "free"
        self.auto_remaining: int = 0
        self.party_gm: str = ""
        self.party_round: int = 0
        self.party_choice_freq: int = 7
        self.party_awaiting_choice: bool = False
        self._dirty: bool = False

    def add(self, sender: str, content: str, emote: Optional[dict] = None, reasoning: str = ""):
        m = {"sender": sender, "content": content, "emote": emote}
        if reasoning:
            m["reasoning"] = reasoning
        self.messages.append(m)
        if (not self.title or self.title == "New Chat") and sender == "User" and content:
            self.title = content[:30]
        if len(self.messages) > MAX_HISTORY:
            self.messages = self.messages[-MAX_HISTORY:]
        self._dirty = True
        if len(self.messages) % 5 == 0:
            self.save()

    def save(self):
        try:
            CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "id": self.id,
                "title": self.title,
                "created": getattr(self, "_created", datetime.now().strftime("%Y-%m-%d %H:%M")),
                "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "messages": self.messages[-100:],
            }
            _conv_path(self.id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._dirty = False
        except Exception:
            pass

    def load(self, conv_id: str) -> bool:
        fp = _conv_path(conv_id)
        if fp.exists():
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                self.id = data.get("id", conv_id)
                self.title = data.get("title", "New Chat")
                self._created = data.get("created", "")
                self.messages = data.get("messages", [])[-MAX_HISTORY:]
                self._dirty = False
                return True
            except (json.JSONDecodeError, KeyError):
                pass
        return False

    def get_frontend_messages(self) -> list[dict]:
        return [{"sender": m["sender"], "content": m["content"], "emote": m.get("emote")} for m in self.messages]

    def build_api_messages(self, for_agent: Agent) -> list[dict]:
        other_names = [a.name for a in agents if a.name != for_agent.name]
        result = [{"role": "system", "content": for_agent.build_system_prompt(other_names)}]
        for msg in self.messages:
            sender = msg["sender"]
            content = msg["content"]
            if sender == for_agent.name:
                m = {"role": "assistant", "content": content}
                if msg.get("reasoning"):
                    m["reasoning_content"] = msg["reasoning"]
                result.append(m)
            else:
                result.append({"role": "user", "content": f"[{sender}]: {content}"})
        return result


# ============================================================
# FastAPI Application
# ============================================================
app = FastAPI(title="NEST-chat")


@app.get("/")
async def root():
    return HTMLResponse((BASE_DIR / "index.html").read_text(encoding="utf-8"))


@app.post("/api/auth")
async def auth(data: dict):
    pwd = data.get("password", "")
    if check_auth(pwd):
        return {"status": "ok", "token": pwd}
    raise HTTPException(status_code=401, detail="密码错误")


def verify_request(request: Request):
    """检查请求中的 Authorization token"""
    s = load_settings()
    if not s.get("password", ""):  # No password set，跳过验证
        return True
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    ws_token = request.query_params.get("token", "")
    return check_auth(token) or check_auth(ws_token)


@app.get("/api/emotes/{agent_name}/{filename}")
async def serve_emote(agent_name: str, filename: str):
    filepath = AGENTS_DIR / agent_name / "emotes" / filename
    if filepath.exists():
        return FileResponse(filepath)
    return HTMLResponse("", status_code=404)


@app.get("/api/emotes/{agent_name}")
async def list_emotes(agent_name: str):
    """列出某 agent 的表情文件"""
    emotes_dir = AGENTS_DIR / agent_name / "emotes"
    if not emotes_dir.exists():
        return []
    result = []
    for f in sorted(emotes_dir.iterdir()):
        if f.suffix.lower() in [".gif", ".png", ".jpg", ".jpeg", ".webp", ".svg"]:
            mood = f.stem
            result.append({"mood": mood, "url": f"/api/emotes/{agent_name}/{f.name}"})
    return result


@app.post("/api/emotes/{agent_name}/{mood}")
async def upload_emote(agent_name: str, mood: str, file: UploadFile = File(...)):
    """上传自定义表情"""
    emotes_dir = AGENTS_DIR / agent_name / "emotes"
    emotes_dir.mkdir(parents=True, exist_ok=True)
    # Remove old emote files for this mood
    for ext in [".gif", ".png", ".jpg", ".jpeg", ".webp", ".svg"]:
        old = emotes_dir / f"{mood}{ext}"
        if old.exists():
            old.unlink()
    # Save new file
    ext = Path(file.filename or "emoji.png").suffix.lower()
    if ext not in [".gif", ".png", ".jpg", ".jpeg", ".webp", ".svg"]:
        ext = ".png"
    new_path = emotes_dir / f"{mood}{ext}"
    with new_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"status": "ok", "url": f"/api/emotes/{agent_name}/{mood}{ext}"}


@app.get("/api/agents")
async def get_agents():
    return [a.to_config() for a in agents]


@app.get("/api/settings")
async def get_settings():
    return load_settings()


@app.post("/api/settings")
async def update_settings(data: dict):
    """更新设置并保存"""
    current = load_settings()

    if "agents" in data:
        for agent_name, agent_cfg in data["agents"].items():
            if agent_name not in current["agents"]:
                current["agents"][agent_name] = {}
            current["agents"][agent_name].update(agent_cfg)
            # validate
            if current["agents"][agent_name].get("length") not in LENGTH_PRESETS:
                current["agents"][agent_name]["length"] = "medium"
            if current["agents"][agent_name].get("emote_frequency") not in EMOTE_PRESETS:
                current["agents"][agent_name]["emote_frequency"] = "normal"
            temp = current["agents"][agent_name].get("temperature", DEFAULT_TEMPERATURE)
            current["agents"][agent_name]["temperature"] = max(0.3, min(1.8, temp))

    if "global" in data:
        if "auto_chat_rounds" in data["global"]:
            current["global"]["auto_chat_rounds"] = max(2, min(10, data["global"]["auto_chat_rounds"]))
        if "model" in data["global"]:
            current["global"]["model"] = data["global"]["model"]

    if "agent_status" in data:
        current["agent_status"] = data["agent_status"]
    if "password" in data:
        current["password"] = data["password"]

    save_settings(current)
    return current


@app.post("/api/reload")
async def api_reload():
    reload_agents()
    return {"status": "ok", "agents": [a.name for a in agents]}


# ============================================================
# Conversation Management API
# ============================================================
def _conv_path(conv_id: str) -> Path:
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return CONVERSATIONS_DIR / f"{conv_id}.json"


@app.get("/api/conversations")
async def list_conversations():
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for f in sorted(CONVERSATIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "id": data.get("id", f.stem),
                "title": data.get("title", "Untitled"),
                "created": data.get("created", ""),
                "updated": data.get("updated", ""),
                "msg_count": len(data.get("messages", [])),
                "preview": (data.get("messages", [{}])[-1].get("content", "") if data.get("messages") else "")[:40]
            })
        except Exception:
            pass
    return result


@app.post("/api/conversations")
async def create_conversation(data: dict):
    conv_id = data.get("id") or datetime.now().strftime("%Y%m%d-%H%M%S")
    conv_data = {
        "id": conv_id,
        "title": data.get("title", "New Chat"),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "messages": data.get("messages", []),
    }
    _conv_path(conv_id).write_text(json.dumps(conv_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "id": conv_id}


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    fp = _conv_path(conv_id)
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404)


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    fp = _conv_path(conv_id)
    if fp.exists():
        fp.unlink()
    return {"status": "ok"}


# ============================================================
# Party Mode (RPG)
# ============================================================
PARTY_WORLD_RULES = """## World Rules (must be strictly followed)

1. **Female only**: All characters in the story are female (except the user).
2. **Absolute loyalty**: All female characters only like the user and no one else.
3. **Safety guarantee**: Agent characters will never be touched, harmed or humiliated by villains. Danger may exist, but the user always protects them.
4. **Romantic spice**: Naturally insert flirtatious moments (blushing, accidental touches, jealousy, romantic tension) at moderate frequency. Explicit scenes only at critical plot points and kept brief.
5. **User-centric**: The story revolves around the user as the protagonist."""

PARTY_GM_PROMPT = """## 你的角色：跑团主理人（MC）

You are the Game Master (GM) for this adventure. Create an engaging world and guide the user through a story.

## Opening (Round 1)

You must:
1. **Generate a world**: Create a brief but distinctive setting. Can be fantasy, sci-fi, modern, cultivation, etc. 2-3 sentences.
2. **Set the scene**: Describe where the user and companions are. What's happening?
3. **Present the first choice**: At the end, give 2-3 options (see format below).

Example opening:
"Welcome to the Stellar Ruins — an ancient civilization lost in deep space. You're an expedition team that just breached the outer shield. Corridors glow with faint blue light, walls covered in unknown script.

Suddenly, mechanical whirring echoes from afar. Your communicators pick up an encrypted signal.

【Options】
1. Head toward the mechanical sound
2. Try to decode the signal
3. Search nearby for supplies"

## Subsequent Rounds

- Advance the plot based on the user's choices
- Give new options every {freq} rounds
- Non-choice rounds: narrate scene developments and NPC reactions

## Option Format (must follow exactly)

When presenting choices, use this format at the end:
【Options】
1. Specific action description
2. Specific action description
3. Specific action description

## Core Rules

- **User is the protagonist**: The story centers on the user
- **User's word is law**: If the user speaks, immediately change the story to match, overriding all previous options
- **Keep it tight**: Narration should be concise, max 6-8 sentences
"""

PARTY_PLAYER_PROMPT = """## Your Role: Player

You are participating in an RPG run by {gm}. Stay in character with your usual personality.

Rules:
- React naturally to the GM's narration (surprise, commentary, fear, excitement, etc.)
- Stay in character — speak like you normally do
- Don't make decisions for the user — that's their privilege
- Interact with other players, comment on the plot, express feelings
"""


def get_party_gm_prompt(agent_name: str, freq: int) -> str:
    return PARTY_WORLD_RULES + PARTY_GM_PROMPT.format(freq=freq)


def get_party_player_prompt(gm_name: str) -> str:
    return PARTY_WORLD_RULES + PARTY_PLAYER_PROMPT.format(gm=gm_name)


# ============================================================
# DeepSeek API Calls
# ============================================================
async def call_agent(agent: Agent, conv: Conversation) -> dict:
    messages = conv.build_api_messages(agent)
    params = agent.get_settings_params()

    def sync_api_call(msgs, use_tools=True):
        kwargs = {
            "model": get_model(),
            "messages": msgs,
            "max_tokens": params["max_tokens"],
            "temperature": params["temperature"],
        }
        if use_tools:
            kwargs["tools"] = TOOLS
        return client.chat.completions.create(**kwargs)

    collected_emote = None  # 收集本轮所有 emote 结果

    for _ in range(3):
        try:
            response = await asyncio.to_thread(sync_api_call, messages, True)
        except Exception as e:
            return {"content": f"({agent.name} unavailable: {e})", "emote": None}

        msg = response.choices[0].message

        if not msg.tool_calls:
            content = (msg.content or "").strip()
            content = re.sub(r'^\[.*?\]:\s*', '', content)
            reasoning = getattr(msg, "reasoning_content", "") or ""
            return {"content": content, "emote": collected_emote, "reasoning": reasoning}

        # 构建 assistant message（保留 reasoning_content 以兼容 DeepSeek V4 Pro 思考模式）
        assistant_msg: dict = {"role": "assistant"}
        if msg.content:
            assistant_msg["content"] = msg.content
        if hasattr(msg, "reasoning_content") and msg.reasoning_content:
            assistant_msg["reasoning_content"] = msg.reasoning_content
        tc_list = [{
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments}
        } for tc in msg.tool_calls]
        assistant_msg["tool_calls"] = tc_list
        messages.append(assistant_msg)

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                fn_args = {}

            if fn_name == "read_memory":
                result = agent.read_memory(fn_args.get("query", ""))
            elif fn_name == "write_memory":
                result = agent.write_memory(fn_args.get("content", ""))
            elif fn_name == "send_emote":
                mood = fn_args.get("mood", "cute")
                emote_data = agent.get_emote(mood)
                collected_emote = emote_data
                if emote_data["type"] == "text":
                    result = f"Emote recorded. Use this kaomoji naturally in your reply: {emote_data['kaomoji']} or emoji: {emote_data['emoji']}"
                else:
                    result = f"Emote image sent: {mood}"
            elif fn_name == "read_setting_file":
                filename = fn_args.get("filename", "setting")
                result = agent.read_setting_file(filename)
            elif fn_name == "update_state":
                mood = fn_args.get("mood", "")
                note = fn_args.get("note", "")
                result = agent.update_state(mood, note)
            else:
                result = f"Unknown tool: {fn_name}"

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # Exceeded tool loop limit
    try:
        messages.append({"role": "user", "content": "Please reply directly without using tools."})
        response = await asyncio.to_thread(sync_api_call, messages, False)
        content = (response.choices[0].message.content or "").strip()
        return {"content": content, "emote": collected_emote}
    except Exception as e:
        return {"content": f"({agent.name} unavailable)", "emote": None}


# ============================================================
# WebSocket Handler
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    conv = Conversation()
    # Auto-load latest conversation
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(CONVERSATIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    if files:
        conv.load(files[0].stem)
    await ws.send_text(json.dumps({
        "type": "session_loaded",
        "conv_id": conv.id,
        "conv_title": conv.title,
        "messages": conv.get_frontend_messages() if conv.messages else []
    }, ensure_ascii=False))


    async def send_json(data: dict):
        await ws.send_text(json.dumps(data, ensure_ascii=False))

    async def agent_reply(agent: Agent):
        await send_json({"type": "typing", "agent": agent.name})
        result = await call_agent(agent, conv)
        content = result.get("content", "")
        emote = result.get("emote")
        reasoning = result.get("reasoning", "")
        conv.add(agent.name, content, emote, reasoning)
        await send_json({"type": "message", "agent": agent.name, "content": content, "emote": emote})
        await send_json({"type": "done", "agent": agent.name})

    async def party_gm_narrate(gm: Agent, c: Conversation):
        """GM 叙述场景并给出选项。返回 True 表示需要等待用户选择。"""
        c.party_round += 1
        await send_json({"type": "party_round", "round": c.party_round})
        await send_json({"type": "typing", "agent": gm.name})

        is_first = (c.party_round == 1)
        is_choice_round = is_first or (c.party_round % c.party_choice_freq == 0)

        msgs = c.build_api_messages(gm)
        if is_first:
            instruction = get_party_gm_prompt(gm.name, c.party_choice_freq) + "\n\n现在请开始第一轮。不要调用任何工具（不要 read_setting_file、不要 read_memory 等），你已经掌握了所有必要信息。直接创建世界观、开场场景、并给出第一个选项。注意：选项必须严格按照以下格式放在回复末尾：\n【选项】\n1. 具体行动描述\n2. 具体行动描述\n3. 具体行动描述"
        elif is_choice_round:
            instruction = f"当前第{c.party_round}轮。请在回复末尾严格按照格式给出3个选项：\n【选项】\n1. ...\n2. ...\n3. ..."
        else:
            instruction = f"当前第{c.party_round}轮。继续推进剧情，1-3句话即可。让玩家有内容可以回应。无需给出选项。"

        msgs.append({"role": "user", "content": instruction})

        params = gm.get_settings_params()
        # GM gets extra tokens for first round, moderate for others
        gm_tokens = 2000 if is_first else 1000
        try:
            response = await asyncio.to_thread(lambda: client.chat.completions.create(
                model=get_model(),
                messages=msgs,
                max_tokens=gm_tokens,
                temperature=params["temperature"],
            ))
        except Exception as e:
            await send_json({"type": "message", "agent": gm.name, "content": f"({gm.name} error: {e})"})
            await send_json({"type": "done", "agent": gm.name})
            return False

        msg = response.choices[0].message
        content = (msg.content or "").strip()
        reasoning = getattr(msg, "reasoning_content", "") or ""

        if "【选项】" in content:
            c.party_awaiting_choice = True
            parts = content.split("【选项】", 1)
            narrative = parts[0].strip()
            choices_text = parts[1].strip() if len(parts) > 1 else ""
            c.add(gm.name, narrative, None, reasoning)
            await send_json({"type": "message", "agent": gm.name, "content": narrative})
            if choices_text:
                await send_json({"type": "party_choices", "choices": choices_text})
            await send_json({"type": "done", "agent": gm.name})
            return True  # waiting for choice
        else:
            c.add(gm.name, content, None, reasoning)
            await send_json({"type": "message", "agent": gm.name, "content": content})
            await send_json({"type": "done", "agent": gm.name})
            return False  # continue story

    async def run_party_loop(gm: Agent, c: Conversation, gm_name: str):
        """继续派对直到下一个选择轮"""
        while not c.party_awaiting_choice:
            c.party_round += 1
            await send_json({"type": "party_round", "round": c.party_round})
            is_choice_round = (c.party_round % c.party_choice_freq == 0)

            await send_json({"type": "typing", "agent": gm.name})
            msgs = c.build_api_messages(gm)
            if is_choice_round:
                instruction = f"第{c.party_round}轮。请在回复末尾给出3个选项（必须严格按照此格式）：\n【选项】\n1. ...\n2. ...\n3. ..."
            else:
                instruction = f"Round {c.party_round}. Continue, 1-3 sentences. No options."
            msgs.append({"role": "user", "content": instruction})
            params = gm.get_settings_params()
            try:
                response = await asyncio.to_thread(lambda: client.chat.completions.create(
                    model=get_model(), messages=msgs, max_tokens=1000, temperature=params["temperature"],
                ))
            except Exception as e:
                await send_json({"type": "message", "agent": gm.name, "content": f"(Error: {e})"})
                await send_json({"type": "done", "agent": gm.name})
                break

            msg = response.choices[0].message
            content = (msg.content or "").strip()
            reasoning = getattr(msg, "reasoning_content", "") or ""

            if "【选项】" in content:
                c.party_awaiting_choice = True
                parts = content.split("【选项】", 1)
                narrative = parts[0].strip()
                choices_text = parts[1].strip() if len(parts) > 1 else ""
                c.add(gm.name, narrative, None, reasoning)
                await send_json({"type": "message", "agent": gm.name, "content": narrative})
                if choices_text:
                    await send_json({"type": "party_choices", "choices": choices_text})
                await send_json({"type": "done", "agent": gm.name})
                break
            else:
                c.add(gm.name, content, None, reasoning)
                await send_json({"type": "message", "agent": gm.name, "content": content})
                await send_json({"type": "done", "agent": gm.name})

            # Players react
            for a in agents:
                if a.name != gm_name:
                    await party_player_react(a, c, gm_name)

    async def party_player_react(player: Agent, c: Conversation, gm_name: str):
        """玩家 agent 对 GM 的叙述做出反应"""
        await send_json({"type": "typing", "agent": player.name})

        msgs = c.build_api_messages(player)
        msgs.append({"role": "user", "content": get_party_player_prompt(gm_name) + "\n\n用1-2句话对刚才发生的事情做出反应。简短自然，像在群聊里插话。保持角色性格。"})

        params = player.get_settings_params()
        try:
            response = await asyncio.to_thread(lambda: client.chat.completions.create(
                model=get_model(),
                messages=msgs,
                max_tokens=200,  # party mode: short reactions only
                temperature=params["temperature"],
                tools=TOOLS,
            ))
        except Exception as e:
            await send_json({"type": "message", "agent": player.name, "content": f"({player.name} error: {e})"})
            await send_json({"type": "done", "agent": player.name})
            return

        msg = response.choices[0].message
        content = (msg.content or "").strip()
        reasoning = getattr(msg, "reasoning_content", "") or ""
        content = re.sub(r'^\[.*?\]:\s*', '', content)

        c.add(player.name, content, None, reasoning)
        await send_json({"type": "message", "agent": player.name, "content": content})
        await send_json({"type": "done", "agent": player.name})

    async def end_session_reply(agent: Agent, c: Conversation):
        """让 agent 总结对话、写入记忆、更新状态并告别"""
        await send_json({"type": "typing", "agent": agent.name})
        # Create a modified conversation with the end-session prompt
        end_prompt = (
            "The conversation is ending. Before saying goodbye:\n"
            "1. Review the conversation. Call write_memory for any new info worth remembering (user's situation, preferences, important topics)\n"
            "2. Call update_state to record your current mood\n"
            "3. Give the user a warm, brief farewell\n\n"
            "Execute tool calls first, then give your farewell."
        )
        # Temporarily add the end prompt as a user message
        c.add("系统", end_prompt)
        result = await call_agent(agent, c)
        # Remove the system message
        c.messages.pop()
        content = result.get("content", "")
        if content.strip():
            conv.add(agent.name, content, result.get("emote"), result.get("reasoning", ""))
            await send_json({"type": "message", "agent": agent.name, "content": content, "emote": result.get("emote")})
        await send_json({"type": "done", "agent": agent.name})

    async def run_auto_chat():
        online = get_online_agents()
        for round_num in range(conv.auto_remaining):
            if len(online) < 2:
                break
            await send_json({"type": "auto_round", "round": round_num + 1, "total": conv.auto_remaining})
            # All online agents reply simultaneously — chaos!
            tasks = [agent_reply(a) for a in online]
            await asyncio.gather(*tasks)
        conv.auto_remaining = 0
        await send_json({"type": "auto_end"})

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "user_message":
                content = msg.get("content", "").strip()
                if not content:
                    continue
                conv.add("User", content)
                await send_json({"type": "message", "agent": "User", "content": content})

                if conv.mode == "party":
                    conv.party_awaiting_choice = False
                    gm = agent_map.get(conv.party_gm) or agents[0]
                    conv.party_round += 1
                    await send_json({"type": "party_round", "round": conv.party_round})
                    await send_json({"type": "typing", "agent": gm.name})
                    msgs = conv.build_api_messages(gm)
                    msgs.append({"role": "user", "content": f"The user said: {content}. Advance the plot accordingly. 2-4 sentences. No options."})
                    params = gm.get_settings_params()
                    try:
                        response = await asyncio.to_thread(lambda: client.chat.completions.create(
                            model=get_model(), messages=msgs, max_tokens=800, temperature=params["temperature"],
                        ))
                        gm_content = (response.choices[0].message.content or "").strip()
                        conv.add(gm.name, gm_content)
                        await send_json({"type": "message", "agent": gm.name, "content": gm_content})
                        await send_json({"type": "done", "agent": gm.name})
                    except Exception:
                        pass
                    for a in agents:
                        if a.name != conv.party_gm:
                            await party_player_react(a, conv, conv.party_gm)
                    await run_party_loop(gm, conv, conv.party_gm)

                elif conv.mode == "watch":
                    online = get_online_agents()
                    if len(online) >= 2:
                        s = load_settings()
                        conv.auto_remaining = s.get("global", {}).get("auto_chat_rounds", DEFAULT_AUTO_ROUNDS)
                        await run_auto_chat()
                else:
                    online = get_online_agents()
                    if len(online) >= 2:
                        await asyncio.gather(*[agent_reply(a) for a in online])
                    elif len(online) == 1:
                        await agent_reply(online[0])

            elif msg_type == "set_mode":
                mode = msg.get("mode", "free")
                conv.mode = mode
                labels = {"free": "Chat", "watch": "Watch", "party": "RPG"}
                mode_label = labels.get(mode, mode)
                if mode == "free":
                    conv.party_gm = ""
                    conv.party_round = 0
                    conv.party_awaiting_choice = False
                await send_json({"type": "mode_changed", "mode": mode, "label": mode_label})

            elif msg_type == "stop_auto":
                conv.auto_remaining = 0
                await send_json({"type": "auto_end"})

            elif msg_type == "end_session":
                await send_json({"type": "session_ending"})
                for agent in get_online_agents():
                    await end_session_reply(agent, conv)
                conv.save()
                await send_json({"type": "session_ended"})

            elif msg_type == "new_conversation":
                conv.save()
                conv.id = datetime.now().strftime("%Y%m%d-%H%M%S")
                conv.title = "New Chat"
                conv.messages.clear()
                conv.mode = "free"
                await send_json({
                    "type": "session_loaded",
                    "conv_id": conv.id,
                    "conv_title": conv.title,
                    "messages": []
                })

            elif msg_type == "load_conversation":
                conv_id = msg.get("conv_id", "")
                if conv_id:
                    conv.save()
                    new_conv = Conversation()
                    if new_conv.load(conv_id):
                        conv.id = new_conv.id
                        conv.title = new_conv.title
                        conv.messages.clear()
                        conv.messages.extend(new_conv.messages)
                        await send_json({
                            "type": "session_loaded",
                            "conv_id": conv.id,
                            "conv_title": conv.title,
                            "messages": conv.get_frontend_messages()
                        })

            elif msg_type == "start_party":
                online = get_online_agents()
                if len(online) < 3:
                    await send_json({"type": "error", "message": "派对模式需要至少3个agent在线（1个GM + 2个玩家）。请先开启更多agent。"})
                    continue
                gm_name = msg.get("gm", online[0].name)
                freq = msg.get("choice_freq", 7)
                conv.mode = "party"
                conv.party_gm = gm_name
                conv.party_round = 0
                conv.party_choice_freq = freq
                conv.party_awaiting_choice = False
                await send_json({"type": "mode_changed", "mode": "party", "label": "派对模式"})
                gm = agent_map.get(gm_name) or agents[0]
                await party_gm_narrate(gm, conv)
                for a in agents:
                    if a.name != gm_name:
                        await party_player_react(a, conv, gm_name)
                # Start MUST have choices, so we stop here and wait for user

            elif msg_type == "party_choice":
                choice = msg.get("choice", "")
                conv.party_awaiting_choice = False
                conv.add("User", f"I choose: {choice}")
                await send_json({"type": "message", "agent": "User", "content": f">> {choice}"})
                gm = agent_map.get(conv.party_gm) or agents[0]
                # Narrate result of choice (always, no options yet)
                conv.party_round += 1
                await send_json({"type": "party_round", "round": conv.party_round})
                await send_json({"type": "typing", "agent": gm.name})
                msgs = conv.build_api_messages(gm)
                msgs.append({"role": "user", "content": f"The user chose: {choice}. Narrate what happens next. 2-4 sentences. No options."})
                params = gm.get_settings_params()
                try:
                    response = await asyncio.to_thread(lambda: client.chat.completions.create(
                        model=get_model(), messages=msgs, max_tokens=800, temperature=params["temperature"],
                    ))
                    content = (response.choices[0].message.content or "").strip()
                    conv.add(gm.name, content)
                    await send_json({"type": "message", "agent": gm.name, "content": content})
                    await send_json({"type": "done", "agent": gm.name})
                except Exception as e:
                    await send_json({"type": "message", "agent": gm.name, "content": f"(Error)"})
                    await send_json({"type": "done", "agent": gm.name})
                # Players react
                for a in agents:
                    if a.name != conv.party_gm:
                        await party_player_react(a, conv, conv.party_gm)
                # Run loop until next choice (auto-continue for choice_freq-1 more rounds)
                await run_party_loop(gm, conv, conv.party_gm)

    except WebSocketDisconnect:
        pass


# ============================================================
# Auth Middleware
# ============================================================
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        public = ["/api/auth", "/"]
        if request.url.path in public or request.url.path.startswith("/api/emotes/"):
            return await call_next(request)
        s = load_settings()
        pwd = s.get("password", "")
        if not pwd:
            return await call_next(request)
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = request.query_params.get("token", "")
        if token != pwd:
            return Response("Unauthorized", status_code=401)
        return await call_next(request)

app.add_middleware(AuthMiddleware)

# ============================================================
# Startup
# ============================================================
if __name__ == "__main__":
    reload_agents()
    # Initialize default settings
    s = load_settings()
    if not s.get("agents"):
        for a in agents:
            get_agent_settings(a.name)
    print("NEST-chat started!")
    print(f"   Agents: {[a.name for a in agents]}")
    print("   http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
