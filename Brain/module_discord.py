import discord
import time

# Set up Discord intents and client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Event: Bot has connected to Discord
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    channel = client.get_channel(channel_id)  # Replace `channel_id` with the actual channel ID
    if channel:
        await channel.send(char_greeting)

# Event: On receiving a message
@client.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # Process messages that mention the bot
    if message.content.startswith(f"<@{client.user.id}>"):
        user_message = message.content
        print(f"User message: {user_message}")

        # Generate a response
        global start_time, latest_text_to_read
        start_time = time.time()
        reply = process_completion(user_message)
        print(f"Bot reply: {reply}")
        latest_text_to_read = reply

        # Send the response back to the channel
        await message.channel.send(latest_text_to_read)
