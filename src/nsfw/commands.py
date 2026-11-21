"""NSFW commands powered by the PurrBot API (https://purrbot.site/).

The age-restricted half of the v2 API lives here, apart from the safe-for-work
commands in `src/social`, so the two can be enabled or reviewed separately.
Every path is served only inside an age-restricted channel — see
`base.is_nsfw_channel`. Commands are table driven and `p!help` picks the cog up
as its own category.
"""

from discord.ext import commands

from src.social.base import Catalog, Image, register_image, run_gallery
from view import error_embed

# name -> (label, help, targeted sentence) for the gif-only NSFW paths. The
# targeted sentence is used when a member is mentioned, e.g. `p!fuck @user`.
NSFW_GIFS: dict[str, tuple[str, str, str]] = {
    "anal": (
        "Anal",
        "A random anal gif.",
        "**{author}** had anal with **{target}**!"),
    "blowjob": (
        "Blowjob",
        "A random blowjob gif.",
        "**{author}** gave **{target}** a blowjob!"),
    "cum": (
        "Cum",
        "A random cum gif.",
        "**{author}** came on **{target}**!"),
    "fuck": (
        "Fuck",
        "A random fuck gif.",
        "**{author}** fucked **{target}**!"),
    "pussylick": (
        "Pussylick",
        "A random pussylick gif.",
        "**{author}** licked **{target}**!"),
    "solo": (
        "Solo",
        "A random solo masturbation gif.",
        "**{author}** watched **{target}** masturbate!"),
    "solo_male": (
        "Solo (Male)",
        "A random solo masturbation gif of a man.",
        "**{author}** watched **{target}** masturbate!"),
    "threesome_fff": (
        "Threesome (FFF)",
        "A random threesome gif, females only.",
        "**{author}** had a threesome with **{target}**!"),
    "threesome_ffm": (
        "Threesome (FFM)",
        "A random threesome gif, two females and one male.",
        "**{author}** had a threesome with **{target}**!"),
    "threesome_mmf": (
        "Threesome (MMF)",
        "A random threesome gif, two males and one female.",
        "**{author}** had a threesome with **{target}**!"),
    "yaoi": (
        "Yaoi",
        "A random yaoi (gay) gif.",
        "**{author}** shared yaoi with **{target}**!"),
    "yuri": (
        "Yuri",
        "A random yuri (lesbian) gif.",
        "**{author}** shared yuri with **{target}**!"),
}

NSFW_IMAGES: dict[str, Image] = {
    "nsfwneko": Image(
        "neko",
        "NSFW Neko",
        "🔞",
        "A random NSFW neko picture or gif. NSFW channels only.",
        ("gif", "img"),
        phrase="nsfw neko",
        nsfw=True,
        targeted="**{author}** showed **{target}** an NSFW neko!"),
    **{
        name: Image(
            name,
            label,
            "🔞",
            f"{help} NSFW channels only.",
            ("gif"),
            phrase=f"{label.lower()} gif",
            nsfw=True,
            targeted=targeted)
        for name, (label, help, targeted) in NSFW_GIFS.items()
    },
}

# name -> (api path, nsfw, kinds) for every NSFW `img/...` path, used by
# p!nsfwgallery.
NSFW_CATALOG: Catalog = {
    name: (image.path, image.nsfw, image.kinds)
    for name, image in NSFW_IMAGES.items()
}


def setup(bot) -> None:
    for name, image in NSFW_IMAGES.items():
        register_image(bot, name, image, module=__name__)

    @bot.command(
        name="nsfwgallery",
        help="List every NSFW image for a path, e.g. `anal`.",
        usage="nsfwgallery <path> [gif|img]")
    async def nsfwgallery(
        ctx: commands.Context,
        name: str | None = None,
        kind: str | None = None) -> None:
        if name is None:
            await ctx.send(
                embed=error_embed(
                    f"Usage: `{ctx.prefix}nsfwgallery <path> [gif|img]`"
                )
            )
            return
        await run_gallery(ctx, name=name, kind=kind, catalog=NSFW_CATALOG)
