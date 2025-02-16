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

# === Custom Modules ===
from modules.module_websearch import search_google, search_google_news
from modules.module_vision import describe_camera_view
from modules.module_stablediffusion import generate_image
from modules.module_volume import handle_volume_command
from modules.module_homeassistant import send_prompt_to_homeassistant
from modules.module_tts import generate_tts_audio
from modules.module_config import load_config, update_character_setting

# === Constants ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Move up to "src"
MODEL_FILENAME = os.path.join(BASE_DIR, 'engine/pickles/naive_bayes_model.pkl')
VECTORIZER_FILENAME = os.path.join(BASE_DIR, 'engine/pickles/module_engine_model.pkl')
TRAINING_DATA_PATH = os.path.join(BASE_DIR, 'engine/training/training_data.csv')

CONFIG = load_config()

#mode to use Naive Bayes or LLM for function calling
mode = "NB"

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
def execute_movement(movement, times):
    """
    Executes the specified movement in a separate thread.
    """
    def movement_task():
        print(f"[DEBUG] Thread started for movement: {movement} x {times}")
        from module_btcontroller import turnRight, turnLeft, poseaction, unposeaction, stepForward
        
        action_map = {
            "turnRight": turnRight,
            "turnLeft": turnLeft,
            "poseaction": poseaction,
            "unposeaction": unposeaction,
            "stepForward": stepForward,
        }
        
        try:
            action_function = action_map.get(movement)
            if callable(action_function):
                for i in range(int(times)):
                    print(f"[DEBUG] Executing {movement}, iteration {i + 1}/{times}")
                    action_function()  # Blocking for this thread
            else:
                print(f"[ERROR] Movement '{movement}' not found in action_map.")
        except Exception as e:
            print(f"[ERROR] Unexpected error while executing movement: {e}")
        finally:
            print(f"[DEBUG] Thread completed for movement: {movement} x {times}")

    # Start the thread
    thread = threading.Thread(target=movement_task, daemon=True)
    thread.start()
    return thread  # Return the thread object if needed

def movement_llmcall(user_input):
    """
    Interpret and execute movement commands based on user input using an LLM.

    Parameters:
    - user_input (str): The natural language command describing the desired movement (e.g., "turn right 90 degrees" or "step forward 3 times").

    Returns:
    - bool: True if the movement command was successfully interpreted and executed, False otherwise.
    - str: Error message if the command could not be processed.
    """
    from module_llm import raw_complete_llm
    # Define the prompt with placeholders
    prompt = f"""
    You are TARS, an AI module responsible for interpreting movement commands. Your job is to:

    1. Determine the type of movement from the following options only:
    - stepForward
    - turnRight
    - turnLeft
    - poseaction
    - unposeaction
    2. Extract the number of steps or the angle of turn if applicable, where 180 degrees equals 2 steps (90 degrees = 1 step).
    3. Respond with a structured JSON output in the exact format:
    {{
        "movement": "{{
            "movement": "<MOVEMENT>",
            "times": <TIMES>
        }}
    }}

    Rules:
    - Always output a single JSON object with the fields "movement" and "times".
    - Do not output explanations, variations, or multiple commands.
    - If no steps or angle is specified, default "times" to 1.
    - Use precise logic for angles:
    - Convert 90 degrees = 1 step.
    - For angles greater than 90, calculate the number of steps (e.g., 180 degrees = 2 steps, 360 degrees = 4 steps).
    - Determine the turn direction (turnLeft or turnRight) based on the input.

    Examples:
    Input: "Hey TARS, walk forward 3 times"
    Output:
    {{
        "movement": "stepForward",
        "times": 3
    }}

    Input: "Hey TARS, do a 180-degree turn"
    Output:
    {{
        "movement": "turnLeft",
        "times": 2
    }}

    Input: "Hey TARS, turn right twice"
    Output:
    {{
        "movement": "turnRight",
        "times": 2
    }}

    Input: "Hey TARS, pose"
    Output:
    {{
        "movement": "poseaction",
        "times": 1
    }}

    Input: "Hey TARS, unpose"
    Output:
    {{
        "movement": "unposeaction",
        "times": 1
    }}

    Instructions:
    - Use only the specified movements (stepForward, turnRight, turnLeft, poseaction, unposeaction).
    - Ensure the JSON output is properly formatted and follows the example structure exactly.
    - Process the input as a single command and provide one-line JSON output.

    Input: "{user_input}"
    Output:
    """
    try:
        data = raw_complete_llm(prompt)

        import json
        # Parse the JSON response
        extracted_data = json.loads(data)

        # Extract movement and times
        movement = extracted_data.get("movement")
        times = extracted_data.get("times")

        print(f"[DEBUG] FunctionCalling: {data}")
        print(f"[DEBUG] Extracted values: {movement}, {times}")

        # Validate the extracted data
        if movement and times:
            if isinstance(movement, str) and isinstance(times, int):
                print("moving")
                execute_movement(movement, times)  # Call the movement function with validated values
                return True
            else:
                print("[ERROR] Invalid types: 'movement' must be str and 'times' must be int.")
                return False
        else:
            print("[ERROR] Missing 'movement' or 'times' in the response.")
            return False
    
    except Exception as e:
        #print(f"[DEBUG] Error in movement_llmcall: {e}")
        return f"Error processing the movement command: {e}"

