"""
module_memory.py

Memory Management Module for GPTARS.

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

class MemoryManager:
    """
    Handles memory operations (long-term and short-term) for GPTARS.
    """
    def __init__(self, config, char_name, char_greeting):
        self.config = config
        self.char_name = char_name
        self.char_greeting = char_greeting
        self.memory_db_path = os.path.abspath(f"memory/{self.config['CHAR']['char_name']}.pickle.gz")
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
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Found existing memory database: {self.memory_db_path}")
            loaded_successfully = self.hyper_db.load(self.memory_db_path)
            if not loaded_successfully or self.hyper_db.vectors is None:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Memory load failed or database is empty. Initializing new memory.")
                self.hyper_db.vectors = np.empty((0, 0), dtype=np.float32)
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Memory loaded successfully")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: No memory DB found. Creating new one: {self.memory_db_path}")
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
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Error retrieving related memories: {e}")
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
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Error retrieving long-term memory: {e}")
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
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Injecting memories from JSON.")
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

        # Check the LLM backend and set the URL accordingly
        if llm_backend == "openai":
            # OpenAI doesn’t have a direct token count endpoint; you must estimate using tiktoken or similar tools.
            # This implementation assumes you calculate the token count locally.
            from tiktoken import encoding_for_model
            enc = encoding_for_model(self.config['LLM']['openai_model'])
            length = {"length": len(enc.encode(text))}
            return length
        elif llm_backend == "ooba":
            url = f"{self.config['LLM']['base_url']}/v1/internal/token-count"
        elif llm_backend == "tabby":
            url = f"{self.config['LLM']['base_url']}/v1/token/encode"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config['LLM']['api_key']}"
        }
        data = {
            "text": text
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            return response.json()
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: ", response.status_code, response.text)
            return None