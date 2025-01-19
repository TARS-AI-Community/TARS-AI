"""
module_engine.py

Core module for TARS-AI responsible for:
- Predicting user intents and determining required modules.
- Executing tool-specific functions like web searches and vision analysis.

This is achieved using a pre-trained Naive Bayes classifier and TF-IDF vectorizer.
"""

# === Standard Libraries ===
import os
import joblib
from datetime import datetime

# === Custom Modules ===
from module_websearch import search_google, search_google_news
from module_vision import describe_camera_view
from module_config import load_config
from module_stablediffusion import get_base64_encoded_image_generate

# Load configuration
config = load_config()

# === Constants ===
MODEL_FILENAME = 'engine/pickles/naive_bayes_model.pkl'
VECTORIZER_FILENAME = 'engine/pickles/module_engine_model.pkl'

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
def execute_movement(command_str):
    print(f"[DEBUG] Executing movement: {command_str}")
    from module_btcontroller import turnRight, turnLeft, poseaction, unposeaction, stepForward
    action_map = {
        "turnRight": turnRight,
        "turnLeft": turnLeft,
        "poseaction": poseaction,
        "unposeaction": unposeaction,
        "stepForward": stepForward,
    }
    try:
        action, count = command_str.split(", ")
        count = int(count)
        action_function = action_map.get(action)
        if callable(action_function):
            for _ in range(count):  # Only execute the specified number of times
                print(f"[DEBUG] Calling {action} function.")
                action_function()
        else:
            print(f"[DEBUG] Action {action} not found in action_map.")
    except ValueError:
        print("[DEBUG] Invalid command format.")
    except Exception as e:
        print(f"[DEBUG] Unexpected error: {e}")

def movement_llmcall(user_input):
    from module_llm import raw_complete_llm
    print(f"[DEBUG] Processing user input: {user_input}")
    """
    Processes a movement command using an LLM and returns the interpreted action.
    
    Parameters:
        user_input (str): The user's movement command (e.g., "Hey TARS, walk forward 3 times").
    
    Returns:
        str: The structured output describing the action.
    """
    # Define the prompt with placeholders
    prompt = f"""
You are TARS, an AI module responsible for interpreting movement commands. Your job is to:
1. Determine the **type of movement** from the following options only:
   - stepForward
   - turnRight
   - turnLeft
   - poseaction
   - unposeaction
2. Extract the **number of steps** or the **angle of turn** if applicable, 180 degrees is equal to 4 turns.
3. Respond with a structured output in the exact format: `MOVEMENT, TIMES`.

### Movement Commands:
- "forward [N] times": Output as `stepForward, N`.
- "turn left [N] times": Output as `turnLeft, N`.
- "turn right [N] times": Output as `turnRight, N`.
- "do a [X]-degree turn": Convert X degrees into steps (1 step = 90 degrees) and output as `turnLeft, N` or `turnRight, N` based on the direction.
- "pose": Output as `poseaction, 1`.
- "unpose": Output as `unposeaction, 1`.

### Examples:
1. User Input: "Hey TARS, walk forward 3 times"
   Output: `stepForward, 3`

2. User Input: "Hey TARS, do a 180-degree turn"
   Output: `turnLeft, 2`

3. User Input: "Hey TARS, turn right twice"
   Output: `turnRight, 2`

4. User Input: "Hey TARS, pose"
   Output: `poseaction, 1`

5. User Input: "Hey TARS, unpose"
   Output: `unposeaction, 1`

### Instructions:
- Only use the movements `stepForward`, `turnRight`, `turnLeft`, `poseaction`, and `unposeaction`.
- Always include the **movement type** and the **number of steps** or `1` if not applicable.
- If the user specifies an angle (e.g., "180-degree turn"), calculate the steps (1 step = 90 degrees) and output the corresponding turn movement.
- If no number of steps or angle is provided, default to `1`.
- Format the response strictly as: `MOVEMENT, TIMES`.

Only output one line that is the most likly, do not combine multiple movements. Now process the following input:
"{user_input}"
    """
    try:
        data = raw_complete_llm(prompt)
        print(f"[DEBUG] LLM Response: {data}")
        if data:
            execute_movement(data)  # Ensure single execution
        return data
    except Exception as e:
        #print(f"[DEBUG] Error in movement_llmcall: {e}")
        return f"Error processing the movement command: {e}"



def call_function(module_name, *args, **kwargs):
    print(f"[DEBUG] Calling module: {module_name}")
    if module_name not in FUNCTION_REGISTRY:
        #print(f"[DEBUG] No function registered for module: {module_name}")
        return
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
        return ""
    
    # Call the function associated with the predicted class
    result = call_function(predicted_class, user_input)

    if result:
        return result

    # Default response if no action is taken
    return

def predict_class(user_input):
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

    print(f"TOOL: Using Tool {predicted_class} ({max_probability})")

    if max_probability < 0.75:
        return None, max_probability

    # Format the value as a percentage with 2 decimal places
    formatted_probability = "{:.2f}%".format(max_probability * 100)
    print(f"TOOL: Using Tool {predicted_class} ({formatted_probability})")
    return predicted_class, max_probability

# === Function Calling ===
FUNCTION_REGISTRY = {
    "Weather": search_google, 
    "News": search_google_news,
    "Move": movement_llmcall,
    "Vision": describe_camera_view,
    "Search": search_google,
    "SDmodule-Generate": get_base64_encoded_image_generate
}