def call_function(module_name, *args, **kwargs):
    #print(f"[DEBUG] Calling module: {module_name}")
    if module_name not in FUNCTION_REGISTRY:
        #print(f"[DEBUG] No function registered for module: {module_name}")
        return "Not a Function"
    func = FUNCTION_REGISTRY[module_name]
    try:
        # Check if the function requires arguments
        if func.__code__.co_argcount == 0:  # No arguments expected
            return func()
        else:  # Pass arguments if required
            return func(*args, **kwargs)
    except Exception as e:
        print(f"[DEBUG] Error while executing {module_name}: {e}")

def check_for_module(user_input):
    """
    Determines the appropriate module to handle the user's input and invokes it.
    """
    predicted_class, probability = predict_class(user_input)
    if not predicted_class:
        return "None"
    
    # Call the function associated with the predicted class
    return call_function(predicted_class, user_input)

def predict_class(user_input):
    """
    Which method to use for function calling NB (single LLM CALL) or LLM (Multiple LLM Calls)
    """
    if mode == 'NB':
        return predict_class_nb(user_input)
    else:
        return predict_class_llm(user_input)
    return

def predict_class_nb(user_input):
    """
    Predicts the class and its confidence score for a given user input.

    Parameters:
        user_input (str): The input text from the user.

    Returns:
        tuple: Predicted class and its probability score.
    """
    query_vector = tfidf_vectorizer.transform([user_input])
    predictions = nb_classifier.predict(query_vector)
    predicted_probabilities = nb_classifier.predict_proba(query_vector)

    predicted_class = predictions[0]
    max_probability = max(predicted_probabilities[0])
    # Return None if confidence is below threshold

    #print(f"TOOL: Using Tool {predicted_class} ({max_probability})")

    if max_probability < 0.75:
        return None, max_probability

    # Format the value as a percentage with 2 decimal places
    formatted_probability = "{:.2f}%".format(max_probability * 100)
    print(f"TOOL: Using Tool {predicted_class} ({formatted_probability})")
    generate_tts_audio("processing, processing, processing", CONFIG['TTS']['ttsoption'], CONFIG['TTS']['azure_api_key'], CONFIG['TTS']['azure_region'], CONFIG['TTS']['ttsurl'], CONFIG['TTS']['toggle_charvoice'], CONFIG['TTS']['tts_voice'])

    return predicted_class, max_probability

