import discord
from datetime import datetime

STATUS_COLOR = {
    "done": 0x2ECC71,
    "wip": 0xF1C40F,
    "todo": 0x95A5A6,
    "error": 0xE74C3C,
    "info": 0x3498DB,
}

# embedは埋め込みって意味
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