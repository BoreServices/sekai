import re

DURATION = re.compile(r"(\d+)([smhdw])")
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> int | None:
    """Parse '30s', '10m', '2h', '1d30m' or '1w' into seconds."""
    value = text.strip().lower()
    if not value:
        return None
    total = 0
    position = 0
    for match in DURATION.finditer(value):
        if match.start() != position:
            return None
        total += int(match.group(1)) * UNITS[match.group(2)]
        position = match.end()
    if position != len(value) or total <= 0:
        return None
    return total
