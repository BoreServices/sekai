import logging
import math

import discord
from discord.ext import commands

from core import economy, shop
from core.duration import parse_duration
from view import (
    error_embed,
    inventory_embed,
    shop_embed,
    success_embed)

log = logging.getLogger("sekai.shop")


def _grantable(ctx: commands.Context, role: discord.Role) -> bool:
    me = ctx.guild.me
    return not (
        role.is_default()
        or role.managed
        or (me is not None and role >= me.top_role)
    )


def _clean(raw: str) -> str:
    return " ".join(raw.split())


async def _listing(ctx: commands.Context, page: int) -> None:
    rows = await shop.items(ctx.bot.db, ctx.guild.id)
    pages = max(1, math.ceil(len(rows) / shop.PAGE_SIZE))
    page = max(page, 1)
    if rows and page > pages:
        await ctx.send(
            embed=error_embed(
                f"The shop only has **{pages}** page{'s' if pages != 1 else ''}."
            )
        )
        return
    chunk = rows[(page - 1) * shop.PAGE_SIZE : page * shop.PAGE_SIZE]
    await ctx.send(
        embed=shop_embed(
            guild_name=ctx.guild.name,
            entries=chunk,
            page=page,
            pages=pages,
            total=len(rows),
            currency=economy.CURRENCY)
    )


