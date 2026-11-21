import discord

from view.base import SUCCESS_COLOR, base_embed, brand


def voicemaster_setup_embed(
    *,
    category: discord.CategoryChannel,
    trigger: discord.VoiceChannel,
    prefix: str,
    already: bool = False,
    menu: discord.TextChannel | None = None,
) -> discord.Embed:
    if already:
        description = (
            "Your VoiceMaster system is already set up — nothing new was created.\n\n"
            f"Join {trigger.mention} and the bot makes a channel for you under "
            f"{category.mention}. It disappears automatically when everyone leaves."
        )
    else:
        description = (
            "Your VoiceMaster system is ready.\n\n"
            f"Join {trigger.mention} and the bot makes a channel for you under "
            f"{category.mention}. It disappears automatically when everyone leaves."
        )

    embed = base_embed(
        title="🔊 VoiceMaster",
        description=description,
        color=SUCCESS_COLOR,
    )
    embed.add_field(name="📁 Category", value=category.mention, inline=True)
    embed.add_field(name="🎙️ Join to create", value=trigger.mention, inline=True)
    if menu is not None:
        embed.add_field(
            name="🖼️ Menu channel",
            value=f"{menu.mention}\nThe guide image and buttons live there.",
            inline=False,
        )
    embed.add_field(
        name="⚙️ Controls",
        value=(
            f"`{prefix}voicemaster lock` / `unlock` — close or reopen your channel\n"
            f"`{prefix}voicemaster hide` / `unhide` — hide or show it in the server\n"
            f"`{prefix}voicemaster rename <name>` — rename it\n"
            f"`{prefix}voicemaster limit <0-99>` — cap members (0 = unlimited)\n"
            f"`{prefix}voicemaster claim` — take over if the owner left\n"
            f"`{prefix}voicemaster transfer <member>` — hand the channel over\n"
            f"`{prefix}voicemaster permit <member>` — let one member in while locked\n"
            f"`{prefix}voicemaster reject <member>` — remove a member\n"
            f"`{prefix}voicemaster bitrate <kbps>` — audio quality\n"
            f"`{prefix}voicemaster delete` — delete the channel now"
        ),
        inline=False,
    )
    return brand(embed)


def voicemaster_claim_prompt_embed(*, channel: discord.VoiceChannel) -> discord.Embed:
    embed = base_embed(
        description=(
            f"The owner left {channel.mention}. Anyone still in the channel can "
            "press **Claim ownership** to take it over — otherwise it disappears "
            "when the last member leaves."
        )
    )
    return brand(embed)


def voicemaster_menu_embed(
    *,
    trigger: discord.VoiceChannel | None,
    prefix: str,
) -> discord.Embed:
    target = trigger.mention if trigger is not None else "**Join to Create**"
    embed = base_embed(
        title="🔊 VoiceMaster",
        description=(
            "### Your channel, your rules\n"
            "Press **Join to Create** and you get a private voice channel plus a "
            "live control panel inside it — name, owner, members, lock, limit and "
            "bitrate stay up to date automatically.\n\n"
            f"You can also join {target} directly."
        ),
    )
    embed.set_image(url="attachment://voicemaster-menu.png")
    return brand(
        embed,
        footer=f"Button replies are private  ·  {prefix}voicemaster for text commands",
    )


def voicemaster_panel_embed(
    *,
    channel: discord.VoiceChannel,
    owner_id: int | None,
    prefix: str = "p!",
) -> discord.Embed:
    guild = channel.guild
    owner = guild.get_member(owner_id) if owner_id else None
    locked = channel.overwrites_for(guild.default_role).connect is False
    hidden = channel.overwrites_for(guild.default_role).view_channel is False
    humans = [member for member in channel.members if not member.bot]
    owner_present = owner is not None and owner in channel.members

    if owner_present:
        description = (
            "Only the owner can use these buttons. Everything here updates by "
            "itself as the channel changes."
        )
    else:
        description = (
            "The owner left — anyone still inside can press **Claim** to take "
            "the channel over."
        )

    if humans:
        names = ", ".join(member.mention for member in humans[:10])
        if len(humans) > 10:
            names += f" … +{len(humans) - 10} more"
        members = f"`{len(humans)}`\n{names}"
    else:
        members = "Nobody is connected."

    embed = base_embed(
        title=f"🔊 {channel.name}",
        description=description,
    )
    embed.add_field(
        name="👑 Owner",
        value=(
            owner.mention
            if owner is not None
            else (f"<@{owner_id}>" if owner_id else "Nobody")
        ),
        inline=True,
    )
    embed.add_field(
        name="🔒 Access",
        value="Locked" if locked else "Open to everyone",
        inline=True,
    )
    embed.add_field(
        name="🙈 Visibility",
        value="Hidden from the server" if hidden else "Visible in the server",
        inline=True,
    )
    embed.add_field(
        name="⚙️ Limit",
        value=str(channel.user_limit) if channel.user_limit else "Unlimited",
        inline=True,
    )
    embed.add_field(
        name="🎚️ Bitrate",
        value=f"{channel.bitrate // 1000} kbps",
        inline=True,
    )
    embed.add_field(
        name="📅 Created",
        value=discord.utils.format_dt(channel.created_at, "R"),
        inline=True,
    )
    embed.add_field(name="👥 In the channel", value=members, inline=False)
    return brand(embed, footer=f"Use the buttons · {prefix}voicemaster for text commands")



