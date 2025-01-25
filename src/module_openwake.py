import tflite_runtime.interpreter as tflite
import numpy as np
import sounddevice as sd
import queue
import librosa
import time
import warnings
import numpy as np
import os

# Suppress numpy warnings about subnormal values
warnings.filterwarnings("ignore", message="The value of the smallest subnormal for .* type is zero.")

# Parameters
SAMPLE_RATE = 16000  # Hz
FRAME_DURATION = 1  # seconds
FRAME_SIZE = SAMPLE_RATE * FRAME_DURATION
NUM_FEATURES = 96  # Number of MFCC features expected by the model
WAKE_WORD_THRESHOLD = 0.75  # Confidence threshold for detection

# Audio queue for real-time processing
audio_queue = queue.Queue()

def audio_callback(indata, frames, time, status):
    """Callback function to store audio data into the queue."""
    if status:
        print(f"Audio status: {status}")
    audio_queue.put(indata.copy())

def preprocess_audio(audio_data, sample_rate=SAMPLE_RATE, num_features=NUM_FEATURES):
    """Preprocess raw audio data into MFCC features."""
    # Compute MFCC features
    mfcc = librosa.feature.mfcc(
        y=audio_data,
        sr=sample_rate,
        n_mfcc=num_features
    )
    # Transpose to match [sequence_length, num_features]
    return mfcc.T

def load_model(model_path):
    """Load the TFLite model."""
    interpreter = tflite.Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    return interpreter

def process_audio(interpreter, audio_data):
    """Process audio data using the TFLite model."""
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    input_shape = input_details[0]['shape']  # Expected shape: [1, sequence_length, num_features]

    # Preprocess audio into MFCC features
    audio_features = preprocess_audio(audio_data)

    # Ensure the shape matches the model's expected input
    sequence_length = input_shape[1]
    audio_features = audio_features[:sequence_length, :]  # Trim to match sequence length
    if audio_features.shape[0] < sequence_length:
        # Pad if the sequence is shorter than expected
        padding = np.zeros((sequence_length - audio_features.shape[0], NUM_FEATURES))
        audio_features = np.vstack((audio_features, padding))

    # Add batch dimension
    input_data = np.expand_dims(audio_features, axis=0)

    # Run inference
    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()

    # Get results
    output_data = interpreter.get_tensor(output_details[0]['index'])
    return output_data

def start_openwakeword():
    
    #play_beep(400, 0.1, 44100, 0.6) #sleeping tone

    relative_path = os.path.join("stt", "openwake", "hey_tars.tflite")
    model_path = os.path.join(os.getcwd(), relative_path)
    print("Loading model...")
    interpreter = load_model(model_path)

    # Start microphone stream
    print("Starting microphone stream...")
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        callback=audio_callback,
        blocksize=FRAME_SIZE,
    ):
        #play_beep(400, 0.1, 44100, 0.6) #sleeping tone
        print(f"TARS: Sleeping...")
        #time.sleep(1)  # Avoid immediate re-triggering
        while True:
            try:
                # Get audio data from queue
                audio_data = audio_queue.get()
                audio_data = audio_data.flatten()

                # Process audio and check for wake word
                output_data = process_audio(interpreter, audio_data)
                confidence = output_data[0][0]  # Adjust based on model's output format

                if confidence > WAKE_WORD_THRESHOLD:
                    #play_beep(1200, 0.1, 44100, 0.8) #wake tone
                    print(f"Wake word detected! (Confidence: {confidence:.2f})")
                    #play_beep(1200, 0.1, 44100, 0.8) #wake tone
                    time.sleep(1)  # Avoid immediate re-triggering
                    return True
            

            except KeyboardInterrupt:
                print("Exiting...")
                break
            except Exception as e:
                print(f"Error: {e}")
