import discord
from discord.ext import tasks

from config.settings import settings

# Rotates through these, one every INTERVAL_SECONDS.
# Placeholders: {guilds}, {members}, {prefix}.
STATUSES: list[tuple[discord.ActivityType, str]] = [
    (discord.ActivityType.watching, "👥 {guilds} servers • {members} members"),
    (discord.ActivityType.playing, settings.invite_url.removeprefix("https://")),
    (discord.ActivityType.watching, "🌐 " + settings.website_url),
    (discord.ActivityType.playing, "💜 PhaseWorld"),
]

INTERVAL_SECONDS = 30


def status_activity(bot, index: int) -> discord.Activity:
    activity_type, text = STATUSES[index % len(STATUSES)]
    guilds = len(bot.guilds)
    members = sum(guild.member_count or 0 for guild in bot.guilds)
    return discord.Activity(
        type=activity_type,
        name=text.format(
            guilds=f"{guilds:,}",
            members=f"{members:,}",
            prefix=settings.default_prefix))


def start_presence_loop(bot) -> tasks.Loop:
    @tasks.loop(seconds=INTERVAL_SECONDS)
    async def cycle() -> None:
        await bot.change_presence(activity=status_activity(bot, cycle.current_loop))

    cycle.before_loop(bot.wait_until_ready)
    cycle.start()
    return cycle
