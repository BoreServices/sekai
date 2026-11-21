"""SFW social commands powered by the PurrBot API (https://purrbot.site/).

Covers the safe-for-work side of the v2 API: every `img/sfw/...` path, the
`list/sfw/...` endpoint, `owoify` and the API info document. NSFW paths live
in their own cog (`src/nsfw`) so the two halves can be enabled or reviewed
separately. Commands are table driven — adding another hug-style action or
character is one row — and `p!help` picks the cog up as its own category.
"""

from dataclasses import dataclass

import discord
from discord.ext import commands

from src.social import client
from src.social.base import (
    Catalog,
    Image,
    register_image,
    run_gallery,
    send_image)
from src.social.client import PurrbotError
from view import error_embed, social_embed


@dataclass(frozen=True, slots=True)
class Action:
    """One PurrBot SFW action: its API path and how its sentence reads."""

    path: str
    help: str
    kind: str = "gif"
    targeted: str | None = None
    solo: str | None = None


ACTIONS: dict[str, Action] = {
    "hug": Action(
        "hug",
        "Hug a member with a random gif.",
        targeted="**{author}** hugs **{target}**!",
        solo="**{author}** hugs themselves!"),
    "pat": Action(
        "pat",
        "Pat a member with a random gif.",
        targeted="**{author}** pats **{target}**!",
        solo="**{author}** pats themselves!"),
    "cuddle": Action(
        "cuddle",
        "Cuddle a member with a random gif.",
        targeted="**{author}** cuddles **{target}**!",
        solo="**{author}** cuddles themselves!"),
    "kiss": Action(
        "kiss",
        "Kiss a member with a random gif.",
        targeted="**{author}** kisses **{target}**!",
        solo="**{author}** blows a kiss!"),
    "slap": Action(
        "slap",
        "Slap a member with a random gif.",
        targeted="**{author}** slaps **{target}**!",
        solo="**{author}** slaps themselves!"),
    "lick": Action(
        "lick",
        "Lick a member with a random gif.",
        targeted="**{author}** licks **{target}**!",
        solo="**{author}** licks themselves!"),
    "poke": Action(
        "poke",
        "Poke a member with a random gif.",
        targeted="**{author}** pokes **{target}**!",
        solo="**{author}** pokes themselves!"),
    "tickle": Action(
        "tickle",
        "Tickle a member with a random gif.",
        targeted="**{author}** tickles **{target}**!",
        solo="**{author}** tickles themselves!"),
    "bite": Action(
        "bite",
        "Bite a member with a random gif.",
        targeted="**{author}** bites **{target}**!",
        solo="**{author}** bites themselves!"),
    "fluff": Action(
        "fluff",
        "Show off your fluff with a random gif.",
        solo="**{author}** is a fluffy ball of fur!"),
    "blush": Action(
        "blush",
        "Blush with a random gif.",
        solo="**{author}** is blushing!"),
    "smile": Action(
        "smile",
        "Smile with a random gif.",
        solo="**{author}** is smiling!"),
    "dance": Action(
        "dance",
        "Dance with a random gif.",
        solo="**{author}** is dancing!"),
    "cry": Action(
        "cry",
        "Cry with a random gif.",
        solo="**{author}** is crying!"),
    "pout": Action(
        "pout",
        "Pout with a random gif.",
        solo="**{author}** is pouting!"),
    "angry": Action(
        "angry",
        "Be angry with a random gif.",
        solo="**{author}** is angry!"),
    "comfy": Action(
        "comfy",
        "Get comfy with a random gif.",
        solo="**{author}** feels comfy!"),
    "lay": Action(
        "lay",
        "Lie down and rest with a random gif.",
        solo="**{author}** is resting!"),
    "tail": Action(
        "tail",
        "Wag your tail with a random gif.",
        solo="**{author}** wags their tail!"),
}

IMAGES: dict[str, Image] = {
    "neko": Image(
        "neko",
        "Neko",
        "🐱",
        "A random neko (cat girl) picture or gif.",
        ("gif", "img")),
    "eevee": Image(
        "eevee",
        "Eevee",
        "🐹",
        "A random Eevee picture or gif.",
        ("gif", "img")),
    "kitsune": Image(
        "kitsune",
        "Kitsune",
        "🦊",
        "A random kitsune (fox girl) picture."),
    "okami": Image(
        "okami",
        "Okami",
        "🐺",
        "A random okami (fox girl) picture."),
    "senko": Image(
        "senko",
        "Senko",
        "🐾",
        "A random Senko picture."),
    "shiro": Image(
        "shiro",
        "Shiro",
        "🐈",
        "A random Shiro picture."),
    "holo": Image(
        "holo",
        "Holo",
        "🐕",
        "A random Holo picture from Spice and Wolf."),
    "background": Image(
        "background",
        "Background",
        "🖼️",
        "A random welcome-card background used by the bot.",
        phrase="welcome background"),
    # `icon` is already an alias of `servericon`, so this one is renamed while
    # still hitting PurrBot's `img/sfw/icon` path.
    "welcomeicon": Image(
        "icon",
        "Icon",
        "🔳",
        "A random welcome-card icon used by the bot.",
        phrase="welcome icon"),
}

