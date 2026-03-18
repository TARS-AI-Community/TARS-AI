"""
module_discord.py

Discord Integration Module for TARS-AI Application.

All Discord functionality lives here — no separate cogs directory needed.
Features:
- commands.Bot with ! prefix
- Text chat: mentions, DMs, replies
- Image attachment processing (multimodal LLM)
- Voice: !join, !leave, !say, !ask
- Reminders: !remind, !timers, !cancel
- !help command
"""

# === Standard Libraries ===
import os
import re
import asyncio
import logging
import base64
import tempfile
import io
import threading
from datetime import datetime, timedelta

import discord
from discord.ext import commands

# === Custom Modules ===
from modules.module_messageQue import queue_message

# === Constants and Globals ===
process_discord_message_callback = None

# Optional voice-recv for listening (speak-only works without it)
_VOICE_RECV_AVAILABLE = False
try:
    import discord.ext.voice_recv as voice_recv
    _VOICE_RECV_AVAILABLE = True
except ImportError:
    pass

# === Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ═══════════════════════════════════════════════════════════════════════════════
# Startup
# ═══════════════════════════════════════════════════════════════════════════════

def start_discord_bot(callback):
    """Start the Discord bot with a message-processing callback.

    Parameters:
        callback: function(user_message: str, image_b64: str|None) -> str|dict
    """
    global process_discord_message_callback
    process_discord_message_callback = callback

    bot_token = os.getenv('DISCORD_TOKEN', '')
    if not bot_token:
        queue_message("ERROR: DISCORD_TOKEN not set in .env")
        return
    bot.run(bot_token)


# ═══════════════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════════════

async def replace_mentions_with_usernames(content):
    """Replace all <@ID> mentions in content with @username."""
    words = content.split()
    for i, word in enumerate(words):
        if word.startswith("<@") and word.endswith(">"):
            username = await _mention_to_username(word)
            if username:
                words[i] = f"@{username}"
    return " ".join(words)


