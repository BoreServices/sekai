import discord

from view.error import error_embed


class AutomodPanelView(discord.ui.View):
    def __init__(self, bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot


async def post_automod_panel(bot, guild: discord.Guild, channel: discord.TextChannel) -> discord.Message:
    raise RuntimeError(
        "Automod now uses Discord AutoMod. Manage it with `automod` commands or Server Settings > AutoMod."
    )
