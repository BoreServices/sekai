import math
import platform
import re

import discord
from discord.ext import commands

from config.settings import settings
from core import music
from view import avatar_decoration_embed, error_embed, info_embed


def _when(value) -> str:
    if value is None:
        return "Unknown"
    return (
        f"{discord.utils.format_dt(value, 'D')} "
        f"({discord.utils.format_dt(value, 'R')})"
    )


def _uptime(bot) -> str:
    total = int((discord.utils.utcnow() - bot.start_time).total_seconds())
    days, rest = divmod(total, 86400)
    hours, minutes = divmod(rest // 60, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _footer(ctx: commands.Context) -> str:
    return (
        f"Requested by {ctx.author}  ·  {settings.bot_name}  ·  "
        f"Owned by {settings.owner_name}"
    )


def _shorten(text: str, limit: int = 1000) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


INVITE_LINK = re.compile(
    r"(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]+)",
    re.IGNORECASE)


def _invite_code(text: str) -> str | None:
    match = INVITE_LINK.search(text.strip())
    if match is not None:
        return match.group(1)
    code = text.strip()
    return code if re.fullmatch(r"[A-Za-z0-9-]{2,64}", code) else None


def _asset_links(asset: discord.Asset) -> str:
    formats = ["png", "jpg", "webp"]
    if asset.is_animated():
        formats.append("gif")
    return "  ·  ".join(
        f"[{name.upper()}]({asset.replace(size=4096, format=name).url})"
        for name in formats
    )


def _display_name(target: discord.abc.User) -> str:
    return getattr(target, "display_name", str(target))


def setup(bot) -> None:
    @bot.command(
        name="userinfo",
        aliases=["ui"],
        help="Show information about a user.",
        usage="userinfo [member]")
    async def userinfo(
        ctx: commands.Context, user: discord.User | None = None
    ) -> None:
        target = user or ctx.author
        member = (
            target
            if isinstance(target, discord.Member)
            else (ctx.guild.get_member(target.id) if ctx.guild else None)
        )

        fields = [
            ("🆔 ID", f"`{target.id}`", True),
            ("🤖 Bot", "Yes" if target.bot else "No", True),
            ("📅 Account created", _when(target.created_at), False),
        ]

        if member is not None:
            fields.append(("📥 Joined server", _when(member.joined_at), False))
            top_role = member.top_role
            fields.append(
                (
                    "🏷️ Top role",
                    top_role.mention
                    if top_role != ctx.guild.default_role
                    else "None",
                    True)
            )
            roles = [
                role.mention
                for role in reversed(member.roles)
                if role != ctx.guild.default_role
            ]
            if roles:
                shown = " ".join(roles[:12])
                if len(roles) > 12:
                    shown += f" … +{len(roles) - 12} more"
            else:
                shown = "None"
            fields.append((f"🎭 Roles ({len(roles)})", shown, False))

        # Banners are not included in member payloads; they only come from
        # fetch_user, so this costs one API call per invocation.
        banner_url = None
        try:
            fetched = await ctx.bot.fetch_user(target.id)
        except discord.HTTPException:
            fetched = None
        if fetched is not None and fetched.banner is not None:
            banner_url = fetched.banner.url

        await ctx.send(
            embed=info_embed(
                title=(
                    f"👤 "
                    f"{getattr(target, 'display_name', str(target))}"
                ),
                description=target.mention,
                fields=fields,
                icon_url=ctx.bot.user.display_avatar.url if ctx.bot.user else None,
                thumbnail_url=target.display_avatar.url,
                image_url=banner_url,
                footer=_footer(ctx))
        )

    @bot.command(
        name="avatar",
        aliases=["av", "pfp"],
        help="Show a user's avatar and decoration (yours by default).",
        usage="avatar [member]")
    async def avatar(
        ctx: commands.Context, user: discord.User | None = None
    ) -> None:
        target = user or ctx.author
        member = (
            target
            if isinstance(target, discord.Member)
            else (ctx.guild.get_member(target.id) if ctx.guild else None)
        )
        global_asset = target.avatar or target.default_avatar
        server_asset = member.guild_avatar if member is not None else None
        asset = server_asset or global_asset

        fields = [("🆔 ID", f"`{target.id}`", True)]
        if server_asset is not None:
            fields.append(
                ("🌐 Global avatar", _asset_links(global_asset), False)
            )

        embeds = [
            info_embed(
                title=f"🖼️ {_display_name(target)}'s avatar",
                description=f"{target.mention}\n{_asset_links(asset)}",
                fields=fields,
                image_url=asset.url,
                footer=_footer(ctx))
        ]
        decoration = target.avatar_decoration
        if decoration is not None:
            embeds.append(
                avatar_decoration_embed(
                    name=_display_name(target),
                    url=decoration.url.split("?", 1)[0],
                    footer=_footer(ctx))
            )

        await ctx.send(embeds=embeds)

    @bot.command(
        name="banner",
        aliases=["userbanner", "ub"],
        help="Show a user's profile banner (yours by default).",
        usage="banner [member]")
    async def banner(
        ctx: commands.Context, user: discord.User | None = None
    ) -> None:
        target = user or ctx.author
        # Banners are not part of cached user payloads; they only come from
        # fetch_user, so this costs one API call per invocation.
        try:
            fetched = await bot.fetch_user(target.id)
        except discord.HTTPException:
            await ctx.send(
                embed=error_embed("I couldn't load that profile right now.")
            )
            return

        if fetched.banner is None:
            await ctx.send(
                embed=error_embed(
                    f"{_display_name(target)} doesn't have a banner set."
                )
            )
            return

        fields = [("🆔 ID", f"`{target.id}`", True)]
        if fetched.accent_color is not None:
            fields.append(("🎨 Accent", str(fetched.accent_color), True))

        await ctx.send(
            embed=info_embed(
                title=f"🎏 {_display_name(target)}'s banner",
                description=f"{target.mention}\n{_asset_links(fetched.banner)}",
                fields=fields,
                image_url=fetched.banner.url,
                footer=_footer(ctx))
        )

    @bot.command(
        name="servericon",
        aliases=["sicon", "icon"],
        help="Show this server's icon.",
        usage="servericon")
    @commands.guild_only()
    async def servericon(ctx: commands.Context) -> None:
        guild = ctx.guild
        if guild.icon is None:
            await ctx.send(
                embed=error_embed("This server doesn't have an icon set.")
            )
            return

        await ctx.send(
            embed=info_embed(
                title=f"🖼️ {guild.name} icon",
                description=_asset_links(guild.icon),
                fields=[("🆔 ID", f"`{guild.id}`", True)],
                image_url=guild.icon.url,
                footer=_footer(ctx))
        )

    @bot.command(
        name="serverbanner",
        aliases=["sbanner", "guildbanner"],
        help="Show this server's banner.",
        usage="serverbanner")
    @commands.guild_only()
    async def serverbanner(ctx: commands.Context) -> None:
        guild = ctx.guild
        if guild.banner is None:
            await ctx.send(
                embed=error_embed("This server doesn't have a banner set.")
            )
            return

        await ctx.send(
            embed=info_embed(
                title=f"🎏 {guild.name} banner",
                description=_asset_links(guild.banner),
                fields=[("🆔 ID", f"`{guild.id}`", True)],
                image_url=guild.banner.url,
                footer=_footer(ctx))
        )

    @bot.command(
        name="serverinfo",
        aliases=["si"],
        help="Show information about this server.",
        usage="serverinfo")
    @commands.guild_only()
    async def serverinfo(ctx: commands.Context) -> None:
        guild = ctx.guild
        owner = (
            guild.owner.mention
            if guild.owner is not None
            else f"<@{guild.owner_id}>"
        )
        channels = (
            f"`{len(guild.text_channels)}` text · "
            f"`{len(guild.voice_channels)}` voice · "
            f"`{len(guild.categories)}` categories · "
            f"`{len(guild.threads)}` threads"
        )
        fields = [
            ("🆔 ID", f"`{guild.id}`", True),
            ("👑 Owner", owner, True),
            ("📅 Created", _when(guild.created_at), True),
            ("👥 Members", f"`{guild.member_count or 0:,}`", True),
            ("🎭 Roles", f"`{len(guild.roles) - 1}`", True),
            (
                "🚀 Boosts",
                f"Tier {guild.premium_tier} · "
                f"`{guild.premium_subscription_count}`",
                True),
            ("📚 Channels", channels, False),
            (
                "🛡️ Verification",
                guild.verification_level.name.replace("_", " ").title(),
                True),
            ("🌍 Locale", str(guild.preferred_locale), True),
        ]

        await ctx.send(
            embed=info_embed(
                title=f"🏠 {guild.name}",
                description=guild.description,
                fields=fields,
                icon_url=ctx.bot.user.display_avatar.url if ctx.bot.user else None,
                thumbnail_url=guild.icon.url if guild.icon else None,
                footer=_footer(ctx))
        )

    @bot.command(
        name="inviteinfo",
        aliases=["inv", "invite"],
        help="Show information about a Discord invite link or code.",
        usage="inviteinfo <invite link or code>")
    async def inviteinfo(ctx: commands.Context, invite: str | None = None) -> None:
        if invite is None:
            await ctx.send(
                embed=error_embed(
                    f"Usage: `{ctx.prefix}inviteinfo <invite link or code>`"
                )
            )
            return

        code = _invite_code(invite)
        if code is None:
            await ctx.send(
                embed=error_embed("That doesn't look like an invite link or code.")
            )
            return

        try:
            snapshot = await ctx.bot.fetch_invite(
                code, with_counts=True, with_expiration=True
            )
        except discord.NotFound:
            await ctx.send(
                embed=error_embed("That invite is invalid or has expired.")
            )
            return
        except discord.HTTPException:
            await ctx.send(
                embed=error_embed(
                    "Discord didn't return that invite. Try again in a moment."
                )
            )
            return

        fields = [("🆔 Code", f"`{snapshot.code}`", True)]
        if snapshot.guild is not None:
            fields.append(("🏠 Server", snapshot.guild.name, True))
            if snapshot.approximate_member_count is not None:
                fields.append(
                    ("👥 Members", f"`{snapshot.approximate_member_count:,}`", True)
                )
            if snapshot.approximate_presence_count is not None:
                fields.append(
                    ("🟢 Online", f"`{snapshot.approximate_presence_count:,}`", True)
                )
        if snapshot.channel is not None:
            fields.append(("📄 Channel", snapshot.channel.mention, True))
        if snapshot.inviter is not None:
            fields.append(("👤 Inviter", snapshot.inviter.mention, True))
        fields.append(("📅 Created", _when(snapshot.created_at), True))
        if snapshot.expires_at is not None:
            fields.append(("⏳ Expires", _when(snapshot.expires_at), True))
        elif snapshot.max_age:
            fields.append(("⏳ Expires", "Unknown", True))
        else:
            fields.append(("⏳ Expires", "Never", True))
        if snapshot.max_uses:
            fields.append(("🔢 Max uses", f"`{snapshot.max_uses}`", True))
        fields.append(("🔗 Invite", snapshot.url, False))

        guild = snapshot.guild
        title = f"📨 {guild.name}" if guild is not None else "📨 Group invite"
        await ctx.send(
            embed=info_embed(
                title=title,
                description=guild.description if guild is not None else None,
                fields=fields,
                icon_url=ctx.bot.user.display_avatar.url if ctx.bot.user else None,
                thumbnail_url=guild.icon.url if guild is not None and guild.icon else None,
                footer=_footer(ctx))
        )

    @bot.command(
        name="roleinfo",
        aliases=["ri"],
        help="Show information about a role (yours by default).",
        usage="roleinfo [role]")
    @commands.guild_only()
    async def roleinfo(
        ctx: commands.Context, role: discord.Role | None = None
    ) -> None:
        if role is None:
            author = ctx.author if isinstance(ctx.author, discord.Member) else None
            if author is not None and author.top_role != ctx.guild.default_role:
                role = author.top_role

        if role is None:
            await ctx.send(
                embed=error_embed(
                    f"Usage: `{ctx.prefix}roleinfo <role>` — "
                    "mention the role, use its ID or its name."
                )
            )
            return

        permissions = role.permissions
        if permissions.administrator:
            perm_value = "Administrator (all permissions)"
        else:
            names = [
                name.replace("_", " ").title() for name, value in permissions if value
            ]
            if names:
                perm_value = ", ".join(names[:12])
                if len(names) > 12:
                    perm_value += f" … +{len(names) - 12} more"
            else:
                perm_value = "None"

        if role.unicode_emoji:
            title = f"{role.unicode_emoji} {role.name}"
        else:
            title = f"🏷️ {role.name}"

        fields = [
            ("🆔 ID", f"`{role.id}`", True),
            ("🎨 Color", str(role.color), True),
            ("📊 Position", f"`{role.position}`", True),
            ("👥 Members", f"`{len(role.members)}`", True),
            ("🔔 Mentionable", "Yes" if role.mentionable else "No", True),
            ("📌 Hoisted", "Yes" if role.hoist else "No", True),
            ("📅 Created", _when(role.created_at), False),
            ("🛡️ Permissions", perm_value, False),
        ]

        await ctx.send(
            embed=info_embed(
                title=title,
                description=role.mention,
                fields=fields,
                icon_url=ctx.bot.user.display_avatar.url if ctx.bot.user else None,
                thumbnail_url=role.icon.url if role.icon else None,
                footer=_footer(ctx))
        )

    @bot.command(
        name="channelinfo",
        aliases=["ci"],
        help="Show information about a channel (this one by default).",
        usage="channelinfo [channel]")
    @commands.guild_only()
    async def channelinfo(
        ctx: commands.Context,
        channel: discord.abc.GuildChannel | discord.Thread | None = None) -> None:
        target = channel or ctx.channel
        category = getattr(target, "category", None)
        position = getattr(target, "position", None)
        nsfw = getattr(target, "nsfw", None)

        if isinstance(target, discord.Thread):
            icon = "🧵"
        elif isinstance(target, (discord.VoiceChannel, discord.StageChannel)):
            icon = "🔊"
        elif isinstance(target, discord.CategoryChannel):
            icon = "📁"
        else:
            icon = "📄"

        fields = [
            ("🆔 ID", f"`{target.id}`", True),
            ("📄 Type", str(target.type).replace("_", " ").title(), True),
            ("📅 Created", _when(target.created_at), True),
        ]
        if category is not None:
            fields.append(("📁 Category", category.name, True))
        if position is not None:
            fields.append(("📊 Position", f"`{position}`", True))

        topic = getattr(target, "topic", None)
        if topic:
            fields.append(("📝 Topic", _shorten(topic), False))

        slowmode = getattr(target, "slowmode_delay", 0)
        if slowmode:
            fields.append(("🐌 Slowmode", f"`{slowmode}s`", True))
        if nsfw is not None:
            fields.append(("🔞 NSFW", "Yes" if nsfw else "No", True))

        if isinstance(target, discord.Thread):
            fields.append(("🧵 Parent", target.parent.mention, True))
            fields.append(("👥 Members", f"`{target.member_count}`", True))
            fields.append(
                ("🗄️ Archived", "Yes" if target.archived else "No", True)
            )
            fields.append(("🔒 Locked", "Yes" if target.locked else "No", True))
        elif isinstance(target, (discord.VoiceChannel, discord.StageChannel)):
            fields.append(
                ("🎚️ Bitrate", f"`{target.bitrate // 1000} kbps`", True)
            )
            fields.append(("👥 User limit", f"`{target.user_limit or '∞'}`", True))
        else:
            threads = getattr(target, "threads", [])
            fields.append(("🧵 Active threads", f"`{len(threads)}`", True))

        overwrites = getattr(target, "overwrites", None)
        if overwrites is not None:
            fields.append(("🔐 Permission overwrites", f"`{len(overwrites)}`", True))

        await ctx.send(
            embed=info_embed(
                title=f"{icon} {target.name}",
                description=target.mention,
                fields=fields,
                icon_url=ctx.bot.user.display_avatar.url if ctx.bot.user else None,
                footer=_footer(ctx))
        )
