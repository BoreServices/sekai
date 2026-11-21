import discord

from core.emojis import iconize
from view.base import (
    ACCENT,
    INFO_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    base_embed,
    brand)


def ticket_panel_embed(*, prefix: str) -> discord.Embed:
    embed = base_embed(
        description=(
            f"### {iconize('🎫')} Need a hand?\n"
            "Press **Open a Ticket** below and I'll make a private channel for you "
            "and the staff team.\n"
            "One open ticket per member — close it when you're done."
        ))
    embed.set_image(url="attachment://ticket-panel.png")
    return brand(embed, footer=f"Press the button  ·  {prefix}ticket for commands")


def ticket_welcome_embed(
    *,
    number: int,
    member: discord.Member,
    staff_role: discord.Role,
    topic: str) -> discord.Embed:
    embed = base_embed(
        description=(
            f"Thanks for reaching out, {member.mention}.\n\n"
            f"**{discord.utils.escape_markdown(topic)}**\n\n"
            f"A member of {staff_role.mention} will pick this up shortly. "
            "Add any screenshots or extra details below."
        ),
        color=SUCCESS_COLOR)
    embed.add_field(name="Ticket", value=f"#{number:04d}", inline=True)
    embed.add_field(name="Opened by", value=member.mention, inline=True)
    embed.add_field(name="Status", value="Waiting for staff", inline=True)
    embed.add_field(
        name="Managing this ticket",
        value=(
            "Claim it as staff, add people who should join, rename the channel "
            "or close it with the transcript going to the opener's DMs."
        ),
        inline=False)
    return brand(embed)


def ticket_setup_embed(
    *,
    category: discord.CategoryChannel,
    staff_role: discord.Role,
    panel: discord.TextChannel,
    logs: discord.TextChannel | None,
    prefix: str,
    already: bool = False) -> discord.Embed:
    description = (
        "Your ticket system is already set up — the panel was refreshed.\n\n"
        if already
        else "Your ticket system is ready.\n\n"
    )
    description += (
        f"Members press **Open a Ticket** on {panel.mention} and get a private "
        f"channel under {category.mention}. Only the opener, the bot and "
        f"{staff_role.mention} can see it."
    )
    embed = base_embed(
        title="🎫 Ticket system",
        description=description,
        color=SUCCESS_COLOR)
    embed.add_field(name="📁 Category", value=category.mention, inline=True)
    embed.add_field(name="🛡️ Staff role", value=staff_role.mention, inline=True)
    embed.add_field(name="🖼️ Panel channel", value=panel.mention, inline=True)
    embed.add_field(
        name="📮 Transcript log",
        value=(
            logs.mention
            if logs is not None
            else "Off — transcripts go to the opener's DMs only."
        ),
        inline=False)
    embed.add_field(
        name="⚙️ Staff commands",
        value=(
            f"`{prefix}ticket list` — every open ticket\n"
            f"`{prefix}ticket claim` / `add` / `remove` / `rename` — inside a ticket\n"
            f"`{prefix}ticket close [reason]` — close and DM a transcript\n"
            f"`{prefix}ticket setup` — reconfigure or refresh the panel\n"
            f"`{prefix}ticket reset` — remove the panel and configuration"
        ),
        inline=False)
    return brand(embed)


def ticket_claim_embed(*, number: int, member: discord.Member) -> discord.Embed:
    embed = base_embed(
        description=f"{member.mention} claimed ticket **#{number:04d}**.",
        color=SUCCESS_COLOR)
    return brand(embed)


def ticket_close_confirm_embed(
    *, number: int, reason: str | None = None
) -> discord.Embed:
    embed = base_embed(
        title=f"Close ticket #{number:04d}?",
        description=(
            "The channel will be deleted for everyone. The opener gets a "
            "transcript by DM."
        ),
        color=WARNING_COLOR)
    if reason:
        embed.add_field(name="Reason", value=discord.utils.escape_markdown(reason))
    return brand(embed)


def ticket_closed_dm_embed(
    *,
    guild_name: str,
    number: int,
    closed_by: str,
    reason: str | None = None,
    transcript: bool = True,
    url: str | None = None) -> discord.Embed:
    description = (
        f"Your ticket **#{number:04d}** in "
        f"**{discord.utils.escape_markdown(guild_name)}** was closed by {closed_by}."
    )
    if transcript:
        description += "\nThe transcript is attached as a `.txt` file."
    if url:
        description += f"\n[View the transcript online]({url})"
    embed = base_embed(
        title=f"🎫 Ticket #{number:04d} closed",
        description=description,
        color=INFO_COLOR)
    if reason:
        embed.add_field(name="Reason", value=discord.utils.escape_markdown(reason))
    return brand(embed)


def ticket_list_embed(
    *, entries: list[tuple[int, str]], total: int
) -> discord.Embed:
    if total == 0:
        description = "No tickets are open right now."
    elif total == 1:
        description = "**1** open ticket."
    else:
        description = f"**{total}** open tickets."
    embed = base_embed(
        title="🎫 Open tickets",
        description=description,
        color=ACCENT)
    for number, value in entries:
        embed.add_field(name=f"Ticket #{number:04d}", value=value, inline=False)
    if total > len(entries):
        return brand(
            embed, footer=f"Showing {len(entries)} of {total} open tickets"
        )
    return brand(embed)