def predict_class_llm(user_input):
    from module_llm import raw_complete_llm
    import json


    prompt = f"""
    You are TARS, an AI module responsible for predicting the appropriate tool usage. Your tasks are:

    1. Identify the tool being referenced from the following list of options and their descriptions:
    {FUNCTION_REGISTRY}

    2. Extract the confidence level for the predicted tool usage, ensuring it is a valid percentage (0–100).

    3. Respond with a structured JSON output in the exact format:
    {{
        "functioncall": {{
            "tool": "<TOOL>",
            "confidence": <CONFIDENCE>
        }}
    }}

    Rules:
    - Always output a single JSON object with the fields "tool" and "confidence".
    - If no confidence is provided or cannot be inferred, set confidence to 50 by default.
    - Ensure the tool matches one of the listed options exactly.
    - Do not include any explanations or extra data in the output.

    Instructions:
    - Match the tool to the intent of the input based on its description and functionality.
    - Only use tools from the provided list.

    Input: "{user_input}"
    Output:
    """

    try:
        # Get the raw response from the LLM
        data = raw_complete_llm(prompt)

        # Parse the JSON response
        extracted_data = json.loads(data)

        # Access the "functioncall" object
        function_call = extracted_data.get("functioncall", {})
        predicted_class = function_call.get("tool")
        confidence = function_call.get("confidence")

        #print(f"[DEBUG] FunctionCalling: {data}")
        print(f"[DEBUG] Extracted values: tool={predicted_class}, confidence={confidence}")

        # Validate the extracted values
        if predicted_class not in FUNCTION_REGISTRY:
            print("[ERROR] Tool not recognized.")
            return None, 0.0

        if not isinstance(confidence, (int, float)):
            print("[INFO] Confidence value not provided or invalid. Defaulting to 50%.")
            confidence = 50.0

        if confidence < 0 or confidence > 100:
            print("[ERROR] Confidence value out of bounds. Setting to 50%.")
            confidence = 50.0

        # Normalize confidence to 0–1
        max_probability = confidence / 100.0

        if max_probability < 0.75:
            print(f"[INFO] Confidence too low ({max_probability:.2f}). Tool not used.")
            return None, max_probability

        # Announce the decision via TTS (optional)
        formatted_probability = f"{max_probability * 100:.2f}%"
        print(f"TOOL: Using Tool {predicted_class} ({formatted_probability})")
        generate_tts_audio("processing, processing, processing", CONFIG['TTS']['ttsoption'], CONFIG['TTS']['azure_api_key'], CONFIG['TTS']['azure_region'], CONFIG['TTS']['ttsurl'], CONFIG['TTS']['toggle_charvoice'], CONFIG['TTS']['tts_voice'])

        return predicted_class, max_probability

    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse LLM response: {e}")
        return None, 0.0
    except Exception as e:
        print(f"[ERROR] Unexpected error in predict_class: {e}")
        return None, 0.0
    
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
    {{
        "error": "Value not provided"
    }}
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

        import json
        # Parse the JSON response
        extracted_data = json.loads(data)

        # Access the "persona" object
        persona_data = extracted_data.get("persona", {})
        trait = persona_data.get("trait")
        value = persona_data.get("value")

        print(f"[DEBUG] FunctionCalling: {data}")
        print(f"[DEBUG] Extracted values: {trait}, {value}")

        # Validate the extracted data
        if trait and value:
            if isinstance(trait, str) and isinstance(value, int):
                print(f"INFO: Saving {trait} setting")
                update_character_setting(trait, value)
                return f"Updated {trait} setting to {value}"
            else:
                print("[ERROR] Invalid types")
                return False
        else:
            print("[ERROR] Missing in the response.")
            return False
    
    except Exception as e:
        #print(f"[DEBUG] Error in movement_llmcall: {e}")
        return f"Error processing the movement command: {e}"
 
# === Function Calling ===
FUNCTION_REGISTRY = {
    "Weather": search_google, 
    "News": search_google_news,
    "Move": movement_llmcall,
    "Vision": describe_camera_view,
    "Search": search_google,
    "SDmodule-Generate": generate_image,
    "Volume": handle_volume_command,
    "Persona": adjust_persona,
    "Home_Assistant": send_prompt_to_homeassistant
}
