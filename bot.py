from datetime import datetime, timedelta
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
from embeds import build_embed, STATUS_COLOR

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if TOKEN is None:
    raise RuntimeError(
        "DISCORD_BOT_TOKEN が設定されていません。.env ファイルを確認してください。"
    )

# Bot：基本設定
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DB_NAME = "bot_system.db"

FEATURES = ["F-1", "F-2", "F-3"]
MILESTONES = ["疎通", "音声", "統合"]

DATE_FMT = "%Y-%m-%d %H:%M"  # updated_at / due_date、両方これに統一

STATUS_MAP = {
    "todo": {"label": "⚪ 未着手", "symbol": "⚪"},
    "wip": {"label": "🟡 進行中", "symbol": "🟡"},
    "done": {"label": "🟢 完了", "symbol": "🟢"},
}

# README「Embedフォーマット統一ルール」準拠の色定義
STATUS_COLOR = {
    "done": 0x2ECC71,
    "wip": 0xF1C40F,
    "todo": 0x95A5A6,
    "error": 0xE74C3C,
    "info": 0x3498DB,
}


# ============================================================
# README準拠：全機能共通のEmbed生成関数
# ============================================================
def build_embed(title, description, kind, fields=None, footer=None):
    embed = discord.Embed(
        title=title,
        description=description,
        color=STATUS_COLOR.get(kind, 0x3498DB),
        timestamp=datetime.now(),
    )
    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=True)
    if footer:
        embed.set_footer(text=footer)
    return embed


# ============================================================
# DB：モジュールレベルで1つのコネクションを使い回す
# ============================================================
# discord.pyの各コマンド/タスクループは基本的に同一イベントループ上で
# 逐次実行されるため、コネクションを毎回開閉せずここで一本化する。
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON")


def init_db():
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS progress (
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            feature TEXT NOT NULL,
            milestone TEXT NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, feature, milestone)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignee_id INTEGER NOT NULL,
            assignee_name TEXT NOT NULL,
            feature TEXT NOT NULL,
            milestone TEXT NOT NULL,
            content TEXT NOT NULL,
            due_date TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            reminded INTEGER DEFAULT 0,
            status TEXT DEFAULT 'open'
        )
        """
    )

    conn.commit()


init_db()


# 進捗更新
def update_progress(user_id, user_name, feature, milestone, status, updated_at):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO progress (user_id, user_name, feature, milestone, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, feature, milestone)
        DO UPDATE SET
            user_name = excluded.user_name,
            status = excluded.status,
            updated_at = excluded.updated_at
        """,
        (user_id, user_name, feature, milestone, status, updated_at),
    )
    conn.commit()


def get_all_progress():
    cur = conn.cursor()
    cur.execute("SELECT user_id, user_name, feature, milestone, status FROM progress")
    return cur.fetchall()


def add_task(assignee_id, assignee_name, feature, milestone, content, due_date, channel_id):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tasks (assignee_id, assignee_name, feature, milestone, content, due_date, channel_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (assignee_id, assignee_name, feature, milestone, content, due_date, channel_id),
    )
    task_id = cur.lastrowid
    conn.commit()

    now_str = datetime.now().strftime(DATE_FMT)
    update_progress(assignee_id, assignee_name, feature, milestone, "wip", now_str)

    return task_id


def get_tasks(assignee_id=None):
    cur = conn.cursor()
    if assignee_id:
        cur.execute(
            """
            SELECT id, assignee_name, feature, milestone, content, due_date, status
            FROM tasks
            WHERE assignee_id = ? AND status = 'open'
            ORDER BY due_date ASC
            """,
            (assignee_id,),
        )
    else:
        cur.execute(
            """
            SELECT id, assignee_name, feature, milestone, content, due_date, status
            FROM tasks
            WHERE status = 'open'
            ORDER BY due_date ASC
            """
        )
    return cur.fetchall()


def get_upcoming_reminders():
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, assignee_id, content, due_date, channel_id
        FROM tasks
        WHERE reminded = 0 AND status = 'open'
        """
    )
    rows = cur.fetchall()

    now = datetime.now()
    upcoming = []

    for task_id, uid, content, due_str, channel_id in rows:
        try:
            due_dt = datetime.strptime(due_str, DATE_FMT)
            if now <= due_dt <= now + timedelta(hours=24):
                upcoming.append((task_id, uid, content, due_str, channel_id))
        except ValueError:
            continue

    return upcoming


def mark_as_reminded(task_id):
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET reminded = 1 WHERE id = ?", (task_id,))
    conn.commit()


def complete_task(task_id):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT assignee_id, assignee_name, feature, milestone
        FROM tasks
        WHERE id = ? AND status = 'open'
        """,
        (task_id,),
    )
    row = cur.fetchone()

    if not row:
        return False

    assignee_id, assignee_name, feature, milestone = row

    cur.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,))
    conn.commit()

    now_str = datetime.now().strftime(DATE_FMT)
    update_progress(assignee_id, assignee_name, feature, milestone, "done", now_str)

    return True


# リマインダー送信
@tasks.loop(minutes=1)
async def check_reminders():
    for task_id, uid, content, due_str, channel_id in get_upcoming_reminders():
        channel = bot.get_channel(channel_id)

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
                user = await bot.fetch_user(uid)
                if user:
                    await user.send(embed=embed)
            except Exception as e:
                print(f"リマインド送信失敗: {e}")

        mark_as_reminded(task_id)


@bot.event
async def on_ready():
    if bot.user:
        print(f"ログイン成功: {bot.user.name}")

    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンド {len(synced)} 件同期")
    except Exception as e:
        print(f"同期失敗: {e}")

    if not check_reminders.is_running(): # type: ignore[attr-defined]
        check_reminders.start() # type: ignore[attr-defined]


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
    bot.run(TOKEN)