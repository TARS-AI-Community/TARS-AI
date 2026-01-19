"""
module_memory.py

Memory Management Module for TARS-AI

Handles long-term and short-term memory with enhanced retrieval.
Includes automatic topic index tracking for months of conversation history.

Atomikspace: update, now using the top 3 search results with expanded context windows and recency scoring, plus adds an AI-maintained topic index
"""

import os
import json
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from hyperdb import HyperDB
import numpy as np

from modules.module_hyperdb import *
from modules.module_config import load_config
from modules.module_messageQue import queue_message

CONFIG = load_config()

class MemoryManager:
    """
    Handles memory operations (long-term and short-term) for TARS-AI.
    Enhanced with better context retrieval, memory synthesis, and topic indexing.
    """
    def __init__(self, config, char_name, char_greeting, ui_manager):
        self.config = config
        self.char_name = char_name
        self.char_greeting = char_greeting
        self.memory_db_path = os.path.abspath(os.path.join(os.path.join("..", "memory"), f"{self.char_name}.pickle.gz"))

        self.topic_index_path = os.path.abspath(os.path.join(os.path.join("..", "memory"), f"{self.char_name}_topics.json"))

        rag_config = self.config.get('RAG', {})
        self.rag_strategy = rag_config.get('strategy', 'naive')
        self.vector_weight = float(rag_config.get('vector_weight', 0.5))
        self.top_k = int(rag_config.get('top_k', 5))

        self.context_window_size = int(rag_config.get('context_window', 2))
        self.max_memories_to_use = int(rag_config.get('max_memories', 3))
        self.recency_boost_days = int(rag_config.get('recency_boost_days', 7))

        self.hyper_db = HyperDB(rag_strategy=self.rag_strategy)
        self.long_mem_use = True
        self.initial_memory_path = os.path.abspath(os.path.join(os.path.join("..", "memory", "initial_memory.json")))

        self.ui_manager = ui_manager  

        self.init_dynamic_memory()
        self.load_initial_memory(self.initial_memory_path)
        self.load_topic_index()

    def init_dynamic_memory(self):
        """
        Initialize dynamic memory from the database file.
        """
        if os.path.exists(self.memory_db_path):
            queue_message(f"LOAD: Found existing memory: {self.char_name}.pickle.gz")
            loaded_successfully = self.hyper_db.load(self.memory_db_path)
            if not loaded_successfully or self.hyper_db.vectors is None:
                queue_message(f"LOAD: Memory load failed. Initializing new memory.")
                self.hyper_db.vectors = np.empty((0, 0), dtype=np.float32)
            else:
                queue_message(f"LOAD: Memory loaded successfully")
        else:
            queue_message(f"LOAD: No memory DB found. Creating new one: {self.memory_db_path}")
            self.hyper_db.add_document({"text": f'{self.char_name}: {self.char_greeting}'})
            self.hyper_db.save(self.memory_db_path)

    def load_topic_index(self):
        if os.path.exists(self.topic_index_path):
            try:
                with open(self.topic_index_path, 'r') as f:
                    self.topic_index = json.load(f)
                queue_message(f"LOAD: Topic index loaded with {len(self.topic_index.get('topics', []))} topics")
            except Exception as e:
                queue_message(f"WARN: Failed to load topic index: {e}")
                self.topic_index = {"topics": [], "last_updated": datetime.now().isoformat()}
        else:
            queue_message(f"LOAD: No topic index found. Creating new one.")
            self.topic_index = {
                "topics": [],
                "last_updated": datetime.now().isoformat(),
                "total_conversations": 0
            }
            self.save_topic_index()

    def save_topic_index(self):
        try:
            os.makedirs(os.path.dirname(self.topic_index_path), exist_ok=True)
            with open(self.topic_index_path, 'w') as f:
                json.dump(self.topic_index, f, indent=2)
        except Exception as e:
            queue_message(f"ERROR: Failed to save topic index: {e}")

    def get_topic_index_summary(self) -> str:
        if not self.topic_index.get('topics'):
            return ""

        topics = self.topic_index['topics']
        last_updated = self.topic_index.get('last_updated', 'unknown')

        recent_topics = [t for t in topics if isinstance(t, dict) and self._is_recent_topic(t)]
        older_topics = [t for t in topics if isinstance(t, dict) and not self._is_recent_topic(t)]

        recent_names = [t.get('topic', t) if isinstance(t, dict) else t for t in recent_topics]
        older_names = [t.get('topic', t) if isinstance(t, dict) else t for t in older_topics]

        summary_parts = ["=== Discussion Topics Index ==="]

        if recent_names:
            summary_parts.append(f"Recent: {', '.join(recent_names[:15])}")

        if older_names:
            summary_parts.append(f"Previous: {', '.join(older_names[:20])}")

        summary_parts.append("===")

        return "\n".join(summary_parts)

    def _is_recent_topic(self, topic: Dict) -> bool:
        try:
            if isinstance(topic, dict) and 'last_mentioned' in topic:
                last_mentioned = datetime.fromisoformat(topic['last_mentioned'])
                return (datetime.now() - last_mentioned).days <= 30
        except Exception:
            pass
        return False

    def _is_similar_memory(self, new_memory: str, existing_memory: str) -> bool:
        """
        Check if two memories are similar enough to be considered duplicates.
        Returns True if they're similar (should skip the new one).
        """
        # Normalize both memories
        new_words = set(new_memory.lower().split())
        existing_words = set(existing_memory.lower().split())
        
        # Remove common filler words
        filler = {'the', 'a', 'an', 'is', 'on', 'with', 'and', 'or', 'of', 'to', 'in'}
        new_words -= filler
        existing_words -= filler
        
        # If either is empty after filtering, not similar
        if not new_words or not existing_words:
            return False
        
        # Calculate word overlap percentage
        overlap = len(new_words & existing_words)
        smaller_set_size = min(len(new_words), len(existing_words))
        
        # If 70%+ of words overlap, consider it similar
        similarity = overlap / smaller_set_size if smaller_set_size > 0 else 0
        return similarity >= 0.7

    def update_topic_index_with_ai_response(self, ai_extracted_topics: str):
        try:
            parsed = json.loads(ai_extracted_topics.strip())
            
            # Handle both formats: ["topic1", "topic2"] or {"new_topics": ["topic1", "topic2"]}
            if isinstance(parsed, dict):
                new_topics = parsed.get('new_topics', parsed.get('topics', []))
            elif isinstance(parsed, list):
                new_topics = parsed
            else:
                return
            
            if not isinstance(new_topics, list):
                return

            current_topic_names = set()
            for t in self.topic_index['topics']:
                if isinstance(t, dict):
                    current_topic_names.add(t.get('topic', '').lower())
                else:
                    current_topic_names.add(str(t).lower())

            added_count = 0
            added_memories = []
            
            for topic in new_topics:
                if isinstance(topic, str) and topic.strip():
                    topic_clean = topic.strip()
                    
                    # Skip if too long
                    if len(topic_clean) > 60:
                        continue
                    
                    # Check if already exists (exact match)
                    if topic_clean.lower() in current_topic_names:
                        continue
                    
                    # Check if similar to any existing memory
                    is_duplicate = False
                    for existing_topic in self.topic_index['topics']:
                        existing_text = existing_topic.get('topic', '') if isinstance(existing_topic, dict) else str(existing_topic)
                        if self._is_similar_memory(topic_clean, existing_text):
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        self.topic_index['topics'].append({
                            'topic': topic_clean,
                            'first_mentioned': datetime.now().isoformat(),
                            'last_mentioned': datetime.now().isoformat(),
                            'mention_count': 1
                        })
                        current_topic_names.add(topic_clean.lower())
                        added_count += 1
                        added_memories.append(topic_clean)

            if added_count > 0:
                self.topic_index['last_updated'] = datetime.now().isoformat()
                self.topic_index['total_conversations'] = self.topic_index.get('total_conversations', 0) + 1
                self.save_topic_index()
                
                # Just list the new memories
                for mem in added_memories:
                    queue_message(f"MEMORY: {mem}")

        except json.JSONDecodeError:
            pass
        except Exception as e:
            queue_message(f"MEMORY: Error: {e}")

    def update_existing_topic(self, topic_name: str):
        topic_lower = topic_name.lower()
        for topic in self.topic_index['topics']:
            if isinstance(topic, dict):
                if topic.get('topic', '').lower() == topic_lower:
                    topic['last_mentioned'] = datetime.now().isoformat()
                    topic['mention_count'] = topic.get('mention_count', 1) + 1
                    self.save_topic_index()
                    break

    def write_longterm_memory(self, user_input: str, bot_response: str):
        self.ui_manager.save_memory()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        document = {
            "timestamp": current_time,
            "user_input": user_input,
            "bot_response": bot_response,
        }
        self.hyper_db.add_document(document)
        self.hyper_db.save(self.memory_db_path)

    def _parse_timestamp(self, memory: Dict[str, Any]) -> Optional[datetime]:
        try:
            timestamp_str = memory.get('timestamp', '')
            if timestamp_str:
                return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        return None

    def _calculate_recency_score(self, memory: Dict[str, Any]) -> float:
        timestamp = self._parse_timestamp(memory)
        if not timestamp:
            return 0.5

        days_old = (datetime.now() - timestamp).days

        if days_old <= self.recency_boost_days:
            return 1.0 - (days_old / (self.recency_boost_days * 2))
        else:
            return max(0.1, 0.5 * np.exp(-(days_old - self.recency_boost_days) / 30))

    def get_related_memories(self, query: str, include_context: bool = True) -> List[Dict[str, Any]]:
        self.ui_manager.think()

        try:
            results = self.hyper_db.query(
                query, 
                top_k=self.top_k, 
                return_similarities=True
            )

            if not results:
                return []

            memory_list = self.hyper_db.dict()
            expanded_memories = []
            seen_indices = set()

            num_to_process = min(self.max_memories_to_use, len(results))

            for i in range(num_to_process):
                # Handle both tuple (document, similarity) and dict formats
                if isinstance(results[i], tuple):
                    memory = results[i][0]
                    similarity = results[i][1] if len(results[i]) > 1 else 0.0
                else:
                    memory = results[i]['document']
                    similarity = results[i].get('similarity', 0.0)

                start_index = next((idx for idx, d in enumerate(memory_list) if d['document'] == memory), None)

                if start_index is None:
                    continue

                if include_context:
                    context_start = max(start_index - self.context_window_size, 0)
                    context_end = min(start_index + self.context_window_size + 1, len(memory_list))

                    for idx in range(context_start, context_end):
                        if idx not in seen_indices:
                            mem_doc = memory_list[idx]['document']
                            recency_score = self._calculate_recency_score(mem_doc)

                            if idx == start_index:
                                combined_score = 0.8 * similarity + 0.2 * recency_score
                            else:
                                combined_score = 0.5 * similarity + 0.5 * recency_score

                            expanded_memories.append({
                                'document': mem_doc,
                                'index': idx,
                                'similarity': similarity,
                                'recency_score': recency_score,
                                'combined_score': combined_score,
                                'is_primary': idx == start_index
                            })
                            seen_indices.add(idx)
                else:
                    recency_score = self._calculate_recency_score(memory)
                    combined_score = 0.7 * similarity + 0.3 * recency_score

                    expanded_memories.append({
                        'document': memory,
                        'index': start_index,
                        'similarity': similarity,
                        'recency_score': recency_score,
                        'combined_score': combined_score,
                        'is_primary': True
                    })
                    seen_indices.add(start_index)

            expanded_memories.sort(key=lambda x: x['combined_score'], reverse=True)

            return expanded_memories

        except Exception as e:
            queue_message(f"ERROR: Error retrieving related memories: {e}")
            return []

    def format_memories_for_context(self, memories: List[Dict[str, Any]]) -> str:
        """
        Format retrieved memories into a clean, readable context string for the LLM.

        Parameters:
        - memories: List of memory documents with metadata

        Returns:
        - str: Formatted memory context
        """
        if not memories:
            return ""

        formatted_parts = []
        formatted_parts.append("=== Relevant Past Conversations ===\n")

        for i, mem in enumerate(memories, 1):
            doc = mem['document']
            timestamp = doc.get('timestamp', 'Unknown time')
            user_input = doc.get('user_input', '')
            bot_response = doc.get('bot_response', '')

            relative_time = self._get_relative_time(timestamp)
            relevance_marker = "★" if mem.get('is_primary', False) else "•"

            if user_input and bot_response:
                formatted_parts.append(
                    f"{relevance_marker} [{relative_time}]\n"
                    f"  User: {user_input}\n"
                    f"  {self.char_name}: {bot_response}\n"
                )
            elif bot_response:
                formatted_parts.append(
                    f"{relevance_marker} [{relative_time}] {bot_response}\n"
                )

        formatted_parts.append("=== End of Past Conversations ===\n")
        return "\n".join(formatted_parts)

    def _get_relative_time(self, timestamp_str: str) -> str:
        """
        Convert timestamp to relative time description.

        Parameters:
        - timestamp_str: Timestamp string

        Returns:
        - str: Relative time description
        """
        try:
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            delta = datetime.now() - timestamp

            if delta.days == 0:
                hours = delta.seconds // 3600
                if hours == 0:
                    minutes = delta.seconds // 60
                    return f"{minutes} min ago" if minutes > 1 else "just now"
                return f"{hours}h ago"
            elif delta.days == 1:
                return "yesterday"
            elif delta.days < 7:
                return f"{delta.days} days ago"
            elif delta.days < 30:
                weeks = delta.days // 7
                return f"{weeks} week{'s' if weeks > 1 else ''} ago"
            else:
                return timestamp_str
        except Exception:
            return timestamp_str

    def get_longterm_memory(self, user_input: str) -> str:
        """
        IMPROVED: Retrieve formatted long-term memory relevant to user input.
        Now includes topic index at the beginning.

        Parameters:
        - user_input (str): The user input.

        Returns:
        - str: Formatted relevant memories with topic index.
        """
        try:
            if not self.long_mem_use:
                return ""

            context_parts = []

            topic_summary = self.get_topic_index_summary()
            if topic_summary:
                context_parts.append(topic_summary)
                context_parts.append("")  

            memories = self.get_related_memories(user_input, include_context=True)

            if memories:
                formatted_context = self.format_memories_for_context(memories)
                context_parts.append(formatted_context)

            return "\n".join(context_parts)

        except Exception as e:
            queue_message(f"ERROR: Error retrieving long-term memory: {e}")
            return ""

    def get_conversation_summary(self, lookback_hours: int = 24) -> str:
        """
        Get a summary of recent conversation topics.

        Parameters:
        - lookback_hours: How many hours to look back

        Returns:
        - str: Summary of recent topics
        """
        try:
            memory_list = self.hyper_db.dict()
            cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

            recent_topics = []
            for entry in reversed(memory_list):
                doc = entry['document']
                timestamp = self._parse_timestamp(doc)

                if timestamp and timestamp > cutoff_time:
                    user_input = doc.get('user_input', '')
                    if user_input:
                        recent_topics.append(user_input)

            if recent_topics:
                return f"Recent topics discussed: {', '.join(recent_topics[:5])}"
            return ""

        except Exception as e:
            return ""

    def get_shortterm_memories_recent(self, max_entries: int) -> List[str]:
        """
        Retrieve the most recent short-term memories.

        Parameters:
        - max_entries (int): Number of recent memories to retrieve.

        Returns:
        - List[str]: List of recent memory documents.
        """
        memory_dict = self.hyper_db.dict()
        return [entry['document'] for entry in memory_dict[-max_entries:]]

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
            queue_message(f"LOAD: Injecting memories from JSON.")
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

        if not hasattr(self, '_fallback_warning_logged'):
            self._fallback_warning_logged = False

        if llm_backend in ["openai", "deepinfra"]:
            try:
                import tiktoken
                override_encoding_model = self.config['LLM'].get('override_encoding_model', "cl100k_base")

                if llm_backend == "deepinfra":
                    enc = tiktoken.get_encoding(override_encoding_model)
                else:
                    openai_model = self.config['LLM'].get('openai_model', None)
                    try:
                        enc = tiktoken.encoding_for_model(openai_model)
                    except KeyError:
                        if not self._fallback_warning_logged:
                            queue_message(f"INFO: Automatic mapping failed '{openai_model}'. Using '{override_encoding_model}'.")
                            self._fallback_warning_logged = True
                        enc = tiktoken.get_encoding(override_encoding_model)

                length = {"length": len(enc.encode(text))}
                return length

            except Exception as e:
                if not hasattr(self, '_token_error_logged'):
                    queue_message(f"ERROR: Failed to calculate tokens using tiktoken: {e}")
                    self._token_error_logged = True
                return {"length": 0}

        elif llm_backend in ["ooba", "tabby"]:
            url = f"{self.config['LLM']['base_url']}/v1/internal/token-count" if llm_backend == "ooba" else f"{self.config['LLM']['base_url']}/v1/token/encode"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config['LLM']['api_key']}"
            }
            data = {"text": text}

            try:
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                queue_message(f"ERROR: Request to {llm_backend} token count API failed: {e}")
                return {"length": 0}
        else:
            queue_message(f"ERROR: Unsupported LLM backend: {llm_backend}")
            return {"length": 0}