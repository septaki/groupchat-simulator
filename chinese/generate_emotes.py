"""Generate default emote SVG files for each agent"""
from pathlib import Path

BASE_DIR = Path(__file__).parent
AGENTS_DIR = BASE_DIR / "agents"

EMOTES = {
    "happy":     {"kaomoji": "(＾▽＾)", "color": "#fbbf24", "bg": "#fef3c7"},
    "sad":       {"kaomoji": "(´;ω;`)", "color": "#60a5fa", "bg": "#dbeafe"},
    "shy":       {"kaomoji": "(/ω＼)",   "color": "#f9a8d4", "bg": "#fce7f3"},
    "angry":     {"kaomoji": "(╬ Ò﹏Ó)", "color": "#f87171", "bg": "#fee2e2"},
    "surprised": {"kaomoji": "(°ロ°)",   "color": "#fbbf24", "bg": "#fef9c3"},
    "cute":      {"kaomoji": "(◕‿◕✿)", "color": "#f472b6", "bg": "#fce7f3"},
    "love":      {"kaomoji": "(｡♥‿♥｡)", "color": "#ec4899", "bg": "#fce7f3"},
    "thinking":  {"kaomoji": "(￣～￣;)", "color": "#a78bfa", "bg": "#ede9fe"},
}

SVG_TEMPLATE = '''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
  <rect width="200" height="200" rx="30" fill="{bg}"/>
  <text x="100" y="110" text-anchor="middle" font-size="28" fill="{color}" font-family="sans-serif">{kaomoji}</text>
</svg>'''


def generate_all():
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        emotes_dir = agent_dir / "emotes"
        emotes_dir.mkdir(exist_ok=True)

        for mood, data in EMOTES.items():
            svg_content = SVG_TEMPLATE.format(
                bg=data["bg"],
                color=data["color"],
                kaomoji=data["kaomoji"],
            )
            filepath = emotes_dir / f"{mood}.svg"
            filepath.write_text(svg_content, encoding="utf-8")
            print(f"  {agent_dir.name}/{mood}.svg")


if __name__ == "__main__":
    print("Generating default emotes...")
    generate_all()
    print("Done!")
