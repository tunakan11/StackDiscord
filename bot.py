import discord
from discord.ext import commands
from config import TOKEN
from db import init_db

# ============================================================
# DB：モジュールレベルで1つのコネクションを使い回す
# ============================================================
# discord.pyの各コマンド/タスクループは基本的に同一イベントループ上で
# 逐次実行されるため、コネクションを毎回開閉せずここで一本化する。

init_db()

# README準拠の /task グループ・/progress グループは cogs 配下で定義する
EXTENSIONS = [
    "cogs.progress",
    "cogs.task",
    "cogs.reminders",
]


# Bot：基本設定
class StackBot(commands.Bot):
    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)


intents = discord.Intents.default()
bot = StackBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    if bot.user:
        print(f"ログイン成功: {bot.user.name}")

    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンド {len(synced)} 件同期")
    except Exception as e:
        print(f"同期失敗: {e}")


if __name__ == "__main__":
    assert TOKEN is not None
    bot.run(TOKEN)
