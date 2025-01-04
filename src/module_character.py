"""
module_character.py

Character Management Module for TARS-AI Application.

This module manages character attributes and dynamic properties for the TARS-AI application.
"""

# === Standard Libraries ===
import json
from datetime import datetime

class CharacterManager:
    """
    Manages character attributes and dynamic properties for TARS-AI.
    """
    def __init__(self, config):
        self.config = config
        self.character_card_path = config['CHAR']['character_card_path']
        self.character_card = None
        self.char_name = None
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
            with open(self.character_card_path, "r") as file:
                data = json.load(file)

            self.char_name = data.get("char_name", "")
            self.personality = data.get("personality", "")
            self.world_scenario = data.get("world_scenario", "")
            self.char_greeting = data.get("char_greeting", "")
            self.example_dialogue = data.get("example_dialogue", "")

            # Format the greeting with placeholders
            if self.char_greeting:
                self.char_greeting = self.char_greeting.replace("{{user}}", self.config['CHAR']['user_name'])
                self.char_greeting = self.char_greeting.replace("{{char}}", self.char_name)
                self.char_greeting = self.char_greeting.replace("{{time}}", datetime.now().strftime("%Y-%m-%d %H:%M"))

            self.character_card = f"\nPersonality: {self.personality}\n"\
                                    f"\nWorld Scenario: {self.world_scenario}\n"\
                                    f"\nExample Dialog:\n{self.example_dialogue}\n"

            print(f"LOAD: Character loaded: {self.char_name}")
        except FileNotFoundError:
            print(f"ERROR: Character file '{self.character_card_path}' not found.")
        except Exception as e:
            print(f"ERROR: Error while loading character attributes: {e}")