from datetime import datetime, timedelta
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands, tasks

# Bot：基本設定
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DB_NAME = "bot_system.db"

FEATURES = ["F-1", "F-2", "F-3"]
MILESTONES = ["疎通", "音声", "統合"]

STATUS_MAP = {
    "todo": {"label": "⚪ 未着手", "symbol": "⚪"},
    "wip": {"label": "🟡 進行中", "symbol": "🟡"},
    "done": {"label": "🟢 完了", "symbol": "🟢"},
}


# DB 初期化
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # 進捗テーブル
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

    # タスクテーブル
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
    conn.close()


init_db()


# 進捗更新
def update_progress(user_id, user_name, feature, milestone, status, updated_at):
    conn = sqlite3.connect(DB_NAME)
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
    conn.close()


# 全進捗データ取得（追加）
def get_all_progress():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, user_name, feature, milestone, status FROM progress"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# タスク登録
def add_task(
    assignee_id,
    assignee_name,
    feature,
    milestone,
    content,
    due_date,
    channel_id,
):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO tasks (assignee_id, assignee_name, feature, milestone, content, due_date, channel_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            assignee_id,
            assignee_name,
            feature,
            milestone,
            content,
            due_date,
            channel_id,
        ),
    )

    task_id = cur.lastrowid
    conn.commit()
    conn.close()

    # タスク登録時は自動で進行中に更新
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    update_progress(
        assignee_id, assignee_name, feature, milestone, "wip", now_str
    )

    return task_id


# タスク取得
def get_tasks(assignee_id=None):
    conn = sqlite3.connect(DB_NAME)
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

    rows = cur.fetchall()
    conn.close()
    return rows


