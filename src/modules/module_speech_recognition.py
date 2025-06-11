import json
import speech_recognition as sr
from modules.module_messageQue import queue_message
from modules.module_config import load_config

CONFIG = load_config().get("STT", {})

def module_speech_recognition(utterance_callback=None):
    """
    Capture from the mic using speech_recognition (Google Web API),
    apply a small retry loop on UnknownValueError, then fire the callback.
    Returns {'text': ...} or None.
    """
    recognizer = sr.Recognizer()
    mic_kwargs = {}
    phrase_time_limit = float(CONFIG.get("phrase_time_limit", 12))
    max_retries      = int(CONFIG.get("max_retries", 3))

    # optionally override sample_rate
    if "sample_rate" in CONFIG:
        mic_kwargs["sample_rate"] = int(CONFIG["sample_rate"])

    try:
        with sr.Microphone(**mic_kwargs) as source:
            queue_message("INFO: Adjusting for ambient noise…")
            recognizer.adjust_for_ambient_noise(source, duration=1.5)
            queue_message("INFO: Listening…")
            audio = recognizer.listen(source, phrase_time_limit=phrase_time_limit)

        # retry loop
        retries = 0
        while retries < max_retries:
            try:
                queue_message("INFO: Recognizing speech…")
                text = recognizer.recognize_google(audio).strip()
                queue_message(f"INFO: Transcribed: {text}")
                result = {"text": text}
                if utterance_callback and text:
                    utterance_callback(json.dumps(result))
                return result

            except sr.UnknownValueError:
                retries += 1
                queue_message("WARNING: Could not understand, retrying…")

            except sr.RequestError as e:
                queue_message(f"ERROR: SR service failure: {e}")
                return None

        queue_message("WARNING: Max retries reached without understanding.")
    except Exception as e:
        queue_message(f"ERROR: speech_recognition failed: {e}")

    return None
