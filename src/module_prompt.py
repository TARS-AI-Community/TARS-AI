"""
module_prompt.py

Utility module for building prompts for LLM backends.
"""

from datetime import datetime
import os

from module_engine import check_for_module

# === Constants and Globals ===
character_manager = None
memory_manager = None

def build_prompt(user_prompt, character_manager, memory_manager, config):
    """
    Build the prompt structure for the Large Language Model (LLM) backend.

    Parameters:
    - user_prompt (str): The user's input prompt.
    - character_manager: The CharacterManager instance.
    - memory_manager: The MemoryManager instance.
    - config (dict): configuration dictionary.

    Returns:
    - str: The formatted prompt for the LLM backend.
    """
    
    now = datetime.now() # Current date and time
    date = now.strftime("%m/%d/%Y")
    time = now.strftime("%H:%M:%S")

    module_engine = check_for_module(user_prompt)
    if module_engine == "Mute":
        return
 
    # Build basic prompt structure
    dtg = f"Current Date: {date}\nCurrent Time: {time}\n"
    past = memory_manager.get_longterm_memory(user_prompt) # Get past memories
    # Correct the order and logic of replacements clean up memories and past json crap
    past = past.replace("\\\\", "\\")  # Reduce double backslashes to single
    past = past.replace("\\n", "\n")   # Replace escaped newline characters with actual newlines
    past = past.replace("\\'", "'")    # Replace escaped single quotes with actual single quotes
    past = past.replace("\'", "'")    # Replace escaped single quotes with actual single quotes

    history = ""
    userInput = user_prompt  # Simulating user input to avoid hanging

    promptsize =  (
        f"System: {config['LLM']['systemprompt']}\n\n"
        f"### Instruction: {config['LLM']['instructionprompt']}\n\n"
        f"{dtg}\n"
        f"User details include: {config['CHAR']['user_details']}\n"
        f"{module_engine}\n"
        f"{character_manager.character_card}\n"
        f"A past memory for context {past}\n\n"
        f"Recent Conversation:\n {history}\n\n"
        f"{config['CHAR']['user_name']}: {userInput}\n"
        f"### Response: {character_manager.char_name}: "
    )

    # Calc how much space is avail for chat history
    remaining = memory_manager.token_count(promptsize).get('length', 0)
    memallocation = int(config['LLM']['contextsize'] - remaining)
    history = memory_manager.get_shortterm_memories_tokenlimit(memallocation)

    prompt = (
        f"System: {config['LLM']['systemprompt']}\n\n"
        f"### Instruction: {config['LLM']['instructionprompt']}\n\n"
        f"{dtg}\n"
        f"User details include: {config['CHAR']['user_details']}\n"
        f"{module_engine}\n"
        f"{character_manager.character_card}\n"
        f"A past memory for context {past}\n\n"
        f"Recent Conversation:\n {history}\n\n"
        f"{config['CHAR']['user_name']}: {userInput}\n"
        f"### Response: {character_manager.char_name}: "
    )

    prompt = prompt.replace("{user}", config['CHAR']['user_name']) 
    prompt = prompt.replace("{char}", os.path.splitext(os.path.basename(config['CHAR']['character_card_path']))[0])
    prompt = clean_text(prompt)
    return prompt


def clean_text(text):
    """
    Clean and format text for inclusion in the prompt.

    Parameters:
    - text (str): The text to clean.

    Returns:
    - str: Cleaned text.
    """
    return (
        text.replace("\\\\", "\\")
        .replace("\\n", "\n")
        .replace("\\'", "'")
        .replace('\\"', '"')
        .replace("<END>", "")
        .strip()
    )