"""Skill: discord — Discord bot integration (background service).

This skill provides the config UI for the Discord bot. The bot runs as a
background thread (not called by the LLM), so execute() is a no-op.
Enable/disable and settings are managed through the Skills config panel.

Features:
- Text chat: responds to mentions, DMs, and replies
- Image attachment processing (multimodal LLM)
- Voice channel support: !join, !leave, !say, !ask
- Reminders: !remind, !timers, !cancel
- Command prefix: ! (e.g., !help, !join, !remind)
"""

import os

SKILL = {
    "name": "discord",
    "description": "Run TARS as a Discord bot in a server channel",
    "config": {
        "channel_id": {
            "type": "text",
            "default": "",
            "description": "Discord channel ID (right-click channel > Copy Channel ID in Developer Mode)",
        },
        "command_prefix": {
            "type": "text",
            "default": "!",
            "description": "Command prefix for bot commands (default: !)",
        },
    },
    "prompt": "",
    "examples": [],
}


def execute(parameters, context):
    """Discord is a background service — not called by the LLM."""
    return None
