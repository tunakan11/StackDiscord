from datetime import datetime
import discord
from discord import app_commands
from embeds import build_embed
from discord.ext import commands
from config import TOKEN, FEATURES, MILESTONES, DATE_FMT, STATUS_MAP
from db import init_db, update_progress, get_all_progress, add_task, get_tasks, complete_task


# Bot：基本設定
class StackBot(commands.Bot):
    async def setup_hook(self):
        # リマインダーのループは cogs/reminders.py に移動済み
        await self.load_extension("cogs.reminders")


intents = discord.Intents.default()
bot = StackBot(command_prefix="!", intents=intents)

# ============================================================
# DB：モジュールレベルで1つのコネクションを使い回す
# ============================================================
# discord.pyの各コマンド/タスクループは基本的に同一イベントループ上で
# 逐次実行されるため、コネクションを毎回開閉せずここで一本化する。

init_db()

# 進捗更新

@bot.event
async def on_ready():
    if bot.user:
        print(f"ログイン成功: {bot.user.name}")

    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンド {len(synced)} 件同期")
    except Exception as e:
        print(f"同期失敗: {e}")


# ============================================================
# README準拠：/task グループ, /progress グループ
# ============================================================

task_group = app_commands.Group(name="task", description="タスク管理")
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
async def progress_update_cmd(
    interaction: discord.Interaction, feature: str, milestone: str, status: str
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
async def progress_show_cmd(interaction: discord.Interaction):
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
async def task_add_cmd(
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
        assignee.id, assignee.display_name, feature, milestone, content, formatted, interaction.channel_id
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
async def task_list_cmd(interaction: discord.Interaction, filter_type: str = "all"):
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
async def task_done_cmd(interaction: discord.Interaction, task_id: int):
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


bot.tree.add_command(task_group)
bot.tree.add_command(progress_group)


if __name__ == "__main__":
    assert TOKEN is not None
    bot.run(TOKEN)