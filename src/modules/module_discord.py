"""
module_discord.py

Discord Integration Module for GPTARS Application.

This module provides integration with Discord for real-time interaction. 
It allows the bot to respond to messages and mentions in a specified Discord channel.
"""

# === Standard Libraries ===
import discord

# === Custom Modules ===
from modules.module_config import load_config

# === Constants and Globals ===
CONFIG = load_config()
process_discord_message_callback = None

# === Initialization ===
intents = discord.Intents.default()  # Initialize Discord client with appropriate intents
intents.message_content = True
intents.voice_states = True  # Enable voice state intents if necessary
client = discord.Client(intents=intents)

def start_discord_bot(callback):
    """
    Starts the Discord bot with a message processing callback.

    Parameters:
    - callback (function): A function that processes user messages and returns a response.
    """
    global process_discord_message_callback
    process_discord_message_callback = callback

    bot_token = CONFIG['DISCORD']['TOKEN']
    client.run(bot_token)
    
async def replace_mentions_with_usernames(content):
    """
    Replace all mentions in the content with their corresponding usernames.

    Args:
        content: The message content containing mentions.

    Returns:
        The content with mentions replaced by usernames.
    """
    words = content.split()
    for i, word in enumerate(words):
        if word.startswith("<@") and word.endswith(">"):
            username = await mention_to_username(word)
            if username:
                words[i] = f"@{username}"  # Replace mention with username
    return " ".join(words)

async def mention_to_username(mention):
    """
    Convert a Discord mention (e.g., <@200301865894805504>) into the username.

    Args:
        mention: The mention string (e.g., <@200301865894805504>).

    Returns:
        The username as a string or None if the user is not found.
    """
    if mention.startswith("<@") and mention.endswith(">"):
        # Extract the user ID from the mention
        user_id = mention.strip("<@!>")  # Handles both <@ID> and <@!ID>
        try:
            user_id = int(user_id)  # Convert the extracted ID to an integer
        except ValueError:
            return None  # Invalid mention format, return None

        try:
            # Use the client to fetch the user by ID
            user = await client.fetch_user(user_id)
            if user:
                return user.name  # Return the user's username
        except discord.NotFound:
            print(f"ERROR: User with ID {user_id} not found.")
        except discord.Forbidden:
            print("ERROR: Insufficient permissions to fetch user details.")
        except discord.HTTPException as e:
            print(f"ERROR: HTTP error occurred: {e}")

    return None  # If the mention format or user is invalid

@client.event
async def on_ready():
    print(f"INFO: Logged in as {client.user}")


@client.event
async def on_message(message):
    """
    Triggered when a message is sent in a channel the bot can access.
    """
    global process_discord_message_callback

    if message.author == client.user:
        return  # Prevent the bot from replying to itself
    
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # Respond to mentions
    if message.content.startswith(f"<@{client.user.id}>"):
        user_message = message.content.strip()

       
        print(f"DISCORD: {await replace_mentions_with_usernames(user_message)}")

        # Use the callback to process the message
        if process_discord_message_callback:
            reply = process_discord_message_callback(user_message)
            print(f"DISCORD: {await replace_mentions_with_usernames(message.author.mention)} {reply}")

            await message.channel.send(f"{message.author.mention} {reply}")
        else:
            print("No callback function defined.")
            await message.channel.send("Error: No processing logic available.")
