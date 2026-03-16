import sys
import os
import time
import logging
import logging.handlers
import threading
import queue
from collections import deque

# Queue for handling message processing
message_queue = queue.Queue()
output_lock = threading.Lock()  # 🔹 Single lock for ALL stdout operations

# Rolling log buffer for the WebUI console
_log_buffer = deque(maxlen=200)
_log_lock = threading.Lock()
_log_counter = 0

# File-based logging with rotation
_file_logger = None

def _init_file_logger():
    global _file_logger
    if _file_logger is not None:
        return
    try:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, 'tars-ai.log')
        _file_logger = logging.getLogger('tars_file')
        _file_logger.setLevel(logging.INFO)
        handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=5_000_000, backupCount=3, encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        _file_logger.addHandler(handler)
        _file_logger.propagate = False
    except Exception:
        _file_logger = None

_init_file_logger()

def get_recent_logs(since=0):
    """Return log lines newer than since and the current counter."""
    with _log_lock:
        lines = [msg for idx, msg in _log_buffer if idx > since]
        head = _log_buffer[-1][0] if _log_buffer else since
    return lines, head

def _buffer_log(message):
    global _log_counter
    with _log_lock:
        _log_counter += 1
        _log_buffer.append((_log_counter, message))
    if _file_logger is not None:
        try:
            _file_logger.info(message)
        except Exception:
            pass

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

        _buffer_log(message)

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
    if not isinstance(message, str):
        message = str(message)
    if message and message.strip():
        message_queue.put((message.strip(), stream))  # 🔹 No lock needed here

def stop_message_processing():
    """ Stops the message processing thread safely. """
    message_queue.put(None)  # Stop signal
    message_thread.join()

# Start the message processing thread
message_thread = threading.Thread(target=process_message_queue, daemon=True)
message_thread.start()
