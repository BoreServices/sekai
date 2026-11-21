import aiohttp
from dataclasses import dataclass

@dataclass(frozen=True)
class D1Config:
    account_id: str = ""
    database_id: str = ""
    api_token: str = ""

    @property
    def query_url(self) -> str:
        return (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/d1/database/{self.database_id}/query"
        )

d1_config = D1Config()
