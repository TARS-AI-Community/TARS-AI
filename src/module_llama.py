#pip install llama-cpp-python
#pip install huggingface_hub

import os
from huggingface_hub import snapshot_download
import llama_cpp

# Define model parameters
MODEL_NAME = "Qwen/Qwen2.5-3B"
MODEL_PATH = f"src/llm/{MODEL_NAME}/qwen2.5-3b-instruct-q4_0.gguf"
MODEL_THREADS = 4  # Adjust based on your Raspberry Pi's capabilities

# Ensure the models directory exists
os.makedirs("models", exist_ok=True)

# Check if the model file exists
if not os.path.isfile(MODEL_PATH):
    print(f"Model not found at {MODEL_PATH}. Downloading from Hugging Face...")
    # Download the model repository
    snapshot_download(repo_id=MODEL_NAME, local_dir=f"src/llm/{MODEL_NAME}", local_dir_use_symlinks=False)
    print("Download complete.")

# Initialize the model
llm = llama_cpp.Llama(model_path=MODEL_PATH, n_threads=MODEL_THREADS)

# Function to generate a response
def generate_response(prompt):
    response = llm(prompt, max_tokens=100, stop=["\n"])
    return response["choices"][0]["text"].strip()

# Main loop for user interaction
if __name__ == "__main__":
    print("Qwen2.5-3B Model is ready. Type 'exit' to quit.")
    while True:
        user_input = input("\nUser: ")
        if user_input.lower() in ["exit", "quit"]:
            break
        output = generate_response(user_input)
        print(f"Qwen2.5-3B: {output}")
