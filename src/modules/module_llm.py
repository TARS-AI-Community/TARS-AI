"""
module_llm.py

LLM module for the TARS-AI application.

Provides:
- Integration with LLM backends (OpenAI, DeepInfra, Ooba, Tabby).
- Functions for text generation, emotion detection, and memory management.
"""

# === Standard Libraries ===
import requests
import threading
import concurrent.futures
from modules.module_config import load_config
from modules.module_prompt import build_prompt

# === Constants and Globals ===
CONFIG = load_config()
character_manager = None
memory_manager = None

# Threading and Executor
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# === Core Functions ===

def get_completion(user_prompt, istext=True):
    """
    Generate a completion using the configured LLM backend.

    Parameters:
    - user_prompt (str): The user's input prompt.
    - istext (bool): Whether the prompt is a standard text query.

    Returns:
    - str: The generated completion.
    """
    if memory_manager is None or character_manager is None:
        raise ValueError("MemoryManager and CharacterManager must be initialized before generating completions.")

    prompt = build_prompt(user_prompt, character_manager, memory_manager, CONFIG)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
    }
    llm_backend = CONFIG['LLM']['llm_backend']
    url, data = _prepare_request_data(llm_backend, prompt)

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        bot_reply = _extract_text(response.json(), istext)
        
        llm_process(user_prompt, bot_reply)
        return bot_reply
    
    except requests.RequestException as e:
        print(f"ERROR: LLM request failed: {e}")
        return None

def _prepare_request_data(llm_backend, prompt):
    """
    Prepare the request URL and data for the LLM backend.

    Parameters:
    - llm_backend (str): The LLM backend name.
    - prompt (str): The formatted prompt.

    Returns:
    - tuple: URL and data payload for the request.
    """
    if llm_backend == "openai":
        url = f"{CONFIG['LLM']['base_url']}/v1/chat/completions"
        data = {
            "model": CONFIG['LLM']['openai_model'],
            "messages": [
                {"role": "system", "content": CONFIG['LLM']['systemprompt']},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": CONFIG['LLM']['max_tokens'],
            "temperature": CONFIG['LLM']['temperature'],
            "top_p": CONFIG['LLM']['top_p']
        }
    elif llm_backend == "deepinfra":
        url = f"{CONFIG['LLM']['base_url']}/v1/openai/chat/completions"
        data = {
            "model": CONFIG['LLM']['openai_model'],
            "messages": [
                {"role": "system", "content": CONFIG['LLM']['systemprompt']},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": CONFIG['LLM']['max_tokens'],
            "temperature": CONFIG['LLM']['temperature'],
            "top_p": CONFIG['LLM']['top_p']
        }
    elif llm_backend in ["ooba", "tabby"]:
        url = f"{CONFIG['LLM']['base_url']}/v1/completions"
        data = {
            "prompt": prompt,
            "max_tokens": CONFIG['LLM']['max_tokens'],
            "temperature": CONFIG['LLM']['temperature'],
            "top_p": CONFIG['LLM']['top_p']
        }
        if llm_backend == "ooba":
            data["seed"] = CONFIG['LLM']['seed']
    else:
        raise ValueError(f"Unsupported LLM backend: {llm_backend}")

    return url, data

def _extract_text(response_json, istext):
    """
    Extract the generated text from the LLM response.

    Parameters:
    - response_json (dict): The JSON response from the LLM backend.
    - istext (bool): Whether the response should be treated as text.

    Returns:
    - str: Extracted text content.
    """
    try:
        llm_backend = CONFIG['LLM']['llm_backend']
        if 'choices' in response_json:
            # Both openai and deepinfra return the message in a similar format.
            return (
                response_json['choices'][0]['message']['content']
                if llm_backend in ["openai", "deepinfra"]
                else response_json['choices'][0]['text']
            ).strip()
        else:
            raise KeyError("Invalid response format: 'choices' key not found.")
    except (KeyError, IndexError, TypeError) as error:
        return f"Text extraction failed: {str(error)}"

def process_completion(prompt):
    """
    Generate a response for the given prompt using the LLM backend.

    Parameters:
    - prompt (str): The input prompt.

    Returns:
    - str: The generated response.
    """
    future = executor.submit(get_completion, prompt, istext=True)
    return future.result()

# === Emotion Detection ===

def detect_emotion(text):
    """
    Detect the emotion of the given text.

    Parameters:
    - text (str): The text to analyze.

    Returns:
    - str: The detected emotion.
    """
    if CONFIG['EMOTION']['enabled']:
        from transformers import pipeline
        classifier = pipeline("text-classification", model="SamLowe/roberta-base-go_emotions", top_k=None)
        model_outputs = classifier(text)
        return max(model_outputs[0], key=lambda x: x['score'])['label']
    return None

# === Memory Integration ===

def llm_process(user_input, bot_response):
    global memory_manager
    """
    Process user input and bot response, integrating with memory.

    Parameters:
    - user_input (str): The user's input.
    - bot_response (str): The bot's response.

    Returns:
    - str: The processed bot response.
    """
    if memory_manager:
        threading.Thread(target=memory_manager.write_longterm_memory, args=(user_input, bot_response)).start()
    
    if CONFIG['EMOTION']['enabled']:
        emotionvalue = threading.Thread(target=detect_emotion, args=(bot_response,)).start()
        #do something with emotionvalue (IE SAD, ANGRY)
    
    return bot_response

def raw_complete_llm(user_prompt, istext=True):
    """
    Generate a completion using the configured LLM backend.

    Parameters:
    - user_prompt (str): The user's input prompt.
    - istext (bool): Whether the prompt is a standard text query.

    Returns:
    - str: The generated completion.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG['LLM']['api_key']}"
    }
    llm_backend = CONFIG['LLM']['llm_backend']
    url, data = _prepare_request_data(llm_backend, user_prompt)

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        bot_reply = _extract_text(response.json(), istext)
        return bot_reply
    
    except requests.RequestException as e:
        print(f"ERROR: LLM request failed: {e}")
        return None

# === Initialization ===
def initialize_manager_llm(mem_manager, char_manager):
    """
    Pass in the shared instances for MemoryManager, CharacterManager, and STTManager.
    
    Parameters:
    - mem_manager: The MemoryManager instance from app.py.
    - char_manager: The CharacterManager instance from app.py.
    """
    global memory_manager, character_manager
    memory_manager = mem_manager
    character_manager = char_manager