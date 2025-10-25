import sys
import time
import threading
import queue

# Queue for handling message processing
message_queue = queue.Queue()
output_lock = threading.Lock()  # 🔹 Single lock for ALL stdout operations

def process_message_queue():
    """ Continuously process the message queue in order. """
    while True:
        item = message_queue.get()

        if item is None:  # Stop signal
            break

        # Handle cases where stream_text is missing (default to False)
        if isinstance(item, tuple) and len(item) == 2:
            message, stream_text = item
        else:
            message = item
            stream_text = False  # Default if not provided

        if stream_text:
            # 🔹 Run text streaming in a **separate thread** to avoid blocking
            threading.Thread(target=stream_text_blocking, args=(message,), daemon=True).start()
        else:
            with output_lock:  # 🔹 Lock only while printing
                print(message, flush=True)

        message_queue.task_done()

def stream_text_blocking(text, delay=0.03):
    """ Streams text character-by-character in a non-blocking manner. """
    
    def _stream():
        with output_lock:  # 🔹 Ensures no other process writes during streaming
            sys.stdout.flush()
            time.sleep(0.4)  # 🔹 Small delay to ensure terminal processes it this will not block the main program

            for char in text:
                sys.stdout.write(char)
                sys.stdout.flush()
                time.sleep(delay)  # 🔹 Slow typing effect

            sys.stdout.write("\n")  # 🔹 Ensure newline at the end
            sys.stdout.flush()

    # Run the streaming in a separate thread to prevent blocking
    threading.Thread(target=_stream, daemon=True).start()

def queue_message(message, stream=False):
    """
    Adds a message to the queue for ordered processing.

    Parameters:
    - message (str): The message content.
    - stream (bool, optional): If True, outputs character-by-character; otherwise, prints instantly.
                               Defaults to False if not provided.
    """
    if message and message.strip():
        message_queue.put((message.strip(), stream))  # 🔹 No lock needed here

def stop_message_processing():
    """ Stops the message processing thread safely. """
    message_queue.put(None)  # Stop signal
    message_thread.join()

# Start the message processing thread
message_thread = threading.Thread(target=process_message_queue, daemon=True)
message_thread.start()