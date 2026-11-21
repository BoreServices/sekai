"""
src/misc/consent.py — Terms of Service + Privacy Policy consent gate.

On the first command a user ever runs the bot sends them an embed linking
to the ToS and Privacy Policy. The command is paused until they click
"I Agree", or cancelled if they click "Decline" (or the prompt times out).

Consent is stored per user in the `user_consent` table and checked in-memory
via a local set for subsequent commands (no DB hit after the first agree).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

import discord
from discord.ext import commands

from core.emojis import emoji_partial, markup

log = logging.getLogger("sekai.consent")

TERMS_URL   = "https://bot.phaseworld.top/terms"
PRIVACY_URL = "https://bot.phaseworld.top/privacy"

# Current policy version. Bump this to force all users to re-agree.
POLICY_VERSION = 2

# In-memory cache — user IDs that have already agreed (avoids a DB hit on
# every command after the first one).
_agreed: set[int] = set()

# Pending consent futures: user_id -> Future that the command waits on.
# True = agreed, False = declined / timed out.
_pending: dict[int, asyncio.Future[bool]] = {}

CONSENT_TIMEOUT = 120   # seconds before the prompt auto-expires


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _has_agreed(db, user_id: int) -> bool:
    row = await db.fetchone(
        "SELECT version FROM user_consent WHERE user_id = ?",
        (user_id,))
    if row is None:
        return False
    return row["version"] >= POLICY_VERSION


async def _record_consent(db, user_id: int) -> None:
    await db.execute(
        """
        INSERT INTO user_consent (user_id, version)
        VALUES (?, ?)
        ON CONFLICT (user_id) DO UPDATE SET
            agreed_at = datetime('now'),
            version   = excluded.version
        """,
        (user_id, POLICY_VERSION))


# ---------------------------------------------------------------------------
# The consent embed
# ---------------------------------------------------------------------------

def _consent_embed() -> discord.Embed:
    embed = discord.Embed(
        description=(
            "By using **Sekai**, you agree to our policies.\n\n"
            f"{markup('paper', '📄')} **[Terms of Service]({TERMS_URL})**\n"
            f"{markup('shield', '🔒')} **[Privacy Policy]({PRIVACY_URL})**\n\n"
            "Please read them before agreeing. "
            "Clicking **I Agree** means you accept both documents.\n\n"
            "> You only need to do this once.\n"
            "> ⏰ This prompt expires in 2 minutes."
        ),
        color=0x9B59B6,  # purple — matches the bot's branding
    )
    return embed


# ---------------------------------------------------------------------------
# The consent view
# ---------------------------------------------------------------------------

class ConsentView(discord.ui.View):
    def __init__(self, user_id: int, future: asyncio.Future[bool]) -> None:
        super().__init__(timeout=CONSENT_TIMEOUT)
        self.user_id = user_id
        self.future = future

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This consent prompt isn't for you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="I Agree",
        style=discord.ButtonStyle.success,
        emoji=emoji_partial("checkmark") or "✅")
    async def agree(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"{markup('checkmark', '✅')} You're all set!\n\n"
                "Thanks for agreeing. Your command is running now.",
                color=0x57F287),
            view=self)
        if not self.future.done():
            self.future.set_result(True)
        self.stop()

    @discord.ui.button(
        label="Decline",
        style=discord.ButtonStyle.danger,
        emoji=emoji_partial("crossmark") or "❌")
    async def decline(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"{markup('crossmark', '❌')} Command cancelled\n\n"
                "You declined the Terms of Service and Privacy Policy.\n"
                "You can run any command again to see this prompt.",
                color=0xED4245),
            view=self)
        if not self.future.done():
            self.future.set_result(False)
        self.stop()

    async def on_timeout(self) -> None:
        if not self.future.done():
            self.future.set_result(False)


# ---------------------------------------------------------------------------
# Public API used by the on_command listener
# ---------------------------------------------------------------------------

async def ensure_consent(ctx: commands.Context) -> bool:
    """
    Return True if the user has already agreed (or just agreed now).
    Return False if they declined or the prompt timed out — the caller
    should then raise commands.CheckFailure to abort the command.

    This is called from the on_command listener BEFORE the command runs.
    """
    user_id = ctx.author.id

    # Fast path: already in memory cache
    if user_id in _agreed:
        return True

    # DB check — covers bot restarts
    db = getattr(ctx.bot, "db", None)
    if db is not None and await _has_agreed(db, user_id):
        _agreed.add(user_id)
        return True

    # User hasn't agreed yet — but someone else may already have a pending
    # prompt for this user (shouldn't happen often, but be safe)
    if user_id in _pending:
        # Another command triggered a prompt; let this one share the result
        try:
            result = await asyncio.wait_for(
                asyncio.shield(_pending[user_id]), timeout=CONSENT_TIMEOUT
            )
        except asyncio.TimeoutError:
            return False
        return result

    # Create a new future so the command can await on it
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    _pending[user_id] = future

    view = ConsentView(user_id=user_id, future=future)

    try:
        # Try to DM first; fall back to channel if DMs are closed
        try:
            msg = await ctx.author.send(embed=_consent_embed(), view=view)
            log.debug("Sent consent DM to user %s", user_id)
        except discord.Forbidden:
            msg = await ctx.send(
                content=ctx.author.mention,
                embed=_consent_embed(),
                view=view)
            log.debug("Sent consent in channel for user %s (DMs closed)", user_id)

        agreed = await asyncio.wait_for(future, timeout=CONSENT_TIMEOUT + 5)
    except asyncio.TimeoutError:
        agreed = False
        # Disable the buttons if the message is still there
        for child in view.children:
            child.disabled = True
        with suppress(Exception):
            await msg.edit(
                embed=discord.Embed(
                    description=f"{markup('timer', '⏰')} Consent prompt expired\n\n"
                    "Run any command again to see this prompt.",
                    color=0xFEE75C),
                view=view)
    finally:
        _pending.pop(user_id, None)

    if agreed:
        _agreed.add(user_id)
        if db is not None:
            await _record_consent(db, user_id)
        log.info("User %s agreed to ToS/Privacy Policy v%s", user_id, POLICY_VERSION)
    else:
        log.info("User %s declined or timed out on consent v%s", user_id, POLICY_VERSION)

    return agreed


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup(bot) -> None:
    @bot.listen("on_command")
    async def check_consent(ctx: commands.Context) -> None:
        """
        Fires before every command invocation. If the user hasn't agreed yet,
        send the consent prompt and cancel the command if they decline.

        discord.py has already parsed and is about to invoke the command when
        on_command fires; to abort it we raise CommandError which discord.py
        routes to on_command_error (handled in core/bot.py — shows the error
        embed). We use a before_invoke hook on the bot instead so we can
        actually block execution.
        """
        # on_command fires right before invoke — we can't block here directly.
        # The actual blocking is done via bot.before_invoke (registered below).
        pass

    @bot.before_invoke
    async def gate_consent(ctx: commands.Context) -> None:
        """
        before_invoke runs synchronously in the command pipeline and CAN raise
        to abort execution. We raise CheckFailure which is caught quietly by
        the existing error handler.
        """
        user_id = ctx.author.id

        # Fast path — already agreed
        if user_id in _agreed:
            return

        agreed = await ensure_consent(ctx)
        if not agreed:
            raise commands.CheckFailure(
                "You must agree to the Terms of Service and Privacy Policy "
                "before using this bot. Run any command again to see the prompt."
            )
