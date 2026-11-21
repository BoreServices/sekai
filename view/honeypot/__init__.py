import discord

from view.base import (
    ERROR_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    base_embed,
    brand)

PUNISH_TEXT = {"ban": "banned", "kick": "kicked", "timeout": "timed out"}


def honeypot_status_embed(
    *,
    enabled: bool,
    punish: str,
    channel_ids: list[int],
    problems: list[str] | None = None) -> discord.Embed:
    state = "enabled" if enabled else "disabled"
    embed = base_embed(
        title="🍯 Honeypot",
        description=(
            f"The honeypot is **{state}**. Anyone who posts in a trap channel is "
            f"**{PUNISH_TEXT.get(punish, punish)}** automatically — it catches raid "
            "bots, self-bots and token grabbers that post in every channel. The "
            "owner, admins and members with **Manage Server** or **Manage "
            "Messages** are exempt."
        ),
        color=SUCCESS_COLOR if enabled else WARNING_COLOR)
    if channel_ids:
        channels = "\n".join(f"<#{cid}>" for cid in channel_ids[:20])
        if len(channel_ids) > 20:
            channels += f"\n…and {len(channel_ids) - 20} more"
    else:
        channels = "None yet — add one with `honeypot set #channel`."

    embed.add_field(name="Punishment", value=f"`{punish}`", inline=True)
    embed.add_field(name="Trap channels", value=channels, inline=False)
    if problems:
        embed.add_field(
            name="⚠️ Not fully armed",
            value="\n".join(f"• {problem}" for problem in problems),
            inline=False)
    embed.add_field(
        name="Commands",
        value=(
            "`honeypot set <#channel>` · `honeypot remove <#channel>` · "
            "`honeypot list` · `honeypot punish <ban|kick|timeout>` · "
            "`honeypot enable` · `honeypot disable`"
        ),
        inline=False)
    return brand(embed)


def honeypot_action_embed(
    *,
    member: discord.Member,
    channel,
    punish: str,
    outcome: str | None = None,
    problem: str | None = None,
    content: str | None = None) -> discord.Embed:
    if problem:
        description = (
            f"{member.mention} posted in the honeypot {channel.mention}, but I "
            f"could not punish them: {problem}"
        )
        color = WARNING_COLOR
    else:
        description = (
            f"{member.mention} was **{outcome}** for posting in the honeypot "
            f"{channel.mention}."
        )
        color = ERROR_COLOR
    embed = base_embed(
        title="🍯 Honeypot triggered", description=description, color=color
    )
    embed.add_field(name="Account", value=f"{member} (`{member.id}`)", inline=True)
    embed.add_field(name="Punishment", value=f"`{punish}`", inline=True)
    if content:
        embed.add_field(name="Message", value=content, inline=False)
    return brand(embed)