# リマインダー対象タスク取得
def get_upcoming_reminders():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, assignee_id, content, due_date, channel_id
        FROM tasks
        WHERE reminded = 0 AND status = 'open'
    """
    )

    rows = cur.fetchall()
    conn.close()

    now = datetime.now()
    upcoming = []

    for task_id, uid, content, due_str, channel_id in rows:
        try:
            due_dt = datetime.strptime(due_str, "%Y-%m-%d %H:%M")
            if now <= due_dt <= now + timedelta(hours=24):
                upcoming.append((task_id, uid, content, due_str, channel_id))
        except ValueError:
            continue

    return upcoming


def mark_as_reminded(task_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET reminded = 1 WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


# タスク完了
def complete_task(task_id):
    conn = sqlite3.connect(DB_NAME)
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
        conn.close()
        return False

    assignee_id, assignee_name, feature, milestone = row

    cur.execute(
        "UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,)
    )
    conn.commit()
    conn.close()

    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    update_progress(
        assignee_id, assignee_name, feature, milestone, "done", now_str
    )

    return True


# リマインダー送信
@tasks.loop(minutes=1)
async def check_reminders():
    for task_id, uid, content, due_str, channel_id in get_upcoming_reminders():
        channel = bot.get_channel(channel_id)

        embed = discord.Embed(
            title="リマインダー：期限が近いタスクがあります",
            description=f"<@{uid}> さん、期限が迫っています。",
            color=0xE74C3C,
        )
        embed.add_field(name="タスクID", value=f"#{task_id}")
        embed.add_field(name="期限", value=due_str)
        embed.add_field(name="内容", value=content)
        embed.set_footer(text="完了したら /task-complete を実行してください")

        if channel:
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
    print(f"ログイン成功: {bot.user.name}")

    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンド {len(synced)} 件同期")
    except Exception as e:
        print(f"同期失敗: {e}")

    if not check_reminders.is_running():
        check_reminders.start()


@bot.tree.command(name="progress", description="進捗ステータスを更新します")
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
async def progress_cmd(
    interaction: discord.Interaction,
    feature: str,
    milestone: str,
    status: str,
):
    user_id = interaction.user.id
    user_name = interaction.user.display_name
    updated_at = interaction.created_at.strftime("%Y/%m/%d %H:%M")

    update_progress(user_id, user_name, feature, milestone, status, updated_at)

    info = STATUS_MAP.get(status, {"label": status})
    color = (
        0x2ECC71
        if status == "done"
        else (0xF1C40F if status == "wip" else 0x3498DB)
    )

    embed = discord.Embed(
        title="進捗更新",
        description=f"{interaction.user.mention} さんの進捗を更新しました",
        color=color,
    )
    embed.add_field(name="機能", value=feature)
    embed.add_field(name="マイルストーン", value=milestone)
    embed.add_field(name="ステータス", value=info["label"])
    embed.set_footer(text=f"更新日時: {updated_at}")

    await interaction.response.send_message(embed=embed)


# 全体進捗確認
@bot.tree.command(name="status", description="全体の進捗一覧を表示します")
async def status_cmd(interaction: discord.Interaction):
    rows = get_all_progress()

    if not rows:
        await interaction.response.send_message("進捗データがありません")
        return

    data = {}
    names = {}

    for uid, uname, f, m, s in rows:
        names[uid] = uname
        data.setdefault(uid, {})[(f, m)] = s

    embed = discord.Embed(
        title="チーム進捗一覧",
        description="🟢 完了 / 🟡 進行中 / ⚪ 未着手",
        color=0x34495E,
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


# タスク登録
@bot.tree.command(name="add-task", description="タスクを登録します")
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
async def add_task_cmd(
    interaction: discord.Interaction,
    assignee: discord.Member,
    feature: str,
    milestone: str,
    content: str,
    due_date: str,
):
    formatted = due_date.replace("/", "-")

    try:
        datetime.strptime(formatted, "%Y-%m-%d %H:%M")
    except ValueError:
        await interaction.response.send_message(
            "日時形式が不正です", ephemeral=True
        )
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

    embed = discord.Embed(
        title="タスク登録完了",
        description="タスクを登録し、進捗を進行中に更新しました",
        color=0x3498DB,
    )
    embed.add_field(name="ID", value=f"#{task_id}")
    embed.add_field(name="担当者", value=assignee.mention)
    embed.add_field(name="対象", value=f"{feature}/{milestone}")
    embed.add_field(name="期限", value=formatted)
    embed.add_field(name="内容", value=content)

    await interaction.response.send_message(embed=embed)


# タスク一覧
@bot.tree.command(name="task-list", description="進行中タスク一覧を表示します")
@app_commands.describe(filter_type="表示対象")
@app_commands.choices(
    filter_type=[
        app_commands.Choice(name="全体", value="all"),
        app_commands.Choice(name="自分のみ", value="me"),
    ]
)
async def task_list_cmd(
    interaction: discord.Interaction, filter_type: str = "all"
):
    if filter_type == "me":
        tasks_data = get_tasks(interaction.user.id)
        title = f"{interaction.user.display_name} さんのタスク"
    else:
        tasks_data = get_tasks()
        title = "全体のタスク一覧"

    if not tasks_data:
        await interaction.response.send_message("進行中タスクはありません")
        return

    embed = discord.Embed(title=title, color=0x34495E)

    for tid, name, f, m, content, due, status in tasks_data:
        embed.add_field(
            name=f"#{tid} [{f}/{m}] 期限: {due} (担当: {name})",
            value=f"内容: {content}",
            inline=False,
        )

    await interaction.response.send_message(embed=embed)


# タスクの完了
@bot.tree.command(name="task-complete", description="タスクを完了にします")
@app_commands.describe(task_id="タスクID")
async def task_complete_cmd(
    interaction: discord.Interaction, task_id: int
):
    if complete_task(task_id):
        embed = discord.Embed(
            title="タスク完了",
            description=f"タスク #{task_id} を完了しました",
            color=0x2ECC71,
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "タスクが存在しないか既に完了しています", ephemeral=True
        )

TOKEN = "＃ここはディスコのトークン"

if __name__ == "__main__":
    bot.run(TOKEN)
