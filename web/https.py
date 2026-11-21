from urllib.parse import urlparse

from aiohttp import web


def site_domain(public_url: str) -> str:
    """The domain whose subdomains all belong to the same public site.

    ``https://bot.phaseworld.top`` -> ``phaseworld.top``, so the landing page,
    the dashboard, transcripts, verification and deeper hostnames such as
    ``new.tickets.phaseworld.top`` or ``a.b.phaseworld.top`` are all covered.
    """
    parsed = urlparse(public_url.strip())
    host = (parsed.netloc or parsed.path).lower()
    host = host.split(":", 1)[0].strip(".")
    labels = host.split(".")
    # Drop the left-most label only when a registrable domain is left behind
    # (``bot.phaseworld.top`` -> ``phaseworld.top``, but an apex stays put).
    return ".".join(labels[1:]) if len(labels) > 2 else host


def enforce_https(public_url: str):
    """Send plain-HTTP visitors to HTTPS and add HSTS once they are on it.

    The Cloudflare tunnel terminates TLS and reports the visitor's scheme in
    X-Forwarded-Proto, so local loopback requests (no header) are untouched.
    Every hostname in the zone matches, at any subdomain depth, so a tunnel
    route like ``status.dev.phaseworld.top`` is treated exactly like
    ``phaseworld.top``.
    """
    domain = site_domain(public_url)

    @web.middleware
    async def middleware(request: web.Request, handler):
        host = request.host.lower().split(":", 1)[0].strip(".")
        if not domain or not (host == domain or host.endswith("." + domain)):
            return await handler(request)
        proto = request.headers.get("X-Forwarded-Proto", "").lower()
        if proto == "http":
            url = str(request.url).replace("http://", "https://", 1)
            raise web.HTTPPermanentRedirect(url)
        response = await handler(request)
        if proto == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000"
            )
        return response

    return middleware
