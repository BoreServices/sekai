from dataclasses import dataclass


@dataclass(frozen=True)
class NodeLinkServer:
    name: str
    url: str
    password: str
    username: str = ""
    ssl: bool = False

    @property
    def resolved_url(self) -> str:
        url = self.url.strip().rstrip("/")
        if "://" not in url:
            url = "http://" + url
        _, rest = url.split("://", 1)
        return f"{'https' if self.ssl else 'http'}://{rest}"


# Curated public Lavalink/NodeLink v4 servers. Wavelink connects to all of them
# and assigns each player to the least-loaded connected node; the health loop
# reconnects dropped nodes. The German nodes keep latency low for France.
NODELINKS: list[NodeLinkServer] = [
    #NodeLinkServer(
    #    name="breed",
    #    url="https://music.breed.rip/",
    #    password="0000", # fake pw :(
    #    ssl=True),
    NodeLinkServer(
        name="serenetia",
        url="lavalinkv4.serenetia.com",
        password="https://seretia.link/discord",
        ssl=True),
    NodeLinkServer(
        name="serenetia-http",
        url="lavalinkv4.serenetia.com:80",
        password="https://seretia.link/discord",
        ssl=False),
    NodeLinkServer(
        name="vinster",
        url="freelavalinkvinster.in",
        password="youshallnotpass",
        ssl=True),
    NodeLinkServer(
        name="vinster-http",
        url="freelavalinkvinster.in:9018",
        password="youshallnotpass",
        ssl=False),
    NodeLinkServer(
        name="ajie",
        url="lava-v4.ajieblogs.eu.org",
        password="https://dsc.gg/ajidevserver",
        ssl=True),
    NodeLinkServer(
        name="ajie-http",
        url="lava-v4.ajieblogs.eu.org:80",
        password="https://dsc.gg/ajidevserver",
        ssl=False),
    NodeLinkServer(
        name="jirayu",
        url="lavalink.jirayu.net",
        password="youshallnotpass",
        ssl=True),
    NodeLinkServer(
        name="jirayu-direct",
        url="lavalink.jirayu.net:13592",
        password="youshallnotpass",
        ssl=False),
    NodeLinkServer(
        name="millohost",
        url="lava-v4.millohost.my.id",
        password="https://discord.gg/mjS5J2K3ep",
        ssl=True),
    NodeLinkServer(
        name="nazha",
        url="lavalink.nazha.online",
        password="nazhafreelava",
        ssl=True),
    NodeLinkServer(
        name="kasawa",
        url="lava2.kasawa.pro:2334",
        password="youshallnotpass",
        ssl=False),
]
