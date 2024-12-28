"""
module_discord.py

Discord Integration Module for GPTARS Application.

This module provides integration with Discord for real-time interaction. 
It allows the bot to respond to messages and mentions in a specified Discord channel.
"""

# === Standard Libraries ===
import discord
import time

# === Custom Modules ===
from module_config import load_config

# === Constants and Globals ===
CONFIG = load_config()

# === Initialization ===
intents = discord.Intents.default() # Initialize Discord client with appropriate intents
intents.message_content = True
client = discord.Client(intents=intents)

# Event: Bot successfully connected to Discord
@client.event
async def on_ready():
    """
    Triggered when the bot connects to Discord and is ready to operate.
    Sends a greeting message to the specified channel.
    """
    print(f"Logged in as {client.user}")
    
    # Fetch the channel by its ID
    channel = client.get_channel(CONFIG['DISCORD']['channel_id'])  # Replace `channel_id` with the actual channel ID
    if channel:
        await channel.send(char_greeting)
        print(f"Greeting sent to channel: {CONFIG['DISCORD']['channel_id']}")
    else:
        print(f"Channel with ID {CONFIG['DISCORD']['channel_id']} not found.")

# Event: Respond to messages in Discord
@client.event
async def on_message(message):
    """
    Triggered when a message is sent in a channel the bot can access.

    Parameters:
    - message (discord.Message): The incoming Discord message object.
    """
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # Respond to mentions
    if message.content.startswith(f"<@{client.user.id}>"):
        user_message = message.content.strip()
        print(f"User message: {user_message}")

        # Generate a response using the GPTARS process_completion function
        global start_time, latest_text_to_read
        start_time = time.time()
        reply = process_completion(user_message)
        print(f"Bot reply: {reply}")

        # Store and send the generated reply
        latest_text_to_read = reply
        await message.channel.send(latest_text_to_read)
