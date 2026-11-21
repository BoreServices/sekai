import discord

from core.emojis import emoji_partial
from view.base import base_embed, brand
from view.error import error_embed
from view.success import success_embed


def giveaway_embed(
    *,
    prize: str,
    host: discord.abc.User | None,
    winners: int,
    ends_at: int,
    ended: bool = False,
    winner_ids: list[int] | None = None) -> discord.Embed:
    embed = base_embed(
        title=f"🎉 {prize}",
        description=(
            "This giveaway has ended."
            if ended
            else "Click **Enter** below for a chance to win. "
            "Click it again to leave."
        ))
    embed.add_field(
        name="Host",
        value=host.mention if host is not None else "—",
        inline=True)
    embed.add_field(name="Winners", value=str(winners), inline=True)
    embed.add_field(
        name="Ends",
        value="Ended" if ended else f"<t:{ends_at}:R>",
        inline=True)
    if ended:
        won_by = ", ".join(f"<@{user_id}>" for user_id in winner_ids or [])
        embed.add_field(
            name="Won by", value=won_by or "No valid entries", inline=False
        )
    return brand(embed)


class GiveawayView(discord.ui.View):
    def __init__(self, bot, giveaway_id: str) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.giveaway_id = giveaway_id
        button = discord.ui.Button(
            label="Enter",
            style=discord.ButtonStyle.primary,
            custom_id=f"giveaway:enter:{giveaway_id}",
            emoji=emoji_partial("confetti") or "🎉")
        button.callback = self.enter
        self.add_item(button)

    async def enter(self, interaction: discord.Interaction) -> None:
        from src.giveaways import state

        if interaction.guild is None:
            await interaction.response.send_message(
                embed=error_embed("Giveaways only work in a server."),
                ephemeral=True)
            return
        if not state._loaded:
            await state.load_state(self.bot)
        entered = await state.toggle_entry(
            self.bot, self.giveaway_id, interaction.user.id
        )
        if entered is None:
            await interaction.response.send_message(
                embed=error_embed("This giveaway has already ended."),
                ephemeral=True)
        elif entered:
            await interaction.response.send_message(
                embed=success_embed("You're in! Good luck.", icon="🎉"),
                ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=success_embed("You left the giveaway.", icon="👋"),
                ephemeral=True)
