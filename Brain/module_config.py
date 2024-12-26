import os
from dotenv import load_dotenv
load_dotenv()

def load_config():
    """
    Load configuration settings from 'config.ini' and return them as a dictionary.
    """
    import sys
    import configparser

    # Set the working directory and adjust the system path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)
    sys.path.insert(0, base_dir)
    sys.path.append(os.getcwd())

    # Parse the config file
    config = configparser.ConfigParser()
    config.read('config.ini')

    # Extract and return configuration variables
    return {
        "base_dir": base_dir,
        "ttsurl": config['TTS']['ttsurl'],
        "charvoice": config.getboolean('TTS', 'charvoice'),
        "ttsoption": config['TTS']['ttsoption'],
        "ttsclone": config['TTS']['ttsclone'],
        "voiceonly": config.getboolean('TTS', 'voiceonly'),
        "emotions": config.getboolean('EMOTION', 'enabled'),
        "emotion_model": config['EMOTION']['emotion_model'],
        "storepath": os.path.join(os.getcwd(), config['EMOTION']['storepath']),
        "llm_backend": config['LLM']['backend'],
        "base_url": config['LLM']['base_url'],
        "api_key": get_api_key(config['LLM']['backend']),
        "openai_model": config['LLM']['openai_model'],
        "contextsize": config.getint('LLM', 'contextsize'),
        "max_tokens": config.getint('LLM', 'max_tokens'),
        "temperature": config.getfloat('LLM', 'temperature'),
        "top_p": config.getfloat('LLM', 'top_p'),
        "seed_llm": config.getint('LLM', 'seed'),
        "systemprompt": config['LLM']['systemprompt'],
        "instructionprompt": config['LLM']['instructionprompt'],
        "charactercard": config['CHAR']['charactercard'],
        "user_name": config['CHAR']['user_name'],
        "user_details": config['CHAR']['user_details'],
        "TOKEN": config['DISCORD']['TOKEN'],
        "channel_id": config['DISCORD']['channel_id'],
        "discordenabled": config['DISCORD']['enabled'],
    }

def get_api_key(llm_backend):
    """
    Retrieves the API key for the specified LLM backend.
    """
    # Map the backend to the corresponding environment variable
    backend_to_env_var = {
        "openai": "OPENAI_API_KEY",
        "ooba": "OOBA_API_KEY",
        "tabby": "TABBY_API_KEY"
    }

    # Check if the backend is supported
    if llm_backend not in backend_to_env_var:
        raise ValueError(f"Unsupported LLM backend: {llm_backend}")

    # Fetch the API key from the environment
    api_key = os.getenv(backend_to_env_var[llm_backend])
    if not api_key:
        raise ValueError(f"API key not found for LLM backend: {llm_backend}")
    
    return api_key