def setup(bot) -> None:
    @bot.group(
        name="shop",
        help="Browse the server shop and see what your coins can buy.",
        usage="shop [page]",
        invoke_without_command=True)
    @commands.guild_only()
    async def shop_command(ctx: commands.Context, page: int = 1) -> None:
        await _listing(ctx, page)

    @shop_command.command(
        name="role",
        help="Put a role up for sale.",
        usage="shop role <price> <role> [name]")
    @commands.has_permissions(manage_guild=True)
    async def shop_role(
        ctx: commands.Context,
        price: int,
        role: discord.Role,
        *,
        name: str | None = None) -> None:
        if not 1 <= price <= shop.MAX_PRICE:
            await ctx.send(
                embed=error_embed(f"Price must be between 1 and {shop.MAX_PRICE:,}.")
            )
            return
        if not _grantable(ctx, role):
            await ctx.send(
                embed=error_embed(
                    "I can't hand that role out — pick one that isn't "
                    "@everyone, bot-managed, or above my highest role."
                )
            )
            return
        label = shop.clean_name(name) if name else shop.clean_name(role.name)
        if label is None:
            await ctx.send(
                embed=error_embed(
                    f"Item names stay under {shop.MAX_NAME} characters — "
                    "pass a shorter one: `shop role <price> <role> <name>`."
                )
            )
            return
        if await shop.find_item(bot.db, ctx.guild.id, label) is not None:
            await ctx.send(
                embed=error_embed(f"The shop already sells an item called `{label}`.")
            )
            return

        await shop.create_item(
            bot.db,
            ctx.guild.id,
            name=label,
            kind=shop.KIND_ROLE,
            price=price,
            role_id=role.id)
        await ctx.send(
            embed=success_embed(
                f"{role.mention} is now on sale as `{label}` for "
                f"**{price:,} {economy.CURRENCY}**.",
                icon="🛒")
        )

    @shop_command.command(
        name="boost",
        help="Put a temporary XP multiplier up for sale.",
        usage="shop boost <price> <multiplier> <duration> [name]")
    @commands.has_permissions(manage_guild=True)
    async def shop_boost(
        ctx: commands.Context,
        price: int,
        multiplier: float,
        duration: str,
        *,
        name: str | None = None) -> None:
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send(
                embed=error_embed(
                    "Duration must look like `30m`, `2h` or `1d12h`."
                )
            )
            return
        if not 1 <= price <= shop.MAX_PRICE:
            await ctx.send(
                embed=error_embed(f"Price must be between 1 and {shop.MAX_PRICE:,}.")
            )
            return
        if not 1 < multiplier <= shop.MAX_MULTIPLIER:
            await ctx.send(
                embed=error_embed(
                    f"Multiplier must be above 1 and at most "
                    f"{shop.MAX_MULTIPLIER:g}."
                )
            )
            return
        label = shop.clean_name(name) if name else f"{multiplier:g}x XP boost"
        if label is None or await shop.find_item(bot.db, ctx.guild.id, label):
            await ctx.send(
                embed=error_embed(
                    f"I need a free name under {shop.MAX_NAME} characters for "
                    "that item."
                )
            )
            return

        await shop.create_item(
            bot.db,
            ctx.guild.id,
            name=label,
            kind=shop.KIND_BOOST,
            price=price,
            multiplier=multiplier,
            duration=seconds)
        await ctx.send(
            embed=success_embed(
                f"`{label}` is on sale for **{price:,} {economy.CURRENCY}** — "
                f"**{multiplier:g}x XP** for {duration} once used.",
                icon="🛒")
        )

    @shop_command.command(
        name="remove",
        aliases=["delete"],
        help="Take an item off the shelves for good.",
        usage="shop remove <name>")
    @commands.has_permissions(manage_guild=True)
    async def shop_remove(ctx: commands.Context, *, name: str) -> None:
        label = _clean(name)
        if not await shop.delete_item(bot.db, ctx.guild.id, label):
            await ctx.send(
                embed=error_embed(f"There's no shop item called `{label}`.")
            )
            return
        log.info("Shop item %s removed in %s", label, ctx.guild.id)
        await ctx.send(
            embed=success_embed(
                f"`{label}` is gone — anything members already bought is cleared too."
            )
        )

    @bot.command(
        name="buy",
        help="Buy something from the server shop.",
        usage="buy <name>")
    @commands.guild_only()
    async def buy(ctx: commands.Context, *, name: str) -> None:
        label = _clean(name)
        item = await shop.find_item(bot.db, ctx.guild.id, label)
        if item is None:
            await ctx.send(
                embed=error_embed(
                    f"The shop has nothing called `{label}` — try `{ctx.prefix}shop`."
                )
            )
            return

        role = None
        if item["kind"] == shop.KIND_ROLE:
            role = ctx.guild.get_role(item["role_id"])
            if role is None or not _grantable(ctx, role):
                await ctx.send(
                    embed=error_embed(
                        "That role can't be handed out right now — tell a manager."
                    )
                )
                return
            if role in ctx.author.roles:
                await ctx.send(
                    embed=error_embed(f"You already have {role.mention}.")
                )
                return

        status = await shop.buy(bot.db, ctx.guild.id, ctx.author.id, item)
        if status == shop.BUY_POOR:
            balance = await economy.get_balance(bot.db, ctx.guild.id, ctx.author.id)
            await ctx.send(
                embed=error_embed(
                    f"That costs **{item['price']:,} {economy.CURRENCY}** — you have "
                    f"**{balance:,}**."
                )
            )
            return
        if status == shop.BUY_OWNED:
            await ctx.send(
                embed=error_embed(f"You already own `{discord.utils.escape_markdown(item['name'])}`.")
            )
            return
        if status == shop.BUY_LIMIT:
            await ctx.send(
                embed=error_embed(
                    f"You're holding the maximum of {shop.MAX_QUANTITY} of those."
                )
            )
            return

        if role is not None:
            try:
                await ctx.author.add_roles(role, reason="Shop purchase")
            except discord.HTTPException:
                log.exception("Could not grant shop role in %s", ctx.guild.id)
                await ctx.send(
                    embed=error_embed(
                        "You were charged but I couldn't add the role — "
                        "tell a manager so they can hand it over."
                    )
                )
                return

        balance = await economy.get_balance(bot.db, ctx.guild.id, ctx.author.id)
        bought = discord.utils.escape_markdown(item["name"])
        if role is not None:
            text = (
                f"You bought `{bought}` for **{item['price']:,} "
                f"{economy.CURRENCY}** — {role.mention} is yours."
            )
        else:
            text = (
                f"You bought `{bought}` for **{item['price']:,} "
                f"{economy.CURRENCY}** — use it with `{ctx.prefix}use {bought}`."
            )
        await ctx.send(
            embed=success_embed(f"{text}\nBalance: **{balance:,}**.", icon="🛒")
        )

    @bot.command(
        name="inventory",
        aliases=["bag", "items"],
        help="Show what you own from the shop.",
        usage="inventory [member]")
    @commands.guild_only()
    async def inventory(
        ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        target = member or ctx.author
        rows = await shop.owned_rows(bot.db, ctx.guild.id, target.id)
        await ctx.send(
            embed=inventory_embed(display_name=target.display_name, entries=rows)
        )

    @bot.command(
        name="use",
        help="Activate an item you bought, like an XP boost.",
        usage="use <name>")
    @commands.guild_only()
    async def use_item(ctx: commands.Context, *, name: str) -> None:
        label = _clean(name)
        item = await shop.find_item(bot.db, ctx.guild.id, label)
        if item is None:
            await ctx.send(
                embed=error_embed(f"The shop has nothing called `{label}`.")
            )
            return

        status, expires_at = await shop.activate(
            bot.db, ctx.guild.id, ctx.author.id, item
        )
        if status == shop.USE_ROLE:
            await ctx.send(
                embed=error_embed(
                    "That's a role — it's added the moment you buy it."
                )
            )
            return
        if status == shop.USE_NONE:
            await ctx.send(
                embed=error_embed(
                    f"You don't have `{discord.utils.escape_markdown(item['name'])}` "
                    "to use."
                )
            )
            return

        await ctx.send(
            embed=success_embed(
                f"**{item['multiplier']:g}x XP** is now active until "
                f"<t:{expires_at}:R>.",
                icon="✨")
        )
