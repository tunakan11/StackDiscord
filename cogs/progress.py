import discord
from discord import app_commands
from discord.ext import commands
from config import FEATURES, MILESTONES, DATE_FMT, STATUS_MAP
from db import update_progress, get_all_progress
from embeds import build_embed


class ProgressCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    progress_group = app_commands.Group(name="progress", description="進捗管理")

    @progress_group.command(name="update", description="進捗ステータスを更新します")
    @app_commands.describe(feature="機能", milestone="マイルストーン", status="ステータス")
    @app_commands.choices(
        feature=[app_commands.Choice(name=f, value=f) for f in FEATURES],
        milestone=[app_commands.Choice(name=m, value=m) for m in MILESTONES],
        status=[
            app_commands.Choice(name="未着手", value="todo"),
            app_commands.Choice(name="進行中", value="wip"),
            app_commands.Choice(name="完了", value="done"),
        ],
    )
    async def update(
        self, interaction: discord.Interaction, feature: str, milestone: str, status: str
    ):
        user_id = interaction.user.id
        user_name = interaction.user.display_name
        updated_at = interaction.created_at.strftime(DATE_FMT)

        update_progress(user_id, user_name, feature, milestone, status, updated_at)

        info = STATUS_MAP.get(status, {"label": status})

        embed = build_embed(
            title="進捗更新",
            description=f"{interaction.user.mention} さんの進捗を更新しました",
            kind=status,
            fields={
                "機能": feature,
                "マイルストーン": milestone,
                "ステータス": info["label"],
            },
            footer=f"更新日時: {updated_at}",
        )

        await interaction.response.send_message(embed=embed)

    @progress_group.command(name="show", description="全体の進捗一覧を表示します")
    async def show(self, interaction: discord.Interaction):
        rows = get_all_progress()

        if not rows:
            await interaction.response.send_message("進捗データがありません")
            return

        data = {}
        names = {}

        for uid, uname, f, m, s in rows:
            names[uid] = uname
            data.setdefault(uid, {})[(f, m)] = s

        embed = build_embed(
            title="チーム進捗一覧",
            description="🟢 完了 / 🟡 進行中 / ⚪ 未着手",
            kind="info",
        )

        for uid, uname in names.items():
            user_data = data.get(uid, {})
            text = ""
            for f in FEATURES:
                row = []
                for m in MILESTONES:
                    st = user_data.get((f, m), "todo")
                    sym = STATUS_MAP.get(st, {}).get("symbol", "⚪")
                    row.append(f"{m}:{sym}")
                text += f"**[{f}]** " + " | ".join(row) + "\n"
            embed.add_field(name=uname, value=text, inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(ProgressCog(bot))
