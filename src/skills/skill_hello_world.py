"""
Skill: hello_world — Example skill template for creating new skills.

Copy this file and rename it to skill_<your_name>.py to create a new skill.
Skills are auto-discovered from the src/skills/ folder — no other files need editing.

Requirements:
  1. Filename must start with "skill_" and end with ".py"
  2. Must have a SKILL dict with at least "name" and "prompt"
  3. Must have an execute(parameters, context) function

Config fields (optional):
  Defined in SKILL["config"], saved to [SKILL:<name>] in config.ini.
  Types: text, number, bool, select, password
  Access in execute() via: context["skill_config"]

API keys / tokens:
  Store secrets in .env (never in the skill file or config.ini).
  Access in execute() via: os.getenv("YOUR_KEY")
"""

import os

SKILL = {
    "name": "hello_world",
    "description": "Example skill — responds with a greeting",

    # Optional: config fields shown in the web UI Skills panel
    "config": {
        "greeting": {
            "type": "text",
            "default": "Hello, World!",
            "description": "The greeting message to return",
        },
    },

    # The prompt tells the LLM when and how to call this skill
    "prompt": """hello_world
   Triggers: Use when the user says "hello world" or asks for a test greeting.
   Parameters: {{"name": "optional name to greet"}}
   Example: {{"function": "hello_world", "parameters": {{"name": "Cooper"}}}}""",

    # Example conversations help the LLM understand the expected JSON format
    "examples": [
        """Example - Hello world:
User: "Say hello world"
Response: {{"question": "Say hello world", "reply": "Hello, World!", "function_calls": [{{"function": "hello_world", "parameters": {{"name": ""}}}}], "new_memories": []}}""",
    ],
}


def execute(parameters, context):
    """Called by the skill manager when the LLM invokes this skill.

    Args:
        parameters: Dict from the LLM's function call (e.g. {"name": "Cooper"})
        context: Dict with skill_config, user_input, config, and more

    Returns:
        A string response shown to the user, or None
    """
    skill_config = context.get("skill_config", {})
    greeting = skill_config.get("greeting", "Hello, World!")
    name = parameters.get("name", "")

    if name:
        return f"{greeting} Nice to meet you, {name}!"
    return greeting
