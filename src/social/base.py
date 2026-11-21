"""Shared plumbing for the PurrBot media cogs (`social` and `nsfw`).

Both cogs serve images from the same API and render the same embeds, so the
picture dataclass, the NSFW-channel check, the send/register helpers and the
gallery runner live here and are imported by each cog.
"""

from dataclasses import dataclass

import discord
from discord.ext import commands

from src.social import client
from src.social.client import PurrbotError
from view import error_embed, social_embed

GALLERY_LIMIT = 15

# name -> (api path, nsfw, kinds) — built by each cog for its own paths.
Catalog = dict[str, tuple[str, bool, tuple[str, ...]]]


@dataclass(frozen=True, slots=True)
class Image:
    """One standalone PurrBot picture (character, welcome card, NSFW, ...)."""

    path: str
    label: str
    emoji: str
    help: str
    kinds: tuple[str, ...] = ("img")
    phrase: str | None = None
    nsfw: bool = False
    # Sentence used when a member is targeted, e.g. `p!fuck @user`. Both
    # placeholders are mentions.
    targeted: str | None = None


def is_nsfw_channel(ctx: commands.Context) -> bool:
    channel = ctx.channel
    if isinstance(channel, discord.Thread):
        channel = channel.parent
    return bool(getattr(channel, "nsfw", False))


async def send_image(
    ctx: commands.Context,
    *,
    path: str,
    kind: str,
    nsfw: bool,
    title: str,
    description: str) -> None:
    async with ctx.typing():
        try:
            image_url = await client.fetch_image(path, kind, nsfw=nsfw)
        except PurrbotError as exc:
            await ctx.send(embed=error_embed(str(exc)))
            return

    await ctx.send(
        embed=social_embed(
            title=title, description=description, image_url=image_url
        )
    )


def register_image(bot, name: str, image: Image, *, module: str) -> None:
    options = []
    if image.targeted:
        options.append("[@member]")
    if len(image.kinds) > 1:
        options.append(f"[{'|'.join(image.kinds)}]")
    usage = f"{name} {' '.join(options)}".strip()

    @bot.command(name=name, help=image.help, usage=usage)
    async def image_command(
        ctx: commands.Context, *, query: str | None = None
    ) -> None:
        if image.nsfw and not is_nsfw_channel(ctx):
            await ctx.send(
                embed=error_embed(
                    f"`{ctx.prefix}{name}` is NSFW — use it in an "
                    "age-restricted channel."
                )
            )
            return

        # Arguments are parsed instead of typed so `p!nsfwneko img` and
        # `p!fuck @user` both work — and in either order.
        choices = image.kinds
        media = None
        member = None
        for token in (query or "").split():
            lowered = token.lower()
            if lowered in choices and media is None:
                media = lowered
                continue
            try:
                member = await commands.MemberConverter().convert(ctx, token)
            except commands.BadArgument:
                await ctx.send(
                    embed=error_embed(
                        f"`{ctx.prefix}{name}` doesn't understand `{token}` — "
                        "pass a member or "
                        f"{' or '.join(f'`{choice}`' for choice in choices)}."
                    )
                )
                return
        media = media or choices[0]

        if member is not None and image.targeted:
            description = image.targeted.format(
                author=ctx.author.mention, target=member.mention
            )
        else:
            description = (
                f"**{ctx.author.mention}** got a random "
                f"{image.phrase or image.label.lower()}!"
            )

        await send_image(
            ctx,
            path=image.path,
            kind=media,
            nsfw=image.nsfw,
            title=f"{image.emoji} {image.label}",
            description=description)

    # `p!help` groups commands by their callback's module, but this factory is
    # shared by the SFW and NSFW cogs, so tag the command with its own cog.
    image_command.callback.__module__ = module


async def run_gallery(
    ctx: commands.Context,
    *,
    name: str,
    kind: str | None,
    catalog: Catalog) -> None:
    """List every image PurrBot has for a path, using the given catalog."""

    entry = catalog.get(name.lower())
    if entry is None:
        # The catalog is keyed by command name, but the usage is `<path>`, and
        # some names differ from their API path (`nsfwneko` -> `neko`,
        # `welcomeicon` -> `icon`). Accept either spelling.
        entry = next(
            (
                candidate
                for candidate in catalog.values()
                if candidate[0].lower() == name.lower()
            ),
            None)
    if entry is None:
        await ctx.send(
            embed=error_embed(
                f"Unknown path `{name}` — try one from `{ctx.prefix}help`."
            )
        )
        return

    path, nsfw, choices = entry
    if nsfw and not is_nsfw_channel(ctx):
        await ctx.send(
            embed=error_embed(
                f"`{name}` is NSFW — use it in an age-restricted channel."
            )
        )
        return

    media = kind.lower() if kind else choices[0]
    if media not in choices:
        await ctx.send(
            embed=error_embed(
                f"`{name}` only serves "
                f"{' or '.join(f'`{choice}`' for choice in choices)}."
            )
        )
        return

    async with ctx.typing():
        try:
            links = await client.fetch_list(path, media, nsfw=nsfw)
        except PurrbotError as exc:
            await ctx.send(embed=error_embed(str(exc)))
            return

    shown = links[:GALLERY_LIMIT]
    listing = "\n".join(
        f"{index}. [image {index}]({link})"
        for index, link in enumerate(shown, start=1)
    )
    if len(links) > len(shown):
        listing += f"\n… and **{len(links) - len(shown)}** more."

    await ctx.send(
        embed=social_embed(
            title=f"🖼️ {name.title()} gallery",
            description=listing,
            footer=f"{len(links)} {media} images from {client.SOURCE}")
    )
