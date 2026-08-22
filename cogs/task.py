from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from config import FEATURES, MILESTONES, DATE_FMT
from db import add_task, get_tasks, complete_task
from embeds import build_embed


class TaskCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    task_group = app_commands.Group(name="task", description="タスク管理")

    @task_group.command(name="add", description="タスクを登録します")
    @app_commands.describe(
        assignee="担当者",
        feature="機能",
        milestone="マイルストーン",
        content="内容",
        due_date="期限 (YYYY-MM-DD HH:MM)",
    )
    @app_commands.choices(
        feature=[app_commands.Choice(name=f, value=f) for f in FEATURES],
        milestone=[app_commands.Choice(name=m, value=m) for m in MILESTONES],
    )
    async def add(
        self,
        interaction: discord.Interaction,
        assignee: discord.Member,
        feature: str,
        milestone: str,
        content: str,
        due_date: str,
    ):
        formatted = due_date.replace("/", "-")

        try:
            datetime.strptime(formatted, DATE_FMT)
        except ValueError:
            await interaction.response.send_message("日時形式が不正です", ephemeral=True)
            return

        task_id = add_task(
            assignee.id,
            assignee.display_name,
            feature,
            milestone,
            content,
            formatted,
            interaction.channel_id,
        )

        embed = build_embed(
            title="タスク登録完了",
            description="タスクを登録し、進捗を進行中に更新しました",
            kind="wip",
            fields={
                "ID": f"#{task_id}",
                "担当者": assignee.mention,
                "対象": f"{feature}/{milestone}",
                "期限": formatted,
                "内容": content,
            },
        )

        await interaction.response.send_message(embed=embed)

    @task_group.command(name="list", description="進行中タスク一覧を表示します")
    @app_commands.describe(filter_type="表示対象")
    @app_commands.choices(
        filter_type=[
            app_commands.Choice(name="全体", value="all"),
            app_commands.Choice(name="自分のみ", value="me"),
        ]
    )
    async def list(self, interaction: discord.Interaction, filter_type: str = "all"):
        if filter_type == "me":
            tasks_data = get_tasks(interaction.user.id)
            title = f"{interaction.user.display_name} さんのタスク"
        else:
            tasks_data = get_tasks()
            title = "全体のタスク一覧"

        if not tasks_data:
            await interaction.response.send_message("進行中タスクはありません")
            return

        embed = build_embed(title=title, description="", kind="info")

        for tid, name, f, m, content, due, status in tasks_data:
            embed.add_field(
                name=f"#{tid} [{f}/{m}] 期限: {due} (担当: {name})",
                value=f"内容: {content}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @task_group.command(name="done", description="タスクを完了にします")
    @app_commands.describe(task_id="タスクID")
    async def done(self, interaction: discord.Interaction, task_id: int):
        if complete_task(task_id):
            embed = build_embed(
                title="タスク完了",
                description=f"タスク #{task_id} を完了しました",
                kind="done",
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                "タスクが存在しないか既に完了しています", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(TaskCog(bot))
