#needed imports
import os
import sys
import threading
import requests
from datetime import datetime
import concurrent.futures

#custom imports
from module_engineTrainer import train_text_classifier
from module_btcontroller import *
from module_stt import *
from module_memory import *
from module_engine import *
from module_tts import *
from module_imagesummary import *
from module_config import load_config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Set the working directory to the base directory
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)
sys.path.append(os.getcwd())

stop_event = threading.Event()
executor = concurrent.futures.ProcessPoolExecutor(max_workers=4)

def initial_msg():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Script running from: {BASE_DIR}")
    #print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] DEBUG: initial_msg() called")
    

    read_character_content()
    train_text_classifier()

    #Load Char card
    measure_background_noise()

    # Load the configuration
    config = load_config()
    if config['ttsoption'] == 'xttsv2':
        try:
            url = f"{ttsurl}/set_tts_settings"
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }

            payload = {
                "stream_chunk_size": 100,
                "temperature": 0.7,
                "speed": 1.1,
                "length_penalty": 1.0,
                "repetition_penalty": 1.2,
                "top_p": 0.9,
                "top_k": 40,
                "enable_text_splitting": True
            }
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: TTS Settings updated successfully.")
            else:
                print(f'Failed to update settings. Status code: {response.status_code}')
                print('Response:', response.text)
        except Exception as e:
            print(f"Error: {e}")

#Trigger once
initial_msg()

#MAIN
if __name__ == "__main__":
    # Set the STT message callback
    from module_main import handle_stt_message, wake_word_tts, start_stt_thread, start_bt_controller_thread
    set_message_callback(handle_stt_message)
    set_wakewordtts_callback(wake_word_tts)

    # Start threads
    stt_thread = threading.Thread(target=start_stt_thread, name="STTThread", daemon=True)
    bt_controller_thread = threading.Thread(target=start_bt_controller_thread, name="BTControllerThread", daemon=True)
    
    stt_thread.start()
    bt_controller_thread.start()
    
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Main program running. Press Ctrl+C to stop.")
        while True:
            pass  # Keep the main program running
    except KeyboardInterrupt:
        print("\nStopping all threads and shutting down executor...")
        stop_event.set()  # Signal threads to stop

        # Shut down the executor
        executor.shutdown(wait=True)

        # Join threads
        stt_thread.join()
        bt_controller_thread.join()
        print("All threads and executor stopped gracefully.")