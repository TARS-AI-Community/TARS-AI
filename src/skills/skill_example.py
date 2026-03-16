"""
Skill: Example — Example skill template for creating new skills.

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

Follow-up mode (optional):
  "followup": True  — TARS says a placeholder, runs the skill, then speaks the result.
                      Use for skills that fetch data (search, vision, APIs).
  "followup": False — (default) fire-and-forget: TARS speaks the reply and the
                      skill runs in the background. Use for actions (volume, lights, movements).

API keys / tokens:
  Store secrets in .env (never in the skill file or config.ini).
  Access in execute() via: os.getenv("YOUR_KEY")
"""

import os
import random

SKILL = {
    "name": "example",
    "description": "Example skill — tells a random fun fact",

    # Follow-up mode:
    #   True  = TARS says a placeholder, runs the skill, then speaks the result
    #   False = (default) TARS speaks the reply and the skill runs in the background
    "followup": True,

    # Config fields: shown in the web UI Skills panel
    # Saved to [SKILL:example] in config.ini. Access via context["skill_config"]
    "config": {
        "category": {
            "type": "select",
            "default": "any",
            "options": ["any", "space", "animals", "food"],
            "description": "Category of fun facts to choose from",
        },
        # Other field types you can use:
        # "count":   {"type": "number", "default": 1, "min": 1, "max": 10, "description": "..."},
        # "enabled": {"type": "bool",   "default": True, "description": "..."},
        # "url":     {"type": "text",   "default": "http://...", "description": "..."},
    },

    # The prompt tells the LLM when and how to call this skill
    "prompt": """example
   Triggers: MUST call when the user says "skill example" or "run skill example".
   Parameters: {{"category": "optional: space, animals, or food"}}
   Example: {{"function": "example", "parameters": {{"category": "space"}}}}""",

    # Example conversations help the LLM understand the expected JSON format
    "examples": [
        """Example - Skill example:
User: "skill example"
Response: {{"reply": "One sec.", "function_calls": [{{"function": "example", "parameters": {{"category": ""}}}}], "new_memories": []}}""",
    ],
}

def execute(parameters, context):
    """Called by the skill manager when the LLM invokes this skill.

    Args:
        parameters: Dict from the LLM's function call (e.g. {"category": "space"})
        context: Dict with skill_config, user_input, config, and more

    Returns:
        A string that TARS will speak as a follow-up (since followup=True)
    """

    # Fun facts organized by category
    FACTS = {
        "space": [
            "A day on Venus is longer than a year on Venus.",
            "Neutron stars are so dense that a teaspoon would weigh about 6 billion tons.",
            "There are more stars in the universe than grains of sand on all of Earth's beaches.",
            "The footprints on the Moon will be there for 100 million years.",
        ],
        "animals": [
            "Octopuses have three hearts and blue blood.",
            "A group of flamingos is called a flamboyance.",
            "Cows have best friends and get stressed when separated.",
            "Sea otters hold hands while sleeping so they don't drift apart.",
        ],
        "food": [
            "Honey never spoils. Archaeologists found 3000-year-old honey that was still edible.",
            "Bananas are technically berries, but strawberries aren't.",
            "The most expensive pizza in the world costs over 12,000 dollars.",
            "Peanuts are one of the ingredients in dynamite.",
        ],
    }

    skill_config = context.get("skill_config", {})
    category = parameters.get("category", "") or skill_config.get("category", "any")

    if category in FACTS:
        facts = FACTS[category]
    else:
        facts = [fact for cat_facts in FACTS.values() for fact in cat_facts]

    return random.choice(facts)
