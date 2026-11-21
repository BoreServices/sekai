import discord

from view.base import INFO_COLOR, base_embed, brand


def starboard_embed(
    *,
    message: discord.Message,
    stars: int,
    emoji: str,
    jump_url: str,
) -> discord.Embed:
    footer = f"{emoji} {stars}"
    body = message.content or ""
    desc = f"**Starboard**\n*{message.author}*\n\n{body}\n\n`{footer}`" if body else f"**Starboard**\n*{message.author}*\n\n`{footer}`"
    embed = base_embed(description=desc)
    images = [
        attachment
        for attachment in message.attachments
        if (attachment.content_type or "").startswith("image/")
    ]
    files = [
        attachment for attachment in message.attachments if attachment not in images
    ]
    if images:
        embed.set_image(url=images[0].url)
    extra = images[1:] + files
    if extra:
        embed.add_field(
            name="Attachments",
            value="\n".join(
                f"[{attachment.filename}]({attachment.url})" for attachment in extra
            )[:1024],
            inline=False,
        )
    if message.stickers:
        embed.add_field(
            name="Sticker",
            value=", ".join(sticker.name for sticker in message.stickers),
            inline=False,
        )

    embed.add_field(name="Source", value=f"[Jump to message]({jump_url})", inline=False)
    return brand(embed, footer=footer)


def starboard_settings_embed(
    *,
    guild_name: str,
    channel: discord.abc.GuildChannel | None,
    emoji: str,
    threshold: int,
    self_star: bool,
    ignored: list,
    footer: str | None = None,
) -> discord.Embed:
    embed = base_embed(
        title=f"⭐ Starboard · {guild_name}",
        description=(
            "Messages that reach the reaction threshold get reposted to the "
            "starboard channel."
        ),
        color=INFO_COLOR,
    )
    embed.add_field(
        name="Channel",
        value=channel.mention if channel is not None else "not set",
        inline=True,
    )
    embed.add_field(name="Emoji", value=emoji, inline=True)
    embed.add_field(name="Threshold", value=f"{threshold} reactions", inline=True)
    embed.add_field(
        name="Self-starring",
        value="allowed" if self_star else "ignored",
        inline=True,
    )
    embed.add_field(
        name="Ignored channels",
        value=(
            ", ".join(item.mention for item in ignored) if ignored else "none"
        )[:1024],
        inline=False,
    )
    return brand(embed, footer=footer)


__all__ = ["starboard_embed", "starboard_settings_embed"]
