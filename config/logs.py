# Server logging. Logging is OFF by default in every server: run `logs`
# (alias `p!logs`) in a server to create LOG_CATEGORY_NAME with one private
# channel per log group (`logs-members`, `logs-channels`, ...). Run
# `logs off` to stop logging there again.
#
# Turn individual groups off here; a group with a disabled toggle gets no
# channel. Run `logs` again after changing these to add/repair channels.
#
# LOG_MEMBERS needs the privileged Server Members Intent enabled for the bot
# in the Discord Developer Portal (Bot -> Privileged Gateway Intents).
LOGGING_ENABLED = True
LOG_CATEGORY_NAME = "Logs"
LOG_CHANNEL_PREFIX = "logs"

LOG_MEMBERS = True  # joins, leaves, nicknames, roles, avatars, timeouts, boosts
LOG_MESSAGES = True  # edits, deletes, bulk deletes
LOG_CHANNELS = True  # channel and category create/delete/update + permissions
LOG_ROLES = True  # role create/delete/update
LOG_SERVER = True  # server settings/icon/banner, bans, webhooks
LOG_VOICE = True  # voice join/leave/move/mute/deafen/stream/camera
LOG_INVITES = True  # invite create/delete
LOG_THREADS = True  # thread create/delete/update
LOG_EMOJIS = True  # emoji create/delete/update
LOG_STICKERS = True  # sticker add/remove/rename
LOG_PINS = True  # pinned message changes
LOG_STAGES = True  # stage instance start/update/end
LOG_EVENTS = True  # scheduled event create/update/delete
LOG_AUTOMOD = True  # automod rule triggers
LOG_ANTINUKE = True  # antinuke triggers, punishments and config changes
LOG_COMMANDS = True  # every prefix command run in a server

# Audit log entries (needs View Audit Log): kicks, prunes, bot adds/removes,
# integrations, automod rules, soundboard, and anything else not logged above.
LOG_AUDIT = True

# Status/activity changes. Needs the privileged Presences Intent in the
# Developer Portal and is very noisy, so it is off by default.
LOG_PRESENCE = False
