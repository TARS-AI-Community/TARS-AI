"""
Module: Memory Lite
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from modules.module_config import load_config
from modules.module_messageQue import queue_message

CONFIG = load_config()

STOPWORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
    'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
    'from', 'up', 'about', 'into', 'through', 'during', 'before', 'after',
    'above', 'below', 'between', 'under', 'again', 'further', 'then',
    'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
    'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'and',
    'but', 'if', 'or', 'because', 'as', 'until', 'while', 'although',
    'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you',
    'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his',
    'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself',
    'they', 'them', 'their', 'theirs', 'themselves', 'what', 'which',
    'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'im', 'dont',
    'wont', 'cant', 'isnt', 'arent', 'wasnt', 'werent', 'hasnt', 'havent',
    'hadnt', 'doesnt', 'didnt', 'wouldnt', 'couldnt', 'shouldnt', 'mightnt',
    'mustnt', 'lets', 'thats', 'whos', 'whats', 'heres', 'theres', 'whens',
    'wheres', 'whys', 'hows', 'yeah', 'yes', 'no', 'okay', 'ok', 'well',
    'um', 'uh', 'like', 'know', 'think', 'want', 'get', 'got', 'go',
    'going', 'say', 'said', 'tell', 'told', 'ask', 'asked', 'make', 'made'
}


class MemoryManagerLite:
    def __init__(self, config, char_name, char_greeting, ui_manager):
        self.config = config
        self.char_name = char_name
        self.char_greeting = char_greeting
        self.memory_db_path = os.path.abspath(os.path.join(os.path.join("..", "memory"), f"{self.char_name}_lite.json"))
        self.topic_index_path = os.path.abspath(os.path.join(os.path.join("..", "memory"), f"{self.char_name}_topics.json"))

        rag_config = self.config.get('RAG', {})
        self.top_k = int(rag_config.get('top_k', 5))
        self.context_window_size = int(rag_config.get('context_window', 2))
        self.max_memories_to_use = int(rag_config.get('max_memories', 3))
        self.recency_boost_days = int(rag_config.get('recency_boost_days', 7))

        self.documents = []
        self.long_mem_use = True
        self.initial_memory_path = os.path.abspath(os.path.join(os.path.join("..", "memory", "initial_memory.json")))

        self.ui_manager = ui_manager

        self.init_dynamic_memory()
        self.load_initial_memory(self.initial_memory_path)
        self.load_topic_index()

    def _extract_keywords(self, text: str) -> set:
        if not text:
            return set()
        words = text.lower().split()
        keywords = set()
        for word in words:
            cleaned = ''.join(c for c in word if c.isalnum())
            if len(cleaned) >= 3 and cleaned not in STOPWORDS:
                keywords.add(cleaned)
        return keywords

    def _calculate_keyword_score(self, query_keywords: set, doc_keywords: set) -> float:
        if not query_keywords or not doc_keywords:
            return 0.0
        intersection = len(query_keywords & doc_keywords)
        union = len(query_keywords | doc_keywords)
        if union == 0:
            return 0.0
        return intersection / union

    def init_dynamic_memory(self):
        if os.path.exists(self.memory_db_path):
            queue_message(f"LOAD: Found existing lite memory: {self.char_name}_lite.json")
            try:
                with open(self.memory_db_path, 'r') as f:
                    self.documents = json.load(f)
                queue_message(f"LOAD: Lite memory loaded with {len(self.documents)} entries")
            except Exception as e:
                queue_message(f"LOAD: Memory load failed: {e}. Initializing new memory.")
                self.documents = []
        else:
            queue_message(f"LOAD: No lite memory found. Creating new one: {self.memory_db_path}")
            self.documents = [{
                "text": f'{self.char_name}: {self.char_greeting}',
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "keywords": list(self._extract_keywords(self.char_greeting))
            }]
            self._save_memory()

    def _save_memory(self):
        try:
            os.makedirs(os.path.dirname(self.memory_db_path), exist_ok=True)
            with open(self.memory_db_path, 'w') as f:
                json.dump(self.documents, f, indent=2)
        except Exception as e:
            queue_message(f"ERROR: Failed to save lite memory: {e}")

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
        new_words = set(new_memory.lower().split())
        existing_words = set(existing_memory.lower().split())

        filler = {'the', 'a', 'an', 'is', 'on', 'with', 'and', 'or', 'of', 'to', 'in'}
        new_words -= filler
        existing_words -= filler

        if not new_words or not existing_words:
            return False

        overlap = len(new_words & existing_words)
        smaller_set_size = min(len(new_words), len(existing_words))

        similarity = overlap / smaller_set_size if smaller_set_size > 0 else 0
        return similarity >= 0.7

    def update_topic_index_with_ai_response(self, ai_extracted_topics: str):
        try:
            parsed = json.loads(ai_extracted_topics.strip())

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
            for topic in new_topics:
                if isinstance(topic, str) and topic.strip():
                    topic_clean = topic.strip()

                    if len(topic_clean) > 60:
                        continue

                    if topic_clean.lower() in current_topic_names:
                        continue

                    is_duplicate = False
                    for existing_topic in self.topic_index['topics']:
                        existing_text = existing_topic.get('topic', '') if isinstance(existing_topic, dict) else str(existing_topic)
                        if self._is_similar_memory(topic_clean, existing_text):
                            is_duplicate = True
                            break

                    if is_duplicate:
                        continue

                    self.topic_index['topics'].append({
                        'topic': topic_clean,
                        'first_mentioned': datetime.now().isoformat(),
                        'last_mentioned': datetime.now().isoformat(),
                        'mention_count': 1
                    })
                    current_topic_names.add(topic_clean.lower())
                    added_count += 1

            if added_count > 0:
                self.topic_index['last_updated'] = datetime.now().isoformat()
                self.save_topic_index()
                queue_message(f"INFO: Added {added_count} new topics to index")

        except json.JSONDecodeError:
            pass
        except Exception as e:
            queue_message(f"WARN: Failed to update topic index: {e}")

    def write_longterm_memory(self, user_input, bot_response):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        combined_text = f"{user_input} {bot_response}"
        keywords = list(self._extract_keywords(combined_text))

        document = {
            "user_input": user_input,
            "bot_response": bot_response,
            "timestamp": current_time,
            "keywords": keywords
        }
        self.documents.append(document)
        self._save_memory()

        if self.ui_manager:
            self.ui_manager.save_memory()

    def query_memories(self, query_text: str, top_k: int = 5) -> List[tuple]:
        if not self.documents:
            return []

        query_keywords = self._extract_keywords(query_text)
        if not query_keywords:
            return [(doc, 0.1) for doc in self.documents[-top_k:]]

        scored_docs = []
        now = datetime.now()

        for i, doc in enumerate(self.documents):
            doc_keywords = set(doc.get('keywords', []))
            if not doc_keywords:
                text = doc.get('user_input', '') + ' ' + doc.get('bot_response', '')
                doc_keywords = self._extract_keywords(text)

            score = self._calculate_keyword_score(query_keywords, doc_keywords)

            try:
                timestamp = datetime.strptime(doc.get('timestamp', ''), "%Y-%m-%d %H:%M:%S")
                days_ago = (now - timestamp).days
                if days_ago <= self.recency_boost_days:
                    recency_boost = 0.2 * (1 - days_ago / self.recency_boost_days)
                    score += recency_boost
            except:
                pass

            scored_docs.append((i, doc, score))

        scored_docs.sort(key=lambda x: x[2], reverse=True)
        return [(doc, score) for _, doc, score in scored_docs[:top_k]]

    def get_related_memories(self, user_input: str, include_context: bool = True) -> List[Dict]:
        results = self.query_memories(user_input, self.top_k)

        if not results:
            return []

        top_results = results[:self.max_memories_to_use]
        memories_with_context = []

        for doc, score in top_results:
            if score < 0.05:
                continue

            try:
                doc_index = self.documents.index(doc)
            except ValueError:
                memories_with_context.append({
                    'main': doc,
                    'score': score,
                    'context_before': [],
                    'context_after': []
                })
                continue

            context_before = []
            context_after = []

            if include_context:
                start_idx = max(0, doc_index - self.context_window_size)
                for i in range(start_idx, doc_index):
                    context_before.append(self.documents[i])

                end_idx = min(len(self.documents), doc_index + self.context_window_size + 1)
                for i in range(doc_index + 1, end_idx):
                    context_after.append(self.documents[i])

            memories_with_context.append({
                'main': doc,
                'score': score,
                'context_before': context_before,
                'context_after': context_after
            })

        return memories_with_context

    def format_memories_for_context(self, memories: List[Dict]) -> str:
        if not memories:
            return ""

        formatted_parts = ["=== Relevant Past Conversations ==="]

        for i, memory in enumerate(memories, 1):
            main_doc = memory['main']
            score = memory.get('score', 0)

            formatted_parts.append(f"\n--- Memory {i} (relevance: {score:.2f}) ---")

            for ctx in memory.get('context_before', []):
                user = ctx.get('user_input', '')
                bot = ctx.get('bot_response', '')
                if user or bot:
                    formatted_parts.append(f"[context] User: {user}")
                    formatted_parts.append(f"[context] {self.char_name}: {bot}")

            user_input = main_doc.get('user_input', '')
            bot_response = main_doc.get('bot_response', '')
            timestamp = main_doc.get('timestamp', '')

            if user_input or bot_response:
                formatted_parts.append(f"User: {user_input}")
                formatted_parts.append(f"{self.char_name}: {bot_response}")
                if timestamp:
                    formatted_parts.append(f"(from: {timestamp})")

            for ctx in memory.get('context_after', []):
                user = ctx.get('user_input', '')
                bot = ctx.get('bot_response', '')
                if user or bot:
                    formatted_parts.append(f"[context] User: {user}")
                    formatted_parts.append(f"[context] {self.char_name}: {bot}")

        formatted_parts.append("\n===")
        return "\n".join(formatted_parts)

    def get_longterm_memory(self, user_input):
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
        try:
            cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

            recent_topics = []
            for entry in reversed(self.documents):
                try:
                    timestamp = datetime.strptime(entry.get('timestamp', ''), "%Y-%m-%d %H:%M:%S")
                    if timestamp > cutoff_time:
                        user_input = entry.get('user_input', '')
                        if user_input:
                            recent_topics.append(user_input)
                except:
                    continue

            if recent_topics:
                return f"Recent topics discussed: {', '.join(recent_topics[:5])}"
            return ""

        except Exception as e:
            return ""

    def get_shortterm_memories_recent(self, max_entries: int) -> List[Dict]:
        return self.documents[-max_entries:]

    def get_shortterm_memories_tokenlimit(self, token_limit: int) -> str:
        accumulated_documents = []
        accumulated_length = 0

        for entry in reversed(self.documents):
            user_input = entry.get('user_input', "")
            bot_response = entry.get('bot_response', "")
            timestamp = entry.get('timestamp', "")

            if not user_input or not bot_response:
                continue

            time_label = self._get_relative_time(timestamp) if timestamp else ""
            time_prefix = f"[{time_label}] " if time_label else ""

            text_str = f"{time_prefix}{{user}}: {user_input}\n{{char}}: {bot_response}"
            text_length = self.token_count(text_str)['length']

            if accumulated_length + text_length > token_limit:
                break

            accumulated_documents.append((user_input, bot_response, time_prefix))
            accumulated_length += text_length

        formatted_output = '\n'.join(
            [f"{tp}{{user}}: {ui}\n{{char}}: {br}" for ui, br, tp in reversed(accumulated_documents)]
        )
        return formatted_output

    def _get_relative_time(self, timestamp_str: str) -> str:
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

    def write_tool_used(self, toolused: str):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        document = {
            "timestamp": current_time,
            "bot_response": toolused,
            "keywords": list(self._extract_keywords(toolused))
        }
        self.documents.append(document)
        self._save_memory()

    def load_initial_memory(self, json_file_path: str):
        if os.path.exists(json_file_path):
            queue_message(f"LOAD: Injecting memories from JSON.")
            with open(json_file_path, 'r') as file:
                memories = json.load(file)

            for memory in memories:
                user_input = memory.get("userinput", "")
                bot_response = memory.get("botresponse", "")
                self.write_longterm_memory(user_input, bot_response)

            os.rename(json_file_path, os.path.splitext(json_file_path)[0] + ".loaded")

    def token_count(self, text: str) -> dict:
        word_count = len(text.split())
        estimated_tokens = int(word_count / 0.75)
        return {"length": estimated_tokens}