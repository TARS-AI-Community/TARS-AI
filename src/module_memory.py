"""
module_memory.py

Memory Management Module for TARS-AI.

Handles long-term and short-term memory. 
Ensures contextual and historical knowledge during interactions.
"""
# === Standard Libraries ===
import os
import json
import requests
from typing import List
from datetime import datetime
from hyperdb import HyperDB
import numpy as np

# === Custom Modules ===
from memory.hyperdb import *
from module_config import load_config

CONFIG = load_config()

class MemoryManager:
    """
    Handles memory operations (long-term and short-term) for TARS-AI.
    """
    def __init__(self, config, char_name, char_greeting):
        self.config = config
        self.char_name = char_name
        self.char_greeting = char_greeting
        self.memory_db_path = os.path.abspath(f"memory/{self.char_name}.pickle.gz")
        self.hyper_db = HyperDB()
        self.long_mem_use = True
        self.initial_memory_path = os.path.abspath("memory/initial_memory.json")
        self.init_dynamic_memory()
        self.load_initial_memory(self.initial_memory_path)

    def init_dynamic_memory(self):
        """
        Initialize dynamic memory from the database file.
        """
        if os.path.exists(self.memory_db_path):
            print(f"LOAD: Found existing memory: {self.char_name}.pickle.gz")
            loaded_successfully = self.hyper_db.load(self.memory_db_path)
            if not loaded_successfully or self.hyper_db.vectors is None:
                print(f"LOAD: Memory load failed. Initializing new memory.")
                self.hyper_db.vectors = np.empty((0, 0), dtype=np.float32)
            else:
                print(f"LOAD: Memory loaded successfully")
        else:
            print(f"LOAD: No memory DB found. Creating new one: {self.memory_db_path}")
            self.hyper_db.add_document({"text": f'{self.char_name}: {self.char_greeting}'})
            self.hyper_db.save(self.memory_db_path)

    def write_longterm_memory(self, user_input: str, bot_response: str):
        """
        Save user input and bot response to long-term memory.

        Parameters:
        - user_input (str): The user's input.
        - bot_response (str): The bot's response.
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        document = {
            "timestamp": current_time,
            "user_input": user_input,
            "bot_response": bot_response,
        }
        self.hyper_db.add_document(document)
        self.hyper_db.save(self.memory_db_path)

    def get_related_memories(self, query: str) -> str:
        """
        Retrieve memories related to a given query from the HyperDB.

        Parameters:
        - query (str): The input query.

        Returns:
        - str: Relevant memories or a fallback message.
        """
        try:
            # Query the memory database for relevant entries
            results = self.hyper_db.query(query, top_k=1, return_similarities=False)
            
            if results:
                memory = results[0]
                memory_list = self.hyper_db.dict()

                # Find the index of the memory for context retrieval
                start_index = next((i for i, d in enumerate(memory_list) if d['document'] == memory), None)

                if start_index is not None:
                    prev_count = 1
                    post_count = 1

                    # Calculate indices for surrounding context
                    start = max(start_index - prev_count, 0)
                    end = min(start_index + post_count + 1, len(memory_list))

                    # Retrieve and format the context memories
                    result = [memory_list[i]['document'] for i in range(start, end)]
                    return result
                else:
                    return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] WARN: Could not locate memory in the database. Memory: {memory}"
            else:
                return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] WARN: No memories found for the query."
        except Exception as e:
            print(f"ERROR: Error retrieving related memories: {e}")
            return "Error retrieving related memories."
    
    def get_longterm_memory(self, user_input: str) -> str:
        """
        Retrieve long-term memory relevant to a user input.

        Parameters:
        - user_input (str): The user input.

        Returns:
        - str: Relevant memory or a fallback message.
        """
        try:
            if self.long_mem_use:
                # Fetch related memories
                past = self.get_related_memories(user_input)
                return str(past) if past else "No relevant memories found."
            return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] WARN: Long-term memory is disabled."
        except Exception as e:
            print(f"ERROR: Error retrieving long-term memory: {e}")
            return "Error retrieving long-term memory."

    def get_shortterm_memories_recent(self, max_entries: int) -> List[str]:
        """
        Retrieve the most recent short-term memories.

        Parameters:
        - max_entries (int): Number of recent memories to retrieve.

        Returns:
        - List[str]: List of recent memory documents.
        """
        # Get the memory dictionary
        memory_dict = self.hyper_db.dict()
        return [entry['document'] for entry in memory_dict[-max_entries:]] # Retrieve the most recent entries
    
    def get_shortterm_memories_tokenlimit(self, token_limit: int) -> str:
        """
        Retrieve short-term memories constrained by a token limit.

        Parameters:
        - token_limit (int): Maximum token limit.

        Returns:
        - str: Concatenated memories formatted for output.
        """
        accumulated_documents = []
        accumulated_length = 0

        for entry in reversed(self.hyper_db.dict()):
            user_input = entry['document'].get('user_input', "")
            bot_response = entry['document'].get('bot_response', "")

            if not user_input or not bot_response:
                continue

            text_str = f"user_input: {user_input}\nbot_response: {bot_response}"
            text_length = self.token_count(text_str)['length']

            if accumulated_length + text_length > token_limit:
                break

            accumulated_documents.append((user_input, bot_response))
            accumulated_length += text_length

        formatted_output = '\n'.join(
            [f"{{user}}: {ui}\n{{char}}: {br}" for ui, br in reversed(accumulated_documents)]
        )
        return formatted_output

    def write_tool_used(self, toolused: str):
        """
        Record the use of a tool in long-term memory.

        Parameters:
        - toolused (str): Description of the tool used.
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        document = {
            "timestamp": current_time,
            "bot_response": toolused
        }
        self.hyper_db.add_document(document)
        self.hyper_db.save(self.memory_db_path)

    def load_initial_memory(self, json_file_path: str):
        """
        Load memories from a JSON file and inject them into the memory database.

        Parameters:
        - json_file_path (str): Path to the JSON file.
        """
        if os.path.exists(json_file_path):
            print(f"LOAD: Injecting memories from JSON.")
            with open(json_file_path, 'r') as file:
                memories = json.load(file)

            for memory in memories:
                time = memory.get("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                user_input = memory.get("userinput", "")
                bot_response = memory.get("botresponse", "")
                self.write_longterm_memory(user_input, bot_response)

            os.rename(json_file_path, os.path.splitext(json_file_path)[0] + ".loaded")

    def token_count(self, text: str) -> dict:
        """
        Calculate the number of tokens in a given text.

        Parameters:
        - text (str): Input text.

        Returns:
        - dict: Dictionary with token count.
        """
        llm_backend = self.config['LLM']['llm_backend']
        # Cache for already logged fallback warnings
        if not hasattr(self, '_fallback_warning_logged'):
            self._fallback_warning_logged = False

        # Check the LLM backend and handle token counting
        if llm_backend == "openai":
            # Use tiktoken for OpenAI models
            try:
                import tiktoken

                # Explicitly map encoding for models that fail automatic detection
                openai_model = self.config['LLM'].get('openai_model', None)
                override_encoding_model = self.config['LLM'].get('override_encoding_model', "cl100k_base")
                try:
                    enc = tiktoken.encoding_for_model(openai_model)
                except KeyError:
                    if not hasattr(self, '_fallback_warning_logged'):
                        print(f"INFO: Automatic mapping failed '{openai_model}'. Using '{override_encoding_model}'.")
                        self._fallback_warning_logged = True
                    enc = tiktoken.get_encoding(override_encoding_model)

                length = {"length": len(enc.encode(text))}
                return length
            
            except Exception as e:
                if not hasattr(self, '_token_error_logged'):
                    print(f"ERROR: Failed to calculate tokens using tiktoken: {e}")
                    self._token_error_logged = True
                return {"length": 0}


        elif llm_backend in ["ooba", "tabby"]:
            # Handle token counting for other backends via API
            url = f"{self.config['LLM']['base_url']}/v1/internal/token-count" if llm_backend == "ooba" else f"{self.config['LLM']['base_url']}/v1/token/encode"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config['LLM']['api_key']}"
            }
            data = {
                "text": text
            }

            try:
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Request to {llm_backend} token count API failed: {e}")
                return {"length": 0}

        else:
            print(f"ERROR: Unsupported LLM backend: {llm_backend}")
            return {"length": 0}