# name -> (api path, nsfw, kinds) for every SFW `img/...` path, used by
# p!gallery. The command name and the API path can differ (e.g. `welcomeicon`
# hits `icon`), so both are kept.
SFW_CATALOG: Catalog = {
    name: (action.path, False, (action.kind))
    for name, action in ACTIONS.items()
}
SFW_CATALOG.update(
    {name: (image.path, False, image.kinds) for name, image in IMAGES.items()}
)


def _register_action(bot, name: str, action: Action) -> None:
    @bot.command(
        name=name,
        help=action.help,
        usage=f"{name} [member]" if action.targeted else name)
    @commands.guild_only()
    async def action_command(
        ctx: commands.Context, member: discord.Member | None = None
    ) -> None:
        if member is not None and member.id == ctx.author.id:
            member = None
        if member is not None and action.targeted is None:
            await ctx.send(
                embed=error_embed(
                    f"`{ctx.prefix}{name}` doesn't take a member — "
                    f"just run `{ctx.prefix}{name}`."
                )
            )
            return

        if member is None:
            description = (action.solo or action.targeted).replace(
                "{author}", ctx.author.mention
            )
        else:
            description = action.targeted.replace(
                "{author}", ctx.author.mention
            ).replace("{target}", member.mention)

        await send_image(
            ctx,
            path=action.path,
            kind=action.kind,
            nsfw=False,
            title=f"🙂 {name.title()}",
            description=description)


def setup(bot) -> None:
    for name, action in ACTIONS.items():
        _register_action(bot, name, action)

    for name, image in IMAGES.items():
        register_image(bot, name, image, module=__name__)

    @bot.command(
        name="gallery",
        help="List every SFW image PurrBot has for a path, e.g. `hug` or `neko`.",
        usage="gallery <path> [gif|img]")
    async def gallery(
        ctx: commands.Context,
        name: str | None = None,
        kind: str | None = None) -> None:
        if name is None:
            await ctx.send(
                embed=error_embed(
                    f"Usage: `{ctx.prefix}gallery <path> [gif|img]`"
                )
            )
            return
        await run_gallery(ctx, name=name, kind=kind, catalog=SFW_CATALOG)

    @bot.command(
        name="owoify",
        aliases=["owo"],
        help="OwO-ify text through purrbot.site.",
        usage="owoify <text>")
    async def owoify(ctx: commands.Context, *, text: str | None = None) -> None:
        usage = f"`{ctx.prefix}owoify <text>`"
        if text is None or not text.strip():
            await ctx.send(embed=error_embed(f"Usage: {usage}"))
            return

        text = text.strip()
        if len(text) > client.MAX_TEXT:
            await ctx.send(
                embed=error_embed(
                    f"Keep it under {client.MAX_TEXT} characters."
                )
            )
            return

        async with ctx.typing():
            try:
                result = await client.owoify(text)
            except PurrbotError as exc:
                await ctx.send(embed=error_embed(str(exc)))
                return

        await ctx.send(
            embed=social_embed(
                title="💬 OwOified",
                description=result,
                fields=[("📝 Original", text, False)])
        )

    @bot.command(
        name="purrbot",
        help="Show the PurrBot API version, licence and links.",
        usage="purrbot")
    async def purrbot(ctx: commands.Context) -> None:
        async with ctx.typing():
            try:
                info = await client.fetch_info()
            except PurrbotError as exc:
                await ctx.send(embed=error_embed(str(exc)))
                return

        links = info.get("links") or {}
        license_info = info.get("license") or {}
        fields = [
            ("Version", info.get("version")),
            ("Licence", license_info.get("type")),
            ("Documentation", links.get("documentation")),
            ("Source code", links.get("source")),
            ("API", links.get("api")),
            ("Legal", links.get("legal")),
        ]

        await ctx.send(
            embed=social_embed(
                title="🐾 PurrBot API",
                description=info.get("description"),
                fields=[
                    (name, value, False) for name, value in fields if value
                ],
                footer=client.SOURCE)
        )
