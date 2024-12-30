import os
import subprocess
import sys
import signal
import subprocess
import json

def is_tool_installed(tool_name):
    """Check if a tool is installed."""
    return subprocess.call(["which", tool_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

def install_ollama():
    """Install ollama on Raspberry Pi."""
    try:
        print("Installing ollama...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "ollama-cli"])
    except subprocess.CalledProcessError as e:
        print(f"Error installing ollama: {e}")
        sys.exit(1)

def pull_model(model_name):
    """Pull a model using ollama."""
    try:
        print(f"Pulling model {model_name}...")
        subprocess.check_call(["ollama", "pull", model_name])
    except subprocess.CalledProcessError as e:
        print(f"Error pulling model {model_name}: {e}")
        sys.exit(1)

def run_ollama():
    """Run ollama."""
    try:
        print("Running ollama...")
        process = subprocess.Popen(["ollama"])
        return process
    except FileNotFoundError:
        print("Failed to run ollama. Please ensure it is installed correctly.")
        sys.exit(1)

def close_ollama(process):
    """Close the ollama process."""
    try:
        print("Closing ollama...")
        os.kill(process.pid, signal.SIGTERM)
    except Exception as e:
        print(f"Error closing ollama: {e}")

def setup_and_run_ollama():
    """Setup and run ollama."""
    if not is_tool_installed("ollama"):
        install_ollama()
    
    pull_model("qwen2.5:3b")
    
    process = run_ollama()
    
    try:
        input("Press Enter to exit and close ollama...\n")
    finally:
        close_ollama(process)



def chat_with_ollama(prompt):
    """
    Send a prompt to the locally running Ollama instance and return the response.
    
    Args:
        prompt (str): The user's input prompt for Ollama.
    
    Returns:
        str: Ollama's response.
    """
    try:
        # Run ollama with the `chat` command and input prompt
        result = subprocess.run(
            ["ollama", "chat", "--json"],  # Use --json for structured responses
            input=prompt.encode(),        # Provide the prompt as input
            stdout=subprocess.PIPE,       # Capture the standard output
            stderr=subprocess.PIPE,       # Capture errors
            check=True                    # Raise exceptions on errors
        )
        # Decode the JSON output
        response_data = json.loads(result.stdout.decode())
        return response_data.get("response", "No response received")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while interacting with Ollama: {e.stderr.decode()}")
        return None

if __name__ == "__main__":
    setup_and_run_ollama()
    print("Chat with Ollama. Type 'exit' to quit.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            print("Goodbye!")
            break
        
        response = chat_with_ollama(user_input)
        if response:
            print(f"Ollama: {response}")
        else:
            print("Failed to get a response from Ollama.")
