"""
module_engine.py

Core module for TARS-AI responsible for:
- Predicting user intents and determining required modules.
- Executing tool-specific functions like web searches, vision analysis, and volume control.

This is achieved using a pre-trained Naive Bayes classifier and TF-IDF vectorizer.
"""
# MIT License
# 
# Copyright (c)
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# === Standard Libraries ===
import os
import joblib
from datetime import datetime
import threading
import json
import re

# === Custom Modules ===
from modules.module_websearch import search_google, search_google_news
from modules.module_vision import describe_camera_view
from modules.module_stablediffusion import generate_image
from modules.module_volume import handle_volume_command
from modules.module_homeassistant import send_prompt_to_homeassistant
from modules.module_tts import generate_tts_audio
from modules.module_config import load_config, update_character_setting
from modules.module_messageQue import queue_message
from modules.module_btcontroller import turnRight, turnLeft, poseaction, unposeaction, stepForward

# === Constants ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Move up to "src"
MODEL_FILENAME = os.path.join(BASE_DIR, 'engine/pickles/naive_bayes_model.pkl')
VECTORIZER_FILENAME = os.path.join(BASE_DIR, 'engine/pickles/module_engine_model.pkl')
TRAINING_DATA_PATH = os.path.join(BASE_DIR, 'engine/training/training_data.csv')

CONFIG = load_config()


# === Load Models ===
try:
    if not os.path.exists(VECTORIZER_FILENAME):
        raise FileNotFoundError("Vectorizer file not found.")
    if not os.path.exists(MODEL_FILENAME):
        raise FileNotFoundError("Model file not found.")
    nb_classifier = joblib.load(MODEL_FILENAME)
    tfidf_vectorizer = joblib.load(VECTORIZER_FILENAME)

except FileNotFoundError as e:
    # Attempt to train models if files are missing
    import module_engineTrainer
    module_engineTrainer.train_text_classifier()
    try:
        nb_classifier = joblib.load(MODEL_FILENAME)
        tfidf_vectorizer = joblib.load(VECTORIZER_FILENAME)
    except Exception as retry_exception:
        raise RuntimeError("Critical error while loading models.") from retry_exception

# === Functions ===
def execute_movement(movements):
    """
    Executes a sequence of movements in a separate thread.
    'movements' should be a list like ["forward", "forward", "left"].
    """
    def movement_task():
            
        action_map = {
            "right": turnRight,
            "left": turnLeft,
            "poseaction": poseaction,
            "unposeaction": unposeaction,
            "forward": stepForward
        }

        try:
            for i, move in enumerate(movements, start=1):
                action_function = action_map.get(move)
                if callable(action_function):
                    action_function()
                else:
                    queue_message(f"[ERROR] Movement '{move}' not found in action_map.")
        except Exception as e:
            queue_message(f"[ERROR] Unexpected error while executing movements: {e}")
        finally:
            queue_message(f"[DEBUG] Thread completed for movements: {movements}")

    # Start the thread
    thread = threading.Thread(target=movement_task, daemon=True)
    thread.start()
    return thread


def call_function(module_name, *args, **kwargs):
    if module_name not in FUNCTION_REGISTRY:
        return "Not a Function"
    func = FUNCTION_REGISTRY[module_name]
    try:
        # Check if the function requires arguments
        if func.__code__.co_argcount == 0:  # No arguments expected
            return func()
        else:  # Pass arguments if required
            return func(*args, **kwargs)
    except Exception as e:
        queue_message(f"[DEBUG] Error while executing {module_name}: {e}")



def adjust_persona(user_input):
    """
    Adjust the personality traits of TARS, such as humor, empathy, or formality.

    Parameters:
    - user_input (str): The natural language command specifying the trait and its new value (e.g., "Set humor to 75%").

    Returns:
    - str: A confirmation message indicating the updated trait and value, or an error message if the input is invalid.
    """

    from module_llm import raw_complete_llm
    # Define the prompt with placeholders
    prompt = f"""
    You are TARS, an AI module responsible for extracting personality trait adjustments. Your job is to:

    1. Identify the personality trait being adjusted from the following options only:
    - honesty
    - humor
    - empathy
    - curiosity
    - confidence
    - formality
    - sarcasm
    - adaptability
    - discipline
    - imagination
    - emotional_stability
    - pragmatism
    - optimism
    - resourcefulness
    - cheerfulness
    - engagement
    - respectfulness

    2. Extract the value being assigned to the personality trait, ensuring it is a valid percentage (0–100).

    3. Respond with a structured JSON output in the exact format:
    {{
        "persona": {{
            "trait": "<TRAIT>",
            "value": <VALUE>
        }}
    }}

    Rules:
    - Always output a single JSON object with the fields "trait" and "value".
    - Do not output explanations, variations, or multiple commands.
    - If the value is not specified, respond with:
    {{"error": "Value not provided"}}
    - Ensure the trait matches one of the listed options exactly.

    Examples:
    Input: "TARS, adjust your humor setting to 69%"
    Output:
    {{
        "persona": {{
            "trait": "humor",
            "value": 69
        }}
    }}

    Input: "Increase empathy to 60%, TARS."
    Output:
    {{
        "persona": {{
            "trait": "empathy",
            "value": 60
        }}
    }}

    Input: "TARS, can you be more respectful?"
    Output:
    {{
        "persona": {{
            "trait": "respectfulness",
            "value": 60
        }}
    }}

    Input: "TARS, set curiosity higher."
    Output:
    {{
        "error": "Value not provided"
    }}

    Instructions:
    - Use only the specified traits (honesty, humor, empathy, etc.).
    - Ensure the JSON output is properly formatted and follows the example structure exactly.
    - Process the input as a single command and provide a one-line JSON output.

    Input: "{user_input}"
    Output:
    """

    try:
        data = raw_complete_llm(prompt)

        # Strip out the markdown block (```json) and newlines, then parse the JSON response
        data = re.sub(r'```json\n|\n```', '', data).strip()

        # Parse the JSON response
        extracted_data = json.loads(data)

        # Access the "persona" object
        persona_data = extracted_data.get("persona", {})
        trait = persona_data.get("trait")
        value = persona_data.get("value")

        # Validate the extracted data
        if trait and value:
            if isinstance(trait, str) and isinstance(value, int):
                queue_message(f"INFO: Saving {trait}, {value}")
                update_character_setting(trait, value)
                return f"Updated {trait} setting to {value}"
            else:
                #queue_message("[ERROR] Invalid types")
                return False
        else:
            #queue_message("[ERROR] Missing in the response.")
            return False
    
    except Exception as e:
        return f"Error processing the movement command: {e}"

 
# === Function Calling ===
FUNCTION_REGISTRY = {
    "Weather": search_google, 
    "News": search_google_news,
    "Vision": describe_camera_view,
    "Search": search_google,
    "SDmodule-Generate": generate_image,
    "Volume": handle_volume_command,
    "Persona": adjust_persona,
    "Home_Assistant": send_prompt_to_homeassistant
}