async def _mention_to_username(mention):
    if mention.startswith("<@") and mention.endswith(">"):
        user_id = mention.strip("<@!>")
        try:
            user = await bot.fetch_user(int(user_id))
            return user.name if user else None
        except (ValueError, discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
    return None


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


def _strip_bot_mention(content):
    """Remove bot mentions from message content."""
    return re.sub(r'<@!?\d+>\s*', '', content).strip()


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


async def _speak_in_voice(text, voice_client):
    """Synthesize text via TARS TTS and play in a Discord voice channel."""
    if not voice_client or not voice_client.is_connected():
        return
    try:
        from modules.module_tts import generate_tts_audio
        from modules.module_config import load_config
        tts_option = load_config()['TTS']['ttsoption']

        audio_buffer = io.BytesIO()
        async for chunk in generate_tts_audio(text, tts_option):
            if chunk:
                chunk.seek(0)
                audio_buffer.write(chunk.read())

        if audio_buffer.tell() == 0:
            return

        audio_buffer.seek(0)
        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        tmp.write(audio_buffer.read())
        tmp.close()

        # Wait for current playback to finish
        while voice_client.is_playing():
            await asyncio.sleep(0.1)

        source = discord.FFmpegPCMAudio(tmp.name)
        done = asyncio.Event()

        def after_play(error):
            if error:
                logging.error(f"Discord voice playback error: {error}")
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            bot.loop.call_soon_threadsafe(done.set)

        voice_client.play(source, after=after_play)
        await done.wait()

    except ImportError as e:
        queue_message(f"WARNING: TTS not available for Discord voice: {e}")
    except Exception as e:
        queue_message(f"ERROR: Discord voice speak failed: {e}")


def _run_side_effects_sync(reply, user_message):
    """Run LLM side effects synchronously (blocking). Used by DM handler
    so follow-up replies (web search, camera, etc.) get sent back."""
    if not isinstance(reply, dict):
        return
    func_calls = reply.get("function_calls", [])
    new_mems = reply.get("new_memories", [])
    cur_activity = reply.get("current_activity")
    if func_calls or new_mems or cur_activity:
        try:
            from modules.module_llm import llm_execute_side_effects
            llm_execute_side_effects(reply, user_message, source="discord")
        except Exception as e:
            queue_message(f"ERROR: Discord side effects failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Events
# ═══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    queue_message(f"INFO: Discord bot logged in as {bot.user}")
    # Register cog classes (skip if already loaded from a previous on_ready)
    for cog_cls in (_VoiceCog, _RemindersCog):
        if not bot.get_cog(cog_cls.__cog_name__):
            try:
                await bot.add_cog(cog_cls(bot))
            except Exception as e:
                queue_message(f"WARNING: Failed to load Discord cog {cog_cls.__name__}: {e}")


@bot.event
async def on_message(message):
    """Handle incoming messages: mentions, DMs, replies, images."""
    if message.author == bot.user:
        return

    # Let prefix commands run first
    await bot.process_commands(message)

    # Skip if this was a ! command
    ctx = await bot.get_context(message)
    if ctx.valid:
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

    user_message = _strip_bot_mention(message.content)
    if not user_message and not message.attachments:
        return

    # Track that user is talking via Discord
    from modules.module_router import set_active_route
    set_active_route("discord",
        discord_channel_id=message.channel.id,
        discord_user_id=str(message.author.id),
    )

    # Log
    queue_message(f"DM: {message.author.name}: {message.content}")

    # Image attachment
    image_b64 = await _extract_image_b64(message)
    if image_b64:
        queue_message(f"DISCORD: Image attachment from {message.author.name}")

    if not process_discord_message_callback:
        await message.channel.send("Error: No processing logic available.")
        return

    # Process with typing indicator
    async with message.channel.typing():
        try:
            reply = await asyncio.get_event_loop().run_in_executor(
                None, lambda: process_discord_message_callback(user_message, image_b64)
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

    # Run side effects inline so follow-up replies (web search results,
    # camera analysis, etc.) get sent back to Discord.
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


# ═══════════════════════════════════════════════════════════════════════════════
# !help
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="help")
async def _help_command(ctx):
    embed = discord.Embed(title="TARS Commands", color=0x3498db)
    embed.add_field(name="Chat", value=(
        "**@mention** - Talk to TARS in a channel\n"
        "**DM** - Send a direct message\n"
        "**Reply** - Reply to any TARS message"
    ), inline=False)
    embed.add_field(name="Voice", value=(
        "**!join** - Join your voice channel\n"
        "**!leave** - Leave voice channel\n"
        "**!say <text>** - Speak text in voice\n"
        "**!ask <question>** - Ask TARS and hear the answer"
    ), inline=False)
    embed.add_field(name="Reminders", value=(
        "**!remind <min> <msg>** - Set a reminder\n"
        "**!timers** - List your reminders\n"
        "**!cancel <id>** - Cancel a reminder"
    ), inline=False)
    embed.add_field(name="Other", value=(
        "**!help** - Show this message\n"
        "Attach an image to any message for visual analysis"
    ), inline=False)
    await ctx.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# Voice Cog
# ═══════════════════════════════════════════════════════════════════════════════

class _VoiceCog(commands.Cog, name="Voice"):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="join")
    async def join(self, ctx):
        """Join your current voice channel."""
        if not ctx.guild:
            await ctx.send("Voice commands only work in servers.")
            return
        if not ctx.author.voice:
            await ctx.send("You need to be in a voice channel first.")
            return

        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
            vc = ctx.voice_client
        else:
            vc = await channel.connect(
                cls=voice_recv.VoiceRecvClient if _VOICE_RECV_AVAILABLE else discord.VoiceClient
            )

        # Wait for connection
        for _ in range(10):
            if vc and vc.is_connected():
                break
            await asyncio.sleep(0.5)

        if not vc or not vc.is_connected():
            await ctx.send(f"Failed to connect to **{channel.name}**.")
            return

        await ctx.send(f"Connected to **{channel.name}**.")
        queue_message(f"INFO: Discord voice joined: {channel.name}")

    @commands.command(name="leave")
    async def leave(self, ctx):
        """Leave the current voice channel."""
        if ctx.voice_client:
            name = ctx.voice_client.channel.name
            await ctx.voice_client.disconnect()
            await ctx.send("Disconnected.")
            queue_message(f"INFO: Discord voice left: {name}")
        else:
            await ctx.send("I'm not in a voice channel.")

    @commands.command(name="say")
    async def say(self, ctx, *, text: str):
        """Speak text in the voice channel."""
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await ctx.send("I'm not in a voice channel. Use `!join` first.")
            return
        await ctx.send(f"Speaking: *{text[:100]}{'...' if len(text) > 100 else ''}*")
        await _speak_in_voice(text, ctx.voice_client)

    @commands.command(name="ask")
    async def ask(self, ctx, *, question: str):
        """Ask TARS something and hear the response in voice."""
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await ctx.send("I'm not in a voice channel. Use `!join` first.")
            return
        if not process_discord_message_callback:
            await ctx.send("Error: No processing logic available.")
            return
        from modules.module_router import set_active_route
        set_active_route("discord",
            discord_channel_id=ctx.channel.id,
            discord_user_id=str(ctx.author.id),
        )

        async with ctx.typing():
            try:
                reply = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: process_discord_message_callback(question, None)
                )
            except Exception as e:
                await ctx.send(f"Error: {e}")
                return

        reply_text = reply.get('reply', '') if isinstance(reply, dict) else (str(reply) if reply else '')
        if not reply_text:
            await ctx.send("No response generated.")
            return

        reply_text = re.sub(r'<think>.*?</think>', '', reply_text, flags=re.DOTALL).strip()
        await _send_long_message(ctx.channel, reply_text)
        await _speak_in_voice(reply_text, ctx.voice_client)

        # Run side effects inline for follow-up replies
        if isinstance(reply, dict):
            initial_reply = reply.get('reply', '')
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: _run_side_effects_sync(reply, question)
            )
            updated_reply = reply.get('reply', '')
            if updated_reply and updated_reply != initial_reply:
                followup_text = re.sub(r'<think>.*?</think>', '', updated_reply, flags=re.DOTALL).strip()
                if followup_text:
                    await _send_long_message(ctx.channel, followup_text)
                    await _speak_in_voice(followup_text, ctx.voice_client)

    @say.error
    @ask.error
    async def _voice_cmd_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Usage: `!{ctx.command.name} <text>`")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Auto-disconnect when the bot is left alone in a voice channel."""
        if member.bot:
            return
        if before.channel and before.channel != after.channel:
            vc = member.guild.voice_client
            if vc and vc.channel == before.channel:
                if not [m for m in before.channel.members if not m.bot]:
                    await vc.disconnect()
                    queue_message("INFO: Discord voice auto-disconnected (empty channel)")


# ═══════════════════════════════════════════════════════════════════════════════
# Reminders Cog — thin wrapper over skill_reminder + module_router
# ═══════════════════════════════════════════════════════════════════════════════


class _RemindersCog(commands.Cog, name="Reminders"):
    """Discord commands for reminders. All logic lives in skill_reminder.py."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="remind")
    async def remind(self, ctx, minutes: int, *, note: str):
        """Set a reminder. Usage: !remind <minutes> <message>"""
        # Update active route so the reminder fires back here
        from modules.module_router import set_active_route
        set_active_route("discord",
            discord_channel_id=ctx.channel.id,
            discord_user_id=str(ctx.author.id),
        )
        if minutes <= 0:
            await ctx.send("Minutes must be positive.")
            return
        if minutes > 10080:
            await ctx.send("Max reminder duration is 10080 minutes (1 week).")
            return

        from skills.skill_reminder import execute as reminder_execute
        result = reminder_execute(
            {"action": "set", "seconds": minutes * 60, "message": note},
            context={},
        )
        if result:
            await ctx.send(result)
        else:
            await ctx.send(
                f"Reminder set! I'll remind you in "
                f"{minutes} minute{'s' if minutes != 1 else ''}: **{note}**"
            )

    @commands.command(name="timers", aliases=["reminders"])
    async def timers(self, ctx):
        """List your active reminders."""
        from skills.skill_reminder import execute as reminder_execute
        result = reminder_execute({"action": "list"}, context={})
        await ctx.send(result or "You have no active reminders.")

    @commands.command(name="cancel", aliases=["kill"])
    async def cancel(self, ctx, reminder_id: int):
        """Cancel a reminder by ID."""
        from skills.skill_reminder import execute as reminder_execute
        result = reminder_execute(
            {"action": "cancel", "id": reminder_id}, context={}
        )
        await ctx.send(result or f"Reminder `{reminder_id}` cancelled.")

    @remind.error
    async def _remind_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!remind <minutes> <message>`\nExample: `!remind 30 Check the oven`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("First argument must be a number of minutes.")
