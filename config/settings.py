from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    bot_name: str
    owner_name: str
    default_prefix: str
    dev_prefix: str
    embed_color: int
    footer_emoji: str
    web_host: str
    web_port: int
    dev_web_port: int
    status_port: int
    dev_status_port: int
    status_url: str
    transcript_port: int
    dev_transcript_port: int
    verify_port: int
    dev_verify_port: int
    dashboard_port: int
    dev_dashboard_port: int
    dashboard_url: str
    dashboard_redirect_uri: str
    website_url: str
    verify_base_url: str
    verify_redirect_uri: str
    transcript_url: str
    invite_url: str
    emoji_dir: Path


settings = Settings(
    bot_name="Sekai",
    owner_name="PhaseWorld",
    default_prefix=".",
    dev_prefix="pd!",
    embed_color=0x9B59B6,
    footer_emoji="crown",
    web_host="127.0.0.1",
    web_port=8080,
    dev_web_port=9080,
    status_port=8081,
    dev_status_port=9081,
    status_url="https://status.phaseworld.top",
    transcript_port=8083,
    dev_transcript_port=9083,
    verify_port=8084,
    dev_verify_port=9084,
    dashboard_port=8085,
    dev_dashboard_port=9085,
    dashboard_url="https://dash.phaseworld.top",
    dashboard_redirect_uri="https://dash.phaseworld.top/auth/callback",
    website_url="https://bot.phaseworld.top",
    verify_base_url="https://verify.phaseworld.top",
    verify_redirect_uri="https://verify.phaseworld.top/auth/callback",
    transcript_url="https://tickets.phaseworld.top",
    invite_url="https://discord.gg/hkzyYFyzCE",
    emoji_dir=BASE_DIR / "emoji")
