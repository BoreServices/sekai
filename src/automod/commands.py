import logging
import re

import discord
from discord.ext import commands

from src.automod import state
from view import error_embed, info_embed, success_embed

log = logging.getLogger("sekai.automod")

ON_VALUES = {"on", "enable", "enabled", "true", "yes"}
OFF_VALUES = {"off", "disable", "disabled", "false", "no"}
MIN_MENTIONS = 1
MAX_MENTIONS = 50

INVITE_REGEX = r"(?:discord\.gg|discord(?:app)?\.com\/invite|discord\.me|dsc\.gg)\/[\w-]+"
LINK_REGEX = r"https?:\/\/\S+"
WALL_OF_TEXT_REGEX = r"[\s\S]{1200,}"
# Rough emoji-spam detector: many emoji/pictographs in one message.
EMOJI_SPAM_REGEX = r"(?:[\U0001F300-\U0001FAFF\u2600-\u27BF]\s*){12,}"

FEATURE_LABELS = {
    "invites": "Invites",
    "links": "Links",
    "mentionspam": "Mention spam",
    "spam": "Spam",
    "walloftext": "Wall of text",
    "emojispam": "Emoji spam",
}


def _switch(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in ON_VALUES:
        return True
    if lowered in OFF_VALUES:
        return False
    return None


def _state_text(value: bool) -> str:
    return "on" if value else "off"


async def _fetch_sekai_rules(guild: discord.Guild) -> dict[str, discord.AutoModRule]:
    # discord.py renamed fetch_auto_moderation_rules -> fetch_automod_rules in
    # 2.6; support both so this keeps working across 2.x.
    fetch = getattr(guild, "fetch_automod_rules", None)
    if fetch is None:
        fetch = getattr(guild, "fetch_auto_moderation_rules", None)
    if fetch is None:
        return {}
    try:
        rules = await fetch()
    except discord.HTTPException:
        return {}
    found: dict[str, discord.AutoModRule] = {}
    for rule in rules:
        feature = state.NAME_TO_FEATURE.get(rule.name)
        if feature:
            found[feature] = rule
    return found


async def _ensure_bot_perms(ctx: commands.Context) -> bool:
    me = ctx.guild.me
    if me is None or not me.guild_permissions.manage_guild:
        await ctx.send(
            embed=error_embed(
                "I need the **Manage Server** permission to manage Discord AutoMod rules."
            )
        )
        return False
    return True


async def _delete_rule(rule: discord.AutoModRule) -> None:
    try:
        await rule.delete(reason="Sekai automod: feature disabled")
    except discord.HTTPException:
        pass


async def _enable_feature(
    guild: discord.Guild, feature: str, *, mention_limit: int | None = None
) -> str | None:
    name = state.FEATURE_RULE_NAMES[feature]
    existing = await _fetch_sekai_rules(guild)
    # Remove existing managed rule for a clean replace where needed.
    if feature in existing and feature not in {"mentionspam"}:
        await _delete_rule(existing[feature])
        existing.pop(feature, None)

    actions = [discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)]

    try:
        if feature == "spam":
            await guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam),
                actions=actions,
                enabled=True,
                reason="Sekai automod: enable spam",
            )
        elif feature == "mentionspam":
            limit = mention_limit or state.DEFAULT_MENTION_LIMIT
            if feature in existing:
                await existing[feature].edit(
                    trigger=discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.mention_spam,
                        mention_limit=limit,
                    ),
                    actions=actions,
                    enabled=True,
                    reason="Sekai automod: enable mention spam",
                )
            else:
                await guild.create_automod_rule(
                    name=name,
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.mention_spam,
                        mention_limit=limit,
                    ),
                    actions=actions,
                    enabled=True,
                    reason="Sekai automod: enable mention spam",
                )
        elif feature == "invites":
            await guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword,
                    regex_patterns=[INVITE_REGEX],
                ),
                actions=actions,
                enabled=True,
                reason="Sekai automod: enable invites",
            )
        elif feature == "links":
            await guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword,
                    regex_patterns=[LINK_REGEX],
                ),
                actions=actions,
                enabled=True,
                reason="Sekai automod: enable links",
            )
        elif feature == "walloftext":
            await guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword,
                    regex_patterns=[WALL_OF_TEXT_REGEX],
                ),
                actions=actions,
                enabled=True,
                reason="Sekai automod: enable wall of text",
            )
        elif feature == "emojispam":
            await guild.create_automod_rule(
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword,
                    regex_patterns=[EMOJI_SPAM_REGEX],
                ),
                actions=actions,
                enabled=True,
                reason="Sekai automod: enable emoji spam",
            )
        else:
            return "Unknown automod feature."
    except discord.Forbidden:
        return "I don't have permission to manage AutoMod rules in this server."
    except discord.HTTPException as exc:
        log.warning("Failed to enable automod %s in %s: %s", feature, guild.id, exc)
        return f"Discord rejected that AutoMod rule: {exc}"
    return None


