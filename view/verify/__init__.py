import discord

from core.emojis import emoji_partial
from view.base import ERROR_COLOR, WARNING_COLOR, base_embed, brand
from view.error import error_embed
from view.success import success_embed


def verify_panel_embed() -> discord.Embed:
    embed = base_embed(
        title="🔐 Verification",
        description=(
            "Click **Verify** to open the verification page. You'll sign in "
            "with Discord there, and the server will give you access "
            "automatically."
        ))
    embed.add_field(
        name="Why?",
        value=(
            "Verification keeps raids and throwaway accounts out. It only asks "
            "for your Discord username — no messages or servers are read."
        ),
        inline=False)
    embed.add_field(
        name="Trouble?",
        value=(
            "If the page says your link expired, click **Verify** again. If "
            "you can't sign in, ask a staff member to check the OAuth2 setup."
        ),
        inline=False)
    return brand(embed)


def verify_link_embed(
    url: str, *, minutes: int, guild_name: str | None = None
) -> discord.Embed:
    where = f" for **{discord.utils.escape_markdown(guild_name)}**" if guild_name else ""
    embed = base_embed(
        title="✅ Finish verification",
        description=(
            f"Open the page below{where} and sign in with Discord. "
            f"The link is personal, works once and expires in {minutes} minutes."
        ))
    embed.add_field(name="Verification page", value=url, inline=False)
    return brand(embed)


def verify_dm_embed(
    guild: discord.Guild, url: str, *, hours: int
) -> discord.Embed:
    embed = base_embed(
        title=f"🔐 Verify to join {discord.utils.escape_markdown(guild.name)}",
        description=(
            "You're almost in! Open the verification page below and sign in "
            "with Discord — the server will unlock for you automatically.\n\n"
            f"This link is personal, works once and expires in {hours} hours."
        ))
    embed.add_field(name="Verification page", value=url, inline=False)
    return brand(embed)


def verify_settings_embed(
    *,
    label: str,
    verified_role: str,
    unverified_role: str,
    panel: str,
    website: str,
    account_days: int,
    raid: str,
    threshold: int,
    window: int,
    verified_members: int) -> discord.Embed:
    embed = base_embed(title=f"🔐 Verification · {label}")
    embed.add_field(
        name="Roles",
        value=f"Verified: {verified_role}\nUnverified: {unverified_role}",
        inline=True)
    embed.add_field(name="Website", value=website, inline=True)
    embed.add_field(name="Panel", value=panel, inline=True)
    embed.add_field(
        name="Account age gate",
        value=(
            f"Kick accounts younger than **{account_days} days**"
            if account_days
            else "off"
        ),
        inline=True)
    embed.add_field(name="Raid mode", value=raid, inline=True)
    embed.add_field(
        name="Raid trigger",
        value=f"{threshold} joins / {window}s",
        inline=True)
    embed.add_field(
        name="Verified members",
        value=f"{verified_members:,}",
        inline=True)
    return brand(embed)


def raid_alert_embed(
    guild: discord.Guild,
    *,
    joins: int,
    window: int,
    minutes: int,
    automatic: bool) -> discord.Embed:
    embed = base_embed(
        description=(
            "🚨 Possible raid detected\n\n"
            f"**{joins}** members joined **{discord.utils.escape_markdown(guild.name)}** "
            f"within {window} seconds. Verification is now locked for "
            f"{minutes} minutes, so new members stay unverified until they pass."
        ),
        color=WARNING_COLOR)
    embed.add_field(
        name="What to do",
        value=(
            "Check recent joins, then run `verify raid off` when it settles. "
            "Turn the threshold down with `verify settings` or keep this "
            "server locked while you clean up."
        ),
        inline=False)
    return brand(embed)


def verify_kick_embed(
    member: discord.Member, *, required_days: int
) -> discord.Embed:
    embed = base_embed(
        title="Join blocked · account too new",
        description=(
            f"**{discord.utils.escape_markdown(str(member))}** (`{member.id}`) "
            f"was kicked because their account is younger than "
            f"**{required_days} days**."
        ),
        color=ERROR_COLOR)
    embed.add_field(
        name="Account created",
        value=f"<t:{int(member.created_at.timestamp())}:R>",
        inline=True)
    return brand(embed)


class VerifyLinkView(discord.ui.View):
    def __init__(self, url: str) -> None:
        super().__init__(timeout=600)
        self.add_item(
            discord.ui.Button(
                label="Open verification page",
                style=discord.ButtonStyle.link,
                url=url,
                emoji="🔗")
        )


class VerifyPanelView(discord.ui.View):
    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        button = discord.ui.Button(
            label="Verify",
            style=discord.ButtonStyle.success,
            custom_id="verify:start",
            emoji=emoji_partial("checkmark") or "✅")
        button.callback = self.verify
        self.add_item(button)

    async def verify(self, interaction: discord.Interaction) -> None:
        from src.verification import state

        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Verification only works in a server."),
                ephemeral=True)
            return
        config = await state.get_config(self.bot, interaction.guild.id)
        if config is None or not config.enabled:
            await interaction.response.send_message(
                embed=error_embed(
                    "Verification isn't set up here — ask staff to run "
                    "`verify setup`."
                ),
                ephemeral=True)
            return
        if await state.is_verified(
            self.bot, interaction.guild.id, interaction.user.id
        ):
            await interaction.response.send_message(
                embed=success_embed("You're already verified."),
                ephemeral=True)
            return
        if not state.website_configured(self.bot):
            await interaction.response.send_message(
                embed=error_embed(
                    "The verification website isn't configured. Ask staff to "
                    "set the OAuth2 client secret and redirect URL."
                ),
                ephemeral=True)
            return
        if not state.link_limiter.allow(interaction.user.id):
            await interaction.response.send_message(
                embed=error_embed("Give the last link a minute before asking for another."),
                ephemeral=True)
            return

        code = state.new_code(interaction.guild.id, interaction.user.id)
        config = await state.get_config(self.bot, interaction.guild.id)
        url = state.verify_url(
            code,
            config.url_path if config else None,
            config.custom_domain if config else None)
        await interaction.response.send_message(
            embed=verify_link_embed(
                url,
                minutes=state.CODE_TTL // 60,
                guild_name=interaction.guild.name),
            view=VerifyLinkView(url),
            ephemeral=True)
