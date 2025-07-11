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
def execute_movement(movement, times):
    """
    Executes the specified movement in a separate thread.
    """
    def movement_task():
        queue_message(f"[DEBUG] Thread started for movement: {movement} x {times}")
        if (CONFIG["SERVO"]["MOVEMENT_VERSION"] == "V2"):
            from modules.module_btcontroller_v2 import turnRight, turnLeft, poseaction, unposeaction, stepForward, stepBackward
        else:
            from modules.module_btcontroller import turnRight, turnLeft, poseaction, unposeaction, stepForward

        action_map = {
            "turnRight": turnRight,
            "turnLeft": turnLeft,
            "poseaction": poseaction,
            "unposeaction": unposeaction,
            "stepForward": stepForward,
            "stepBackward": stepBackward
        }
        
        try:
            action_function = action_map.get(movement)
            if callable(action_function):
                for i in range(int(times)):
                    queue_message(f"[DEBUG] Executing {movement}, iteration {i + 1}/{times}")
                    action_function()  # Blocking for this thread
            else:
                queue_message(f"[ERROR] Movement '{movement}' not found in action_map.")
        except Exception as e:
            queue_message(f"[ERROR] Unexpected error while executing movement: {e}")
        finally:
            queue_message(f"[DEBUG] Thread completed for movement: {movement} x {times}")

    # Start the thread
    thread = threading.Thread(target=movement_task, daemon=True)
    thread.start()
    return thread  # Return the thread object if needed

