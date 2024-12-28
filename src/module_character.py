"""
module_character.py

Character Management Module for GPTARS Application.

This module manages character attributes and dynamic properties for the GPTARS application.
"""

# === Standard Libraries ===
import re
from datetime import datetime

class CharacterManager:
    """
    Manages character attributes and dynamic properties for GPTARS.
    """
    def __init__(self, config):
        self.config = config
        self.character_card_path = config['CHAR']['character_card_path']
        self.character_card = None
        self.char_name = None
        self.char_persona = None
        self.personality = None
        self.world_scenario = None
        self.char_greeting = None
        self.example_dialogue = None
        self.voice_only = config['TTS']['voice_only']
        self.humor = None
        self.mood = None
        self.load_character_attributes()

    def load_character_attributes(self):
        """
        Load character attributes from the character card file specified in the config.
        """
        try:
            with open(self.character_card, "r") as file:
                content = file.read()

            # Helper to extract matches
            def extract_match(pattern, group=2, default=""):
                match = re.search(pattern, content)
                return match.group(group) if match else default

            self.char_name = extract_match(r'("char_name"|"name"):\s*"([^"]*)"', content)
            self.char_persona = extract_match(r'("char_persona"|"description"):\s*"([^"]*)"', content)
            self.personality = extract_match(r'"personality":\s*"([^"]*)"', content, group=1)
            self.world_scenario = extract_match(r'("world_scenario"|"scenario"):\s*"([^"]*)"', content)
            self.char_greeting = extract_match(r'("char_greeting"|"first_mes"):\s*"([^"]*)"', content)
            self.example_dialogue = extract_match(r'("example_dialogue"|"mes_example"):\s*"([^"]*)"', content)

            # Format the greeting with placeholders
            self.char_greeting = self.char_greeting.replace("{{user}}", self.config['CHAR']['user_name'])
            self.char_greeting = self.char_greeting.replace("{{char}}", self.char_name)
            self.char_greeting = self.char_greeting.replace("{{time}}", datetime.now().strftime("%Y-%m-%d %H:%M"))

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Character loaded: {self.char_name}")
        except FileNotFoundError:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Character file '{self.character_card}' not found.")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Error while loading character attributes: {e}")