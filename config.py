from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if TOKEN is None:
    raise RuntimeError(
        "DISCORD_BOT_TOKEN が設定されていません。.env ファイルを確認してください。"
    )

DB_NAME = "bot_system.db"
FEATURES = ["F-1", "F-2", "F-3"]
MILESTONES = ["疎通", "音声", "統合"]
DATE_FMT = "%Y-%m-%d %H:%M"  # updated_at / due_date、両方これに統一
STATUS_MAP = {
    "todo": {"label": "⚪ 未着手", "symbol": "⚪"},
    "wip": {"label": "🟡 進行中", "symbol": "🟡"},
    "done": {"label": "🟢 完了", "symbol": "🟢"},
}