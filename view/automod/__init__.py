import discord

from view.base import WARNING_COLOR, base_embed, brand


def automod_action_embed(
    *,
    member: discord.Member,
    channel,
    reason: str,
    content: str | None = None,
) -> discord.Embed:
    embed = base_embed(
        title="Automod",
        description=f"Action taken on a message from {member.mention}.",
        color=WARNING_COLOR,
    )
    embed.add_field(name="Rule", value=reason, inline=True)
    if channel is not None:
        embed.add_field(name="Channel", value=getattr(channel, "mention", str(channel)), inline=True)
    if content:
        embed.add_field(name="Message", value=content, inline=False)
    return brand(embed)
