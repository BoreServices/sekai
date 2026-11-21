import discord

from view.base import ERROR_COLOR, SUCCESS_COLOR, base_embed, brand


def welcome_embed(member: discord.Member, text: str) -> discord.Embed:
    desc = f"**Welcome**\n*{member}*\n\n{text}"
    embed = base_embed(description=desc, color=SUCCESS_COLOR)
    embed.set_thumbnail(url=member.display_avatar.url)
    return brand(embed)


def leave_embed(member: discord.Member, text: str) -> discord.Embed:
    desc = f"**Goodbye**\n*{member}*\n\n{text}"
    embed = base_embed(description=desc, color=ERROR_COLOR)
    embed.set_thumbnail(url=member.display_avatar.url)
    return brand(embed)
