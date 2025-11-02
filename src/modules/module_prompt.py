"""
module_prompt.py

Utility module for building prompts for LLM backends.
"""

from datetime import datetime
import os
from modules.module_engine import check_for_module
from modules.module_messageQue import queue_message

def build_prompt(user_prompt, character_manager, memory_manager, config, debug=False):
    """
    Build a dynamically optimized prompt for the LLM backend.

    Parameters:
    - user_prompt (str): The user's input prompt.
    - character_manager: The CharacterManager instance.
    - memory_manager: The MemoryManager instance.
    - config (dict): Configuration dictionary.
    - debug (bool): If True, print debug information.

    Returns:
    - str: The formatted prompt for the LLM backend.
    """
    now = datetime.now()
    dtg = f"Current Date: {now.strftime('%m/%d/%Y')}\nCurrent Time: {now.strftime('%H:%M:%S')}\n"
    user_name = config['CHAR']['user_name']
    char_name = character_manager.char_name
    functioncall = check_for_module(user_prompt)

    # Construct persona traits
    persona_traits = "\n".join(
        [f"- {trait}: {value}" for trait, value in character_manager.traits.items()]
    )

    
    # Build the base prompt
    base_prompt = (
        f"System: {config['LLM']['systemprompt']}\n\n"
        f"### Instruction:\n{inject_dynamic_values(config['LLM']['instructionprompt'], user_name, char_name)}\n\n"
        f"### Interaction Context:\n---\n"
        f"User: {user_name}\n"
        f"Character: {char_name}\n"
        f"{dtg}\n---\n\n"
        f"### Character Details:\n---\n{character_manager.character_card}\n---\n\n"
        f"### {char_name} Settings:\n{persona_traits}\n---\n\n"
    )

    # Dynamically append memory and examples
    final_prompt = append_memory_and_examples(
        base_prompt, user_prompt, memory_manager, config, character_manager, functioncall
    )

    final_prompt = inject_dynamic_values(final_prompt, user_name, char_name)

    if debug:
        queue_message(f"DEBUG PROMPT:\n{final_prompt}")

    return clean_text(final_prompt)

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

def append_memory_and_examples(base_prompt, user_prompt, memory_manager, config, character_manager, functioncall):
    """
    Append short-term memory and example dialog to the prompt based on token availability.

    Parameters:
    - base_prompt (str): The base portion of the prompt.
    - user_prompt (str): The user's input prompt.
    - memory_manager: The MemoryManager instance.
    - config (dict): Configuration dictionary.
    - character_manager: The CharacterManager instance.
    - functioncall (str): The function determined by the input.

    Returns:
    - str: The full prompt with memory and examples included.
    """
    # Prepare memory and examples
    past_memory = clean_text(memory_manager.get_longterm_memory(user_prompt))
    short_term_memory = ""
    example_dialog = ""

    total_base_prompt = "".join([
    base_prompt,
    f"### Memory:\n---\nLong-Term Context:\n{past_memory}\n---\n",
    f"### Interaction:\n{config['CHAR']['user_name']}: {user_prompt}\n\n",
    f"### Function Calling Tool:\nResult: {functioncall}\n"
    f"### Response:\n{character_manager.char_name}: "
    ])

    #queue_message(f"base prompt {memory_manager.token_count(base_prompt).get('length', 0)}")

    context_size = int(config['LLM']['contextsize'])
    base_length = memory_manager.token_count(total_base_prompt).get('length', 0)
    available_tokens = max(0, context_size - base_length)

    #queue_message(f"context_size {context_size}: base_length{base_length}: available_tokens: {available_tokens} ")

    # Add short-term memory first
    if available_tokens > 0:
        short_term_memory = memory_manager.get_shortterm_memories_tokenlimit(available_tokens)
        memory_length = memory_manager.token_count(short_term_memory).get('length', 0)
        available_tokens -= memory_length
        #queue_message(f"Tokens after short term {available_tokens}")

    # Add example dialog only if there's space remaining
    if available_tokens > 0 and character_manager.example_dialogue:
        example_length = memory_manager.token_count(character_manager.example_dialogue).get('length', 0)
        if example_length <= available_tokens:
            example_dialog = f"### Example Dialog:\n{character_manager.example_dialogue}\n---\n"

    # Append memory and examples to the prompt
    return (
        f"{base_prompt}"
        f"{example_dialog}"
        f"### Memory:\n---\nLong-Term Context:\n{past_memory}\n---\n"
        f"Recent Conversation:\n{short_term_memory}\n---\n"
        f"### Interaction:\n{config['CHAR']['user_name']}: {user_prompt}\n\n"
        f"### Function Calling Tool:\nResult: {functioncall}\n"
        f"### Response:\n{character_manager.char_name}: "
    )

def inject_dynamic_values(template, user_name, char_name):
    """
    Replace placeholders in a template with dynamic values.

    Parameters:
    - template (str): Template string containing placeholders.
    - user_name (str): User's name.
    - char_name (str): Character's name.

    Returns:
    - str: Template with placeholders replaced.
    """
    return (
        template
        .replace("{user}", user_name)
        .replace("{char}", char_name)
        .replace("'user_input'", user_name)
        .replace("'bot_response'", char_name)
    )