def movement_llmcall(user_input):

    if CONFIG['CONTROLS']['voicemovement'] != "True":
        return
    
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
    - stepBackward
    2. Extract the number of steps or the angle of turn if applicable, where 180 degrees equals 2 steps (90 degrees = 1 step).
    3. Respond with a structured JSON output in the exact format:
    {{
        "movement": "<MOVEMENT>",
        "times": <TIMES>
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

    Input: "Can you please move backwards 3 times"
    Output:
    {{ 
        "movment": "stepBackward",
        "times": 3
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

    Input: "Hey Tars, can you take 2 steps backwards"
    Output:
    {{
        "movment": "stepBackward",
        "times": 2
    }}

    Input: "Hey Tars, can you please move 2 steps forward"
    Output:
    {{ 
        "movment": "stepForward"
        "times": 2
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

        queue_message(f"[DEBUG] FunctionCalling: {data}")
        queue_message(f"[DEBUG] Extracted values: {movement}, {times}")

        # Validate the extracted data
        if movement and times:
            if isinstance(movement, str) and isinstance(times, int):
                queue_message("moving")
                execute_movement(movement, times)  # Call the movement function with validated values
                return True
            else:
                queue_message("[ERROR] Invalid types: 'movement' must be str and 'times' must be int.")
                return False
        else:
            queue_message("[ERROR] Missing 'movement' or 'times' in the response.")
            return False
    
    except Exception as e:
        #queue_message(f"[DEBUG] Error in movement_llmcall: {e}")
        return f"Error processing the movement command: {e}"

def call_function(module_name, *args, **kwargs):
    #queue_message(f"[DEBUG] Calling module: {module_name}")
    if module_name not in FUNCTION_REGISTRY:
        #queue_message(f"[DEBUG] No function registered for module: {module_name}")
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
    if CONFIG['LLM']['functioncalling'] == 'NB':
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

    #queue_message(f"TOOL: Using Tool {predicted_class} ({max_probability})")

    if max_probability < 0.75:
        return None, max_probability

    # Format the value as a percentage with 2 decimal places
    formatted_probability = "{:.2f}%".format(max_probability * 100)
    queue_message(f"TOOL: Using Tool {predicted_class} ({formatted_probability})")
    generate_tts_audio("processing, processing, processing", CONFIG['TTS']['ttsoption'], CONFIG['TTS']['azure_api_key'], CONFIG['TTS']['azure_region'], CONFIG['TTS']['ttsurl'], CONFIG['TTS']['toggle_charvoice'], CONFIG['TTS']['tts_voice'])

    return predicted_class, max_probability

def predict_class_llm(user_input):
    from module_llm import raw_complete_llm

    prompt = f"""
    You are an AI module tasked with predicting the appropriate tool usage based on the user's message, with a high level of accuracy and understanding of the intent behind their words. The available tools and their descriptions are as follows: {FUNCTION_REGISTRY}.

    Your tasks are:

    1. Determine if a tool should be used based on the user's message or if the user is simply chatting. If no tool is needed, the response should default to "chat".
    
    2. Identify the specific tool being referenced from the available list of tools and their descriptions. It is crucial to recognize when the user is just having a casual conversation and does not require any tool. In such cases, use "chat" as the tool.

    3. Extract the confidence level for the predicted tool usage based on the user's message. Ensure the confidence is a valid percentage (0–100).

    4. Respond with a structured JSON output in the following format:
    {{
        "functioncall": {{
            "tool": "<TOOL>",
            "confidence": <CONFIDENCE>
        }}
    }}

    Rules:
    - Always output a single JSON object containing "tool" and "confidence".
    - If no confidence is provided, or if the tool is not explicitly referenced, set the confidence to 0.
    - If no tool is needed or the user is just chatting, set the "tool" to "chat" with a confidence of 0.
    - Ensure that the tool name exactly matches one from the available options, or default to "chat" if no tool is needed.
    - Do not include any explanations, variations, or additional data in the output.

    Instructions:
    - Match the appropriate tool to the intent of the user's input based on the provided descriptions.
    - Consider context carefully—if the input is a simple greeting or chat, do not suggest any tools.
    - Only use tools from the provided list and avoid making assumptions about the user's intent.

    Input: "{user_input}"
    Output:
    """

    try:
        # Get the raw response from the LLM
        data = raw_complete_llm(prompt)
        #queue_message(f"[DEBUG] Raw LLM response: {repr(data)}")  # Show exact response

        # Strip out the markdown block (```) from the raw response
        data = re.sub(r'```json\n|\n```', '', data).strip()

        # Parse the response
        predicted_class = None
        confidence = None

        # Try JSON parsing first
        try:
            parsed_data = json.loads(data)  # Strip whitespace/newlines
            #queue_message(f"[DEBUG] Parsed JSON: {parsed_data}")
            function_call = parsed_data.get("functioncall")
            if function_call and "tool" in function_call and "confidence" in function_call:
                predicted_class = function_call["tool"]
                confidence = function_call["confidence"]
            else:
                #queue_message("[ERROR] Invalid JSON structure: missing required fields.")
                return None, 0.0
        except json.JSONDecodeError as e:
            #queue_message(f"[DEBUG] JSON parsing failed: {str(e)}")
            # Fallback to string parsing
            match = re.search(r'Tool:\s*(\w+),\s*Confidence:\s*(\d+)%', data)
            if match:
                predicted_class = match.group(1)
                confidence = int(match.group(2))
            else:
                #queue_message("[ERROR] Failed to extract tool and confidence from response.")
                return None, 0.0

        # Validate extracted values
        if not predicted_class or not isinstance(confidence, (int, float)):
            #queue_message("[ERROR] Extracted tool or confidence is invalid.")
            return None, 0.0

        #queue_message(f"[DEBUG] Extracted values: tool={predicted_class}, confidence={confidence}")

        if predicted_class not in FUNCTION_REGISTRY:
            #queue_message("[ERROR] Tool not recognized.")
            return None, 0.0

        if confidence < 0 or confidence > 100:
            #queue_message("[ERROR] Confidence out of bounds. Setting to 50%.")
            confidence = 50.0

        # Normalize confidence to 0–1
        max_probability = confidence / 100.0

        if max_probability < 0.75:
            #queue_message(f"[INFO] Confidence too low ({max_probability:.2f}). Tool not used.")
            return None, max_probability

        formatted_probability = f"{max_probability * 100:.2f}%"
        queue_message(f"TOOL: Using Tool {predicted_class} ({formatted_probability})")
        generate_tts_audio("processing, processing, processing", CONFIG['TTS']['ttsoption'], CONFIG['TTS']['azure_api_key'], CONFIG['TTS']['azure_region'], CONFIG['TTS']['ttsurl'], CONFIG['TTS']['toggle_charvoice'], CONFIG['TTS']['tts_voice'])

        return predicted_class, max_probability

    except Exception as e:
        queue_message(f"[ERROR] Unexpected error: {str(e)}")
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

        #queue_message(f"[DEBUG] FunctionCalling: {data}")
        #queue_message(f"[DEBUG] Extracted values: {trait}, {value}")

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
    "Move": movement_llmcall,
    "Vision": describe_camera_view,
    "Search": search_google,
    "SDmodule-Generate": generate_image,
    "Volume": handle_volume_command,
    "Persona": adjust_persona,
    "Home_Assistant": send_prompt_to_homeassistant
}
