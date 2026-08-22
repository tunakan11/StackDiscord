import discord
from discord.ext import tasks, commands
from embeds import build_embed
from db import get_upcoming_reminders, mark_as_reminded

class RemindersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_reminders.start()

    async def cog_unload(self):
        self.check_reminders.cancel()

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        for task_id, uid, content, due_str, channel_id, in get_upcoming_reminders():
            channel = self.bot.get_channel(channel_id)

            embed = build_embed(
                title="⏰ リマインダー：期限が近いタスクがあります",
                description=f"<@{uid}> さん、期限が迫っています。",
                kind="error",
                fields={
                    "タスクID": f"#{task_id}",
                    "期限": due_str,
                    "内容": content,
                },
                footer="完了したら /task done を実行してください",
            )

            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(content=f"<@{uid}>", embed=embed)
            else:
                try:
                    user = await self.bot.fetch_user(uid)
                    if user:
                        await user.send(embed=embed)
                except Exception as e:
                    print(f"リマインド送信失敗: {e}")

            mark_as_reminded(task_id)

async def setup(bot):
    await bot.add_cog(RemindersCog(bot))