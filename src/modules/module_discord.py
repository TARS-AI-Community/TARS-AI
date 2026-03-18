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
import sqlite3
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


def _run_side_effects(reply, user_message):
    """Run LLM side effects (function calls, memories) in a background thread."""
    if not isinstance(reply, dict):
        return
    func_calls = reply.get("function_calls", [])
    new_mems = reply.get("new_memories", [])
    cur_activity = reply.get("current_activity")
    if func_calls or new_mems or cur_activity:
        try:
            from modules.module_llm import llm_execute_side_effects
            threading.Thread(
                target=llm_execute_side_effects,
                args=(reply, user_message),
                kwargs={"source": "discord"}, daemon=True
            ).start()
        except Exception as e:
            queue_message(f"ERROR: Discord side effects failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Events
# ═══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    queue_message(f"INFO: Discord bot logged in as {bot.user}")
    # Register cog classes directly — no external files needed
    for cog_cls in (_VoiceCog, _RemindersCog):
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

    # Determine whether to respond
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user in message.mentions
    is_reply_to_bot = (
        message.reference
        and message.reference.resolved
        and isinstance(message.reference.resolved, discord.Message)
        and message.reference.resolved.author == bot.user
    )

    if not (is_dm or is_mention or is_reply_to_bot):
        return

    user_message = _strip_bot_mention(message.content)
    if not user_message and not message.attachments:
        return

    # Log
    display = await replace_mentions_with_usernames(message.content)
    queue_message(f"{'DM' if is_dm else 'DISCORD'}: {message.author.name}: {display}")

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

    if is_dm:
        await _send_long_message(message.channel, reply_text)
    else:
        await _send_long_message(message.channel, f"{message.author.mention} {reply_text}")

    queue_message(f"DISCORD: Replied to {message.author.name}")
    _run_side_effects(reply, user_message)


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
        _run_side_effects(reply, question)

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
# Reminders Cog
# ═══════════════════════════════════════════════════════════════════════════════

# Reminders DB lives next to other TARS data
_REMINDERS_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'memory', 'discord_reminders.db'
)


def _get_reminders_db():
    os.makedirs(os.path.dirname(_REMINDERS_DB), exist_ok=True)
    conn = sqlite3.connect(_REMINDERS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            due_time TEXT NOT NULL,
            note TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


class _RemindersCog(commands.Cog, name="Reminders"):

    def __init__(self, bot):
        self.bot = bot
        self._tasks = {}  # id -> asyncio.Task
        self.bot.loop.create_task(self._load())

    async def _load(self):
        await self.bot.wait_until_ready()
        conn = _get_reminders_db()
        try:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE due_time > ?", (datetime.now().isoformat(),)
            ).fetchall()
            for row in rows:
                self._schedule(dict(row))
            if rows:
                queue_message(f"INFO: Discord reminders: rescheduled {len(rows)}")
        finally:
            conn.close()

    def _schedule(self, data):
        rid = data['id']
        due = datetime.fromisoformat(data['due_time'])

        async def _fire():
            delay = (due - datetime.now()).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            ch = self.bot.get_channel(int(data['channel_id']))
            if ch:
                await ch.send(f"**REMINDER:** <@{data['user_id']}> - {data['note']}")
            self._db_delete(rid)
            self._tasks.pop(rid, None)

        self._tasks[rid] = self.bot.loop.create_task(_fire())

    def _db_delete(self, rid):
        conn = _get_reminders_db()
        try:
            conn.execute("DELETE FROM reminders WHERE id = ?", (rid,))
            conn.commit()
        finally:
            conn.close()

    @commands.command(name="remind")
    async def remind(self, ctx, minutes: int, *, note: str):
        """Set a reminder. Usage: !remind <minutes> <message>"""
        if minutes <= 0:
            await ctx.send("Minutes must be positive.")
            return
        if minutes > 10080:
            await ctx.send("Max reminder duration is 10080 minutes (1 week).")
            return

        due_time = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        conn = _get_reminders_db()
        try:
            cur = conn.execute(
                "INSERT INTO reminders (user_id, channel_id, due_time, note) VALUES (?,?,?,?)",
                (str(ctx.author.id), str(ctx.channel.id), due_time, note)
            )
            rid = cur.lastrowid
            conn.commit()
        finally:
            conn.close()

        self._schedule({
            'id': rid, 'user_id': str(ctx.author.id),
            'channel_id': str(ctx.channel.id), 'due_time': due_time, 'note': note
        })
        await ctx.send(
            f"Reminder set (ID: {rid}). "
            f"I'll remind you in {minutes} minute{'s' if minutes != 1 else ''}: **{note}**"
        )

    @commands.command(name="timers", aliases=["reminders"])
    async def timers(self, ctx):
        """List your active reminders."""
        conn = _get_reminders_db()
        try:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE user_id = ? ORDER BY due_time ASC",
                (str(ctx.author.id),)
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            await ctx.send("You have no active reminders.")
            return

        embed = discord.Embed(title="Your Active Reminders", color=0x3498db)
        for row in rows:
            left = datetime.fromisoformat(row['due_time']) - datetime.now()
            mins = max(0, int(left.total_seconds() // 60))
            status = f"In {mins}m" if mins > 0 else "Due now!"
            embed.add_field(name=f"ID: {row['id']} | {status}", value=row['note'], inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="cancel", aliases=["kill"])
    async def cancel(self, ctx, reminder_id: int):
        """Cancel a reminder by ID."""
        conn = _get_reminders_db()
        try:
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ? AND user_id = ?",
                (reminder_id, str(ctx.author.id))
            ).fetchone()
        finally:
            conn.close()

        if not row:
            await ctx.send(f"Reminder `{reminder_id}` not found or doesn't belong to you.")
            return

        task = self._tasks.pop(reminder_id, None)
        if task:
            task.cancel()
        self._db_delete(reminder_id)
        await ctx.send(f"Reminder `{reminder_id}` cancelled.")

    @remind.error
    async def _remind_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `!remind <minutes> <message>`\nExample: `!remind 30 Check the oven`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("First argument must be a number of minutes.")
