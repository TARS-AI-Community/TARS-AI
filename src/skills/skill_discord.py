"""Skill: discord — Discord bot integration.

Purely conversational — just DM the bot and it responds via the LLM.
Everything goes through the same pipeline as voice/webui.

Features:
- DM chat with LLM processing
- Image attachment processing (multimodal LLM)
- Follow-up replies (web search results, camera analysis, etc.)
- Allowed user filter (only respond to configured user)
"""

import os
import re
import asyncio
import base64
import logging

logging.getLogger('discord.client').setLevel(logging.ERROR)

import discord
from discord.ext import commands

from modules.module_messageQue import queue_message

# ── Skill metadata (for webui config panel) ──────────────────────────────────

SKILL = {
    "name": "discord",
    "description": "Run TARS as a Discord bot — DM it to chat",
    "config": {
        "allowed_user": {
            "type": "text",
            "default": "",
            "description": "Discord username to respond to (e.g. 'pyrater'). Leave empty to respond to all DMs.",
        },
    },
    "prompt": "",
    "examples": [],
}


def execute(parameters, context):
    """Discord is a background service — not called by the LLM."""
    return None


# ── Bot setup ────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


def _process_message(user_message, image_b64=None):
    """Process a Discord message through the LLM pipeline."""
    try:
        from modules.module_llm import process_completion
        return process_completion(user_message, image_b64=image_b64)
    except Exception as e:
        queue_message(f"ERROR: Discord LLM processing: {e}")
        return "Sorry, I encountered an error processing your message."


def _send_discord(text, route, image_path=None):
    """Delivery function registered with the router."""
    channel_id = route.get("discord_channel_id")
    user_id = route.get("discord_user_id")
    if not channel_id and not user_id:
        return

    async def _do_send():
        channel = bot.get_channel(int(channel_id)) if channel_id else None
        if not channel and user_id:
            try:
                user = await bot.fetch_user(int(user_id))
                channel = await user.create_dm()
            except Exception as e:
                queue_message(f"ROUTER: Could not open DM for user {user_id}: {e}")
                return
        if not channel:
            queue_message(f"ROUTER: Discord channel {channel_id} not found")
            return

        if image_path:
            import discord as _discord
            await channel.send(text or "", file=_discord.File(image_path))
        elif text:
            await channel.send(text)

    try:
        if bot.loop and bot.loop.is_running():
            asyncio.run_coroutine_threadsafe(_do_send(), bot.loop)
        else:
            asyncio.run(_do_send())
    except Exception as e:
        queue_message(f"ROUTER: Discord send failed: {e}")


def start():
    """Start the Discord bot and register with the router."""
    bot_token = os.getenv('DISCORD_TOKEN', '')
    if not bot_token:
        queue_message("ERROR: DISCORD_TOKEN not set in .env")
        return

    # Register as a router target so send()/send_image() can deliver to Discord
    from modules.module_router import register_target
    register_target("discord", _send_discord)

    import threading
    threading.Thread(target=bot.run, args=(bot_token,), daemon=True).start()
    queue_message("INFO: Discord bot started in a separate thread.")


# ── Utilities ────────────────────────────────────────────────────────────────

async def _extract_image_b64(message):
    """Extract the first image attachment as a base64 string."""
    for attachment in message.attachments:
        if any(attachment.filename.lower().endswith(ext)
               for ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            try:
                return base64.b64encode(await attachment.read()).decode('utf-8')
            except Exception as e:
                queue_message(f"ERROR: Failed to read image attachment: {e}")
    return None


async def _send_long_message(channel, text, max_len=2000):
    """Send a message, splitting at newlines/spaces if it exceeds Discord's limit."""
    while len(text) > max_len:
        split_at = text.rfind('\n', 0, max_len)
        if split_at == -1:
            split_at = text.rfind(' ', 0, max_len)
        if split_at == -1:
            split_at = max_len
        await channel.send(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        await channel.send(text)


def _run_side_effects_sync(reply, user_message):
    """Run LLM side effects synchronously so follow-up replies get sent back."""
    if not isinstance(reply, dict):
        return
    fc = reply.get("function_calls", [])
    nm = reply.get("new_memories", [])
    ca = reply.get("current_activity")
    if fc or nm or ca:
        try:
            from modules.module_llm import llm_execute_side_effects
            llm_execute_side_effects(reply, user_message, source="discord")
        except Exception as e:
            queue_message(f"ERROR: Discord side effects failed: {e}")


# ── Events ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    queue_message(f"INFO: Discord bot logged in as {bot.user}")


@bot.event
async def on_message(message):
    """Handle incoming DMs — process through LLM like voice/webui."""
    if message.author == bot.user:
        return

    # Only respond to DMs
    if not isinstance(message.channel, discord.DMChannel):
        return

    # Filter by allowed user (if configured in skill settings)
    try:
        from modules.module_skills import get_skill_manager
        _sm = get_skill_manager()
        if _sm:
            _dc = _sm.get_skill_config("discord")
            _allowed = _dc.get("allowed_user", "").strip()
            if _allowed and message.author.name.lower() != _allowed.lower():
                return
    except Exception:
        pass

    user_message = re.sub(r'<@!?\d+>\s*', '', message.content).strip()
    if not user_message and not message.attachments:
        return

    # Track that user is talking via Discord
    from modules.module_router import set_active_route
    set_active_route("discord",
        discord_channel_id=message.channel.id,
        discord_user_id=str(message.author.id),
    )

    queue_message(f"DM: {message.author.name}: {message.content}")

    # Image attachment
    image_b64 = await _extract_image_b64(message)
    if image_b64:
        queue_message(f"DISCORD: Image attachment from {message.author.name}")

    # Process with typing indicator
    async with message.channel.typing():
        try:
            reply = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _process_message(user_message, image_b64)
            )
        except Exception as e:
            queue_message(f"ERROR: Discord processing failed: {e}")
            reply = "Sorry, I encountered an error processing your message."

    reply_text = reply.get('reply', '') if isinstance(reply, dict) else (str(reply) if reply else '')
    if not reply_text:
        return

    reply_text = re.sub(r'<think>.*?</think>', '', reply_text, flags=re.DOTALL).strip()

    await _send_long_message(message.channel, reply_text)
    queue_message(f"DISCORD: Replied to {message.author.name}")

    # Run side effects inline so follow-up replies (web search, camera, etc.) get sent back
    if isinstance(reply, dict):
        initial_reply = reply.get('reply', '')
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: _run_side_effects_sync(reply, user_message)
        )
        updated_reply = reply.get('reply', '')
        if updated_reply and updated_reply != initial_reply:
            followup_text = re.sub(r'<think>.*?</think>', '', updated_reply, flags=re.DOTALL).strip()
            if followup_text:
                await _send_long_message(message.channel, followup_text)


# ── Auto-start on import (if enabled + token set) ───────────────────────────
try:
    import configparser as _cp
    _c = _cp.ConfigParser()
    _c.read(os.path.join(os.path.dirname(__file__), '..', 'config.ini'))
    _disabled = _c.get('SKILL:discord', 'disabled', fallback='false').lower() in ('true', '1', 'yes')
    if not _disabled and os.getenv('DISCORD_TOKEN'):
        start()
except Exception:
    pass