async def _disable_feature(guild: discord.Guild, feature: str) -> str | None:
    rules = await _fetch_sekai_rules(guild)
    rule = rules.get(feature)
    if rule is None:
        return None
    try:
        await rule.delete(reason="Sekai automod: feature disabled")
    except discord.Forbidden:
        return "I don't have permission to manage AutoMod rules in this server."
    except discord.HTTPException as exc:
        log.warning("Failed to disable automod %s in %s: %s", feature, guild.id, exc)
        return f"Discord rejected that change: {exc}"
    return None


async def _status_embed(guild: discord.Guild) -> discord.Embed:
    rules = await _fetch_sekai_rules(guild)
    fields = []
    for feature in state.FEATURES:
        rule = rules.get(feature)
        on = rule is not None and getattr(rule, "enabled", True)
        label = FEATURE_LABELS[feature]
        extra = ""
        if feature == "mentionspam" and on:
            trigger = getattr(rule, "trigger", None)
            limit = getattr(trigger, "mention_limit", None)
            if limit:
                extra = f" (limit {limit})"
        fields.append((label, f"{_state_text(on)}{extra}", True))
    return info_embed(
        title="Automod",
        description=(
            "Uses Discord AutoMod rules managed by Sekai. "
            "Features: `emojispam`, `mentionspam`, `spam`, `walloftext`, `invites`, `links`."
        ),
        fields=fields
        + [
            (
                "Commands",
                "`automod emojispam on|off` · `automod mentionspam on [limit]|off` · "
                "`automod spam on|off` · `automod walloftext on|off` · "
                "`automod invites on|off` · `automod links on|off`",
                False,
            )
        ],
    )


async def _apply_toggle(
    ctx: commands.Context, feature: str, value: bool, *, mention_limit: int | None = None
) -> None:
    if not await _ensure_bot_perms(ctx):
        return
    err = (
        await _enable_feature(ctx.guild, feature, mention_limit=mention_limit)
        if value
        else await _disable_feature(ctx.guild, feature)
    )
    if err:
        await ctx.send(embed=error_embed(err))
        return
    label = FEATURE_LABELS[feature]
    extra = ""
    if feature == "mentionspam" and value and mention_limit:
        extra = f" (limit {mention_limit})"
    await ctx.send(embed=success_embed(f"{label} is now {_state_text(value)}{extra}."))


def setup(bot) -> None:
    @bot.group(
        name="automod",
        help="Manage Discord AutoMod filters (emojispam, mentionspam, spam, walloftext, invites, links).",
        usage="automod",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def automod(ctx: commands.Context) -> None:
        await ctx.send(embed=await _status_embed(ctx.guild))

    @automod.command(name="invites", help="Toggle Discord AutoMod blocking of invite links.", usage="automod invites <on|off>")
    @commands.has_permissions(manage_guild=True)
    async def invites(ctx: commands.Context, switch: str) -> None:
        value = _switch(switch)
        if value is None:
            await ctx.send(embed=error_embed("Use `on` or `off`."))
            return
        await _apply_toggle(ctx, "invites", value)

    @automod.command(name="links", help="Toggle Discord AutoMod blocking of links.", usage="automod links <on|off>")
    @commands.has_permissions(manage_guild=True)
    async def links(ctx: commands.Context, switch: str) -> None:
        value = _switch(switch)
        if value is None:
            await ctx.send(embed=error_embed("Use `on` or `off`."))
            return
        await _apply_toggle(ctx, "links", value)

    @automod.command(name="spam", help="Toggle Discord AutoMod spam filter.", usage="automod spam <on|off>")
    @commands.has_permissions(manage_guild=True)
    async def spam(ctx: commands.Context, switch: str) -> None:
        value = _switch(switch)
        if value is None:
            await ctx.send(embed=error_embed("Use `on` or `off`."))
            return
        await _apply_toggle(ctx, "spam", value)

    @automod.command(name="mentionspam", aliases=["mentions"], help="Toggle Discord AutoMod mention spam filter.", usage="automod mentionspam <on|off> [limit]")
    @commands.has_permissions(manage_guild=True)
    async def mentionspam(ctx: commands.Context, switch: str, limit: int | None = None) -> None:
        value = _switch(switch)
        if value is None:
            await ctx.send(embed=error_embed("Use `on` or `off`."))
            return
        if limit is not None and not MIN_MENTIONS <= limit <= MAX_MENTIONS:
            await ctx.send(embed=error_embed(f"Mention limit must be between {MIN_MENTIONS} and {MAX_MENTIONS}."))
            return
        await _apply_toggle(ctx, "mentionspam", value, mention_limit=limit)

    @automod.command(name="walloftext", help="Toggle Discord AutoMod wall-of-text filter.", usage="automod walloftext <on|off>")
    @commands.has_permissions(manage_guild=True)
    async def walloftext(ctx: commands.Context, switch: str) -> None:
        value = _switch(switch)
        if value is None:
            await ctx.send(embed=error_embed("Use `on` or `off`."))
            return
        await _apply_toggle(ctx, "walloftext", value)

    @automod.command(name="emojispam", help="Toggle Discord AutoMod emoji-spam filter.", usage="automod emojispam <on|off>")
    @commands.has_permissions(manage_guild=True)
    async def emojispam(ctx: commands.Context, switch: str) -> None:
        value = _switch(switch)
        if value is None:
            await ctx.send(embed=error_embed("Use `on` or `off`."))
            return
        await _apply_toggle(ctx, "emojispam", value)
