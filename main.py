import argparse
import socket

import aiohttp
import discord_phone
from config.token import DEV_DISCORD_TOKEN, DISCORD_TOKEN
from core import processes
from core.bot import SekaiBot
from core.logger import setup_logging

GATEWAY_HOST = "gateway.discord.gg"

NETWORK_HELP = (
    "The bot couldn't reach Discord: the DNS lookup for {host} failed.\n"
    "That's a network problem on this machine, not a bug in the bot. Try:\n"
    "  - check the internet connection (can you open https://discord.com?)\n"
    "  - turn off any VPN, proxy, ad-blocker or DNS filter\n"
    "  - run `nslookup {host}` — it should return an IP address\n"
    "  - run `ipconfig /flushdns`, or switch DNS to 1.1.1.1 / 8.8.8.8\n"
    "  - check that a hosts-file entry isn't blocking discord.gg"
)


def _exception_chain(error: BaseException):
    """The error plus everything it was raised from/handling."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _is_network_error(error: BaseException) -> bool:
    """True when Discord was unreachable (DNS, refused connection, …).

    discord.py re-raises an AttributeError of its own when the first gateway
    connection fails (`self.ws` is still None), so the real cause only shows up
    in the exception chain.
    """
    markers = (socket.gaierror, aiohttp.ClientConnectorError)
    return any(isinstance(item, markers) for item in _exception_chain(error))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Purpurite bot.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dev", action="store_true", help="use the dev token from config/token.py"
    )
    mode.add_argument(
        "--main", action="store_true", help="use the production token (default)"
    )
    debug = parser.add_mutually_exclusive_group()
    debug.add_argument(
        "--debug",
        action="store_true",
        help="show debug logs, including aiohttp access and NodeLink output")
    debug.add_argument(
        "--nodebug", action="store_true", help="leave debug logs off (default)"
    )
    return parser.parse_args()


class SyncedSekaiBot(SekaiBot):
    """Subclass or wrapper to clear out old ghost slash commands on startup."""
    async def setup_hook(self) -> None:
        # Run any original setup hooks from SekaiBot if they exist
        if hasattr(super(), "setup_hook"):
            await super().setup_hook()
        
        # Clear global command tree and sync it to wipe ghost commands
        self.tree.clear_commands(guild=None)
        synced = await self.tree.sync()
        print(f"[Slash Sync] Cleared and synced tree. Active slash commands: {len(synced)}")


def main() -> None:
    args = parse_args()
    setup_logging(debug=args.debug)
    processes.install()

    token = DEV_DISCORD_TOKEN if args.dev else DISCORD_TOKEN
    if token.startswith("YOUR_"):
        raise RuntimeError("Set your bot token in config/token.py before running.")

    # Use our synced bot class to wipe the ghost commands on boot
    bot = SyncedSekaiBot(dev=args.dev)
    try:
        bot.run(token, log_handler=None)
    except Exception as error:
        if not _is_network_error(error):
            raise
        print("\n" + NETWORK_HELP.format(host=GATEWAY_HOST) + "\n")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()