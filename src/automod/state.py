RULE_INVITES = "Sekai: Invites"
RULE_LINKS = "Sekai: Links"
RULE_MENTIONSPAM = "Sekai: Mention spam"
RULE_SPAM = "Sekai: Spam"
RULE_WALLOFTEXT = "Sekai: Wall of text"
RULE_EMOJISPAM = "Sekai: Emoji spam"

FEATURES = ("emojispam", "mentionspam", "spam", "walloftext", "invites", "links")

FEATURE_RULE_NAMES = {
    "invites": RULE_INVITES,
    "links": RULE_LINKS,
    "mentionspam": RULE_MENTIONSPAM,
    "spam": RULE_SPAM,
    "walloftext": RULE_WALLOFTEXT,
    "emojispam": RULE_EMOJISPAM,
}

NAME_TO_FEATURE = {v: k for k, v in FEATURE_RULE_NAMES.items()}

DEFAULT_MENTION_LIMIT = 5
