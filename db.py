import sqlite3
from datetime import datetime
from config import DB_NAME, DATE_FMT

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
    from datetime import timedelta
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