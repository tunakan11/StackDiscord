import discord
import os
import sys
from embeds import build_embed

webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
event_name = os.environ["GITHUB_EVENT_NAME"] # "push" or "pull_request"
actor = os.environ["GITHUB_ACTOR"]
branch = os.environ["GITHUB_REF_NAME"]

webhook = discord.SyncWebhook.from_url(webhook_url)

if event_name == "push":
    embed = build_embed(
        title="📦 Push通知",
        description=f"{actor} さんが {branch} にpushしました",
        kind="info"
    )
else:
    embed = build_embed(
        title="🔀 PR通知",
        description=f"{actor} さんがPRを作成しました",
        kind="wip",
    )

webhook.send(embed=embed)