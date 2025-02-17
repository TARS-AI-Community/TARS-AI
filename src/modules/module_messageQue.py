import sys
import time
import threading
import queue

# Queue for handling message processing
message_queue = queue.Queue()
print_lock = threading.Lock()

def process_message_queue():
    """ Continuously process the message queue in order. """
    while True:
        message, stream_text = message_queue.get()

        if message is None:  # Stop signal
            break

        with print_lock:
            if stream_text:
                stream_text_blocking(message)
            else:
                print(message, flush=True)

        message_queue.task_done()

def stream_text_blocking(text, delay=0.03):
    """
    Streams text character by character in a **blocking** way.

    Parameters:
    - text (str): The text to stream.
    - delay (float): Delay between characters.
    """
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)

    sys.stdout.write("\n")
    sys.stdout.flush()

# Start the message processing thread
message_thread = threading.Thread(target=process_message_queue, daemon=True)
message_thread.start()

def queue_message(message, stream_text=False):
    """
    Adds a message to the queue for ordered processing.

    Parameters:
    - message (str): The message content.
    - stream_text (bool): If True, outputs character-by-character; otherwise, prints instantly.
    """
    if message and message.strip():
        message_queue.put((message.strip(), stream_text))

def stop_message_processing():
    """ Stops the message processing thread safely. """
    message_queue.put((None, False))  # Stop signal
    message_thread.join()
