# Discord user IDs allowed to use owner-only commands (p!nodelinkswitch).
# The bot's application owner (the Discord account that created the bot) is always allowed.
OWNER_IDS: list[int] = [
    1513282313092595822,
    1566633799788269598,
    1467913714484121725,
    1546968812522311703,
]

# Users with control over EVERY server. They bypass the per-server permission
# checks on bot commands (so they can run admin commands in any server without
# the Discord "Manage Server" permission) and can manage every server from the
# web dashboard, regardless of their role in that server.
GLOBAL_ADMIN_IDS: list[int] = [
    1546968812522311703,
]

# Accounts that can manage EVERY server from the web dashboard. Everyone else
# who signs in only sees the servers they own or administer (Administrator or
# Manage Server). Owners are always included.
DASHBOARD_CONTROL_ALL_IDS: list[int] = list(
    dict.fromkeys([*OWNER_IDS, *GLOBAL_ADMIN_IDS, 1546968812522311700]))

# Backwards-compatible alias for the old "dashboard admin" name.
DASHBOARD_ADMIN_IDS = DASHBOARD_CONTROL_ALL_IDS

# DM'd when a command hits an unexpected error.
ERROR_REPORT_USER_ID = 1546968812522311703
