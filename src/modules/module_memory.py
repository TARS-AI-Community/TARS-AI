"""
Module: Memory
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
import requests
import threading
from concurrent.futures import Future
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from hyperdb import HyperDB
import numpy as np

from modules.module_hyperdb import *
from modules.module_config import load_config
from modules.module_messageQue import queue_message

CONFIG = load_config()

# Anchor memory directory relative to this file (src/modules/ -> src/memory/)
_MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory")

_MEMORY_FLUSH_INTERVAL = 30  # seconds between periodic disk flushes


class MemoryManager:
    def __init__(self, config, char_name, char_greeting, ui_manager):
        self.config = config
        self.char_name = char_name
        self.char_greeting = char_greeting
        self.memory_db_path = os.path.join(_MEMORY_DIR, f"{self.char_name}.pickle.gz")

        # Legacy path — topics are now stored inside the pickle via extra_data
        self._legacy_topic_path = os.path.join(_MEMORY_DIR, f"{self.char_name}_topics.json")

        rag_config = self.config.get('RAG', {})
        self.rag_strategy = rag_config.get('strategy', 'naive')
        self.top_k = int(rag_config.get('top_k', 5))

        self.context_window_size = int(rag_config.get('context_window', 2))
        self.max_memories_to_use = int(rag_config.get('max_memories', 3))
        self.recency_boost_days = int(rag_config.get('recency_boost_days', 7))

        self.hyper_db = HyperDB(rag_strategy=self.rag_strategy)
        self.long_mem_use = True
        self.initial_memory_path = os.path.join(_MEMORY_DIR, "initial_memory.json")

        self.ui_manager = ui_manager
        self._dirty = False  # True when in-memory state has unflushed changes
        self._flush_lock = threading.Lock()
        self._prefetch_future = None  # Background embedding prefetch
        self._prefetch_query = None
        self._identity_manager = None  # cached identity manager (False = tried and unavailable)
        self._speaker_id_manager = None

        self.init_dynamic_memory()
        self.load_initial_memory(self.initial_memory_path)
        self.load_topic_index()
        self._start_periodic_flush()

    def init_dynamic_memory(self):
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
            self._mark_dirty()

    def load_topic_index(self):
        # Try loading from pickle extra_data first (new location)
        if "topics" in self.hyper_db.extra_data:
            self.topic_index = self.hyper_db.extra_data["topics"]
            queue_message(f"LOAD: Topic index loaded with {len(self.topic_index.get('topics', []))} topics")
            # Migrate: remove legacy JSON file if it exists
            if os.path.exists(self._legacy_topic_path):
                try:
                    os.remove(self._legacy_topic_path)
                    queue_message("LOAD: Migrated topics into pickle, removed legacy JSON")
                except OSError:
                    pass
            return

        # Backwards compat: migrate from legacy JSON file
        if os.path.exists(self._legacy_topic_path):
            try:
                with open(self._legacy_topic_path, 'r') as f:
                    self.topic_index = json.load(f)
                queue_message(f"LOAD: Topic index migrated from JSON ({len(self.topic_index.get('topics', []))} topics)")
                self.save_topic_index()  # persist into pickle
                # Remove the old file
                try:
                    os.remove(self._legacy_topic_path)
                except OSError:
                    pass
                return
            except Exception as e:
                queue_message(f"WARN: Failed to load legacy topic index: {e}")

        # No topics found — create new
        queue_message(f"LOAD: No topic index found. Creating new one.")
        self.topic_index = {
            "topics": [],
            "last_updated": datetime.now().isoformat(),
            "total_conversations": 0
        }
        self.save_topic_index()

    def save_topic_index(self):
        self.hyper_db.extra_data["topics"] = self.topic_index
        self._mark_dirty()

    def _mark_dirty(self):
        """Mark in-memory state as needing a flush to disk."""
        self._dirty = True

    def flush(self, blocking=False):
        """Write in-memory state to disk if dirty. Called by heartbeat + shutdown.

        Args:
            blocking: If True, flush synchronously (used for shutdown).
                      If False, flush in a background thread to avoid blocking the bot.
        """
        if not self._dirty:
            return
        if self._flush_lock.locked():
            return  # A flush is already in progress

        def _do_flush():
            with self._flush_lock:
                try:
                    self.hyper_db.save(self.memory_db_path)
                    self._dirty = False
                except Exception as e:
                    queue_message(f"ERROR: Failed to flush memory to disk: {e}")

        if blocking:
            _do_flush()
        else:
            threading.Thread(target=_do_flush, daemon=True).start()

    def _start_periodic_flush(self):
        """Register a recurring heartbeat task to flush memory periodically."""
        try:
            from modules.module_heartbeat import schedule_recurring
            schedule_recurring(
                "memory_flush", _MEMORY_FLUSH_INTERVAL, lambda: self.flush()
            )
        except Exception:
            pass  # heartbeat not available — memory will flush on shutdown only

    # --- Current Activity Tracking ---
    # Transient activities (TTL-based) that bridge the gap between short-term
    # conversation context and permanent topic facts.

    def save_current_activity(self, activity: str):
        """Store a transient activity note with a timestamp. Auto-pruned on read."""
        if not activity or not activity.strip():
            return
        activities = self.hyper_db.extra_data.setdefault("current_activities", [])
        activities.append({
            "text": activity.strip(),
            "timestamp": datetime.now().isoformat()
        })
        # Keep list bounded to avoid unbounded growth
        if len(activities) > 50:
            activities[:] = activities[-50:]
        self._mark_dirty()

    def get_current_activities(self, max_age_hours: int = 4) -> str:
        """Return recent activities as a prompt-injectable string, pruning expired ones."""
        activities = self.hyper_db.extra_data.get("current_activities", [])
        if not activities:
            return ""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        valid = []
        for a in activities:
            try:
                ts = datetime.fromisoformat(a["timestamp"])
                if ts >= cutoff:
                    valid.append(a)
            except Exception:
                continue
        # Prune expired entries
        if len(valid) != len(activities):
            self.hyper_db.extra_data["current_activities"] = valid
            self._mark_dirty()
        if not valid:
            return ""
        lines = [a["text"] for a in valid[-8:]]  # last 8 activities
        return "Current/recent activities: " + " | ".join(lines)

    def get_topic_index_summary(self) -> str:
        if not self.topic_index.get('topics'):
            return ""

        topics = self.topic_index['topics']

        recent_topics = [t for t in topics if isinstance(t, dict) and self._is_recent_topic(t)]
        older_topics = [t for t in topics if isinstance(t, dict) and not self._is_recent_topic(t)]

        summary_parts = ["=== Known Facts About the User ==="]

        if recent_topics:
            summary_parts.append("Recent:")
            for t in recent_topics[:15]:
                name = t.get('topic', '') if isinstance(t, dict) else str(t)
                count = t.get('mention_count', 1) if isinstance(t, dict) else 1
                last = t.get('last_mentioned', '')
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last)
                        days_ago = (datetime.now() - last_dt).days
                        if days_ago == 0:
                            when = "today"
                        elif days_ago == 1:
                            when = "yesterday"
                        elif days_ago < 7:
                            when = f"{days_ago}d ago"
                        else:
                            when = f"{days_ago // 7}w ago"
                        summary_parts.append(f"  - {name} (mentioned {count}x, last {when})")
                    except Exception:
                        summary_parts.append(f"  - {name}")
                else:
                    summary_parts.append(f"  - {name}")

        if older_topics:
            older_names = [t.get('topic', '') if isinstance(t, dict) else str(t) for t in older_topics[:20]]
            summary_parts.append(f"Older: {', '.join(older_names)}")

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
        filler = {'the', 'a', 'an', 'is', 'on', 'with', 'and', 'or', 'of', 'to', 'in',
                  'has', 'had', 'have', 'was', 'were', 'been', 'be', 'am', 'are',
                  'i', 'my', 'me', 'you', 'your', 'they', 'their', 'it', 'its',
                  'that', 'this', 'for', 'at', 'by', 'from', 'about', 'just', 'so'}

        new_words = set(new_memory.lower().split()) - filler
        existing_words = set(existing_memory.lower().split()) - filler

        if not new_words or not existing_words:
            return False

        overlap = len(new_words & existing_words)
        smaller_set_size = min(len(new_words), len(existing_words))

        # Use overlap ratio against the SMALLER set — catches cases like
        # "has dog named Max" vs "adopted a dog called Max" (overlap: {dog, max})
        similarity = overlap / smaller_set_size if smaller_set_size > 0 else 0
        return similarity >= 0.6

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
            added_memories = []

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

                # Prune if over 100 topics — drop oldest, lowest mention-count entries
                max_topics = 100
                topics = self.topic_index['topics']
                if len(topics) > max_topics:
                    topics.sort(key=lambda t: (
                        t.get('mention_count', 1) if isinstance(t, dict) else 1,
                        t.get('last_mentioned', '') if isinstance(t, dict) else ''
                    ))
                    self.topic_index['topics'] = topics[-max_topics:]

                self.save_topic_index()

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

    def write_longterm_memory(self, user_input: str, bot_response: str, activity_context: str = None):
        self.ui_manager.save_memory()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        document = {
            "timestamp": current_time,
            "user_input": user_input,
            "bot_response": bot_response,
        }
        # Store enriched activity keywords on the document itself so they're
        # permanently searchable via BM25 and embedding — not just the 4h TTL cache.
        # e.g. "cooking spaghetti pasta for dinner, making Italian food, eating"
        if activity_context:
            document["activity_context"] = activity_context
        # Tag memory with current speaker and present people via identity coordinator
        try:
            if self._identity_manager is None:
                try:
                    from modules.module_identity import get_identity_manager
                    self._identity_manager = get_identity_manager() or False
                except Exception:
                    self._identity_manager = False
            im = self._identity_manager
            if im and im is not False:
                speaker = im.get_current_speaker()
                if speaker is not None:
                    document["speaker"] = speaker
                present = im.get_present_people()
                if present:
                    document["present"] = [p["name"] for p in present]
            else:
                if self._speaker_id_manager is None:
                    try:
                        from modules.module_speaker_id import get_speaker_id_manager
                        self._speaker_id_manager = get_speaker_id_manager() or False
                    except Exception:
                        self._speaker_id_manager = False
                sid = self._speaker_id_manager
                if sid and sid is not False:
                    speaker = sid.get_current_speaker()
                    if speaker is not None:
                        document["speaker"] = speaker
        except Exception:
            pass
        self.hyper_db.add_document(document)
        self._mark_dirty()

    def reindex_embeddings(self):
        """Re-embed all documents with current embedding function.

        Run once after changing the embedding logic (Change B) to fix old
        vectors that were computed from metadata-polluted text.
        Can be triggered from the console or a startup flag.
        """
        if not self.hyper_db.documents:
            queue_message("MEMORY: No documents to reindex.")
            return
        count = len(self.hyper_db.documents)
        queue_message(f"MEMORY: Reindexing {count} documents (this may take a while)...")
        new_vectors = self.hyper_db.embedding_function(self.hyper_db.documents)
        self.hyper_db.vectors = np.array(new_vectors, dtype=np.float32)
        if self.hyper_db.rag_strategy == "hybrid":
            self.hyper_db._init_bm25_index()
        self._mark_dirty()
        self.flush(blocking=True)
        queue_message(f"MEMORY: Reindex complete. {count} document vectors updated.")


    def _parse_timestamp(self, memory: Dict[str, Any]) -> Optional[datetime]:
        cached = memory.get('_parsed_ts')
        if cached is not None:
            return cached
        try:
            timestamp_str = memory.get('timestamp', '')
            if timestamp_str:
                dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                memory['_parsed_ts'] = dt
                return dt
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

    def _parse_time_reference(self, query: str):
        """Parse temporal references from query. Returns (target_datetime, window_timedelta) or (None, None)."""
        import re
        q = query.lower()
        now = datetime.now()

        # "N days/hours/weeks/months ago"
        m = re.search(r'(\d+)\s+(day|hour|week|month)s?\s+ago', q)
        if m:
            num = int(m.group(1))
            unit = m.group(2)
            if unit == 'hour':
                return now - timedelta(hours=num), timedelta(hours=2)
            elif unit == 'day':
                return now - timedelta(days=num), timedelta(days=1)
            elif unit == 'week':
                return now - timedelta(weeks=num), timedelta(days=3)
            elif unit == 'month':
                return now - timedelta(days=num * 30), timedelta(days=7)

        if 'yesterday' in q:
            return now - timedelta(days=1), timedelta(days=1)
        if 'last night' in q:
            return now - timedelta(days=1), timedelta(hours=12)
        if 'today' in q or 'this morning' in q or 'tonight' in q or 'earlier' in q:
            return now, timedelta(days=1)
        if 'last week' in q:
            return now - timedelta(weeks=1), timedelta(days=3)
        if 'last month' in q:
            return now - timedelta(days=30), timedelta(days=7)
        if 'few days ago' in q or 'other day' in q:
            return now - timedelta(days=3), timedelta(days=2)

        return None, None

    def _calculate_time_boost(self, memory: Dict[str, Any], time_target, time_window) -> float:
        """Score multiplier based on how close a memory is to the target time."""
        timestamp = self._parse_timestamp(memory)
        if not timestamp or not time_target:
            return 1.0

        distance = abs((timestamp - time_target).total_seconds())
        window_seconds = time_window.total_seconds()

        if distance <= window_seconds:
            return 2.0   # Strong boost — within target window
        elif distance <= window_seconds * 2:
            return 1.5   # Moderate boost — close to target
        else:
            return 1.0   # No boost

    def prefetch_embedding(self, query: str):
        """Start computing the query embedding in a background thread.

        Call this as early as possible (e.g. right after STT returns) so the
        embedding is ready by the time get_longterm_memory() needs it.
        """
        self._prefetch_query = query
        future = Future()

        def _compute():
            try:
                vec = self.hyper_db.embedding_function([query])[0]
                future.set_result(vec)
            except Exception as e:
                future.set_exception(e)

        self._prefetch_future = future
        threading.Thread(target=_compute, daemon=True).start()

    def _get_query_vector(self, query: str):
        """Return query embedding, using prefetched result if available."""
        if (self._prefetch_future is not None
                and self._prefetch_query == query):
            try:
                vec = self._prefetch_future.result(timeout=10)
                self._prefetch_future = None
                self._prefetch_query = None
                return vec
            except Exception:
                pass
        # Fallback: compute synchronously
        return self.hyper_db.embedding_function([query])[0]

    def get_related_memories(self, query: str, include_context: bool = True) -> List[Dict[str, Any]]:
        self.ui_manager.think()

        try:
            documents = self.hyper_db.documents
            if not documents:
                return []

            # Parse temporal reference for time-aware boosting
            time_target, time_window = self._parse_time_reference(query)

            # Use prefetched query vector if available
            query_vector = self._get_query_vector(query)

            # Use configured search strategy (hybrid or naive) — this is where
            # BM25 keyword matching + FlashRank reranking actually run now
            results = self.hyper_db.query(
                query, top_k=self.top_k,
                return_similarities=True, query_vector=query_vector
            )

            if not results:
                return []

            # Build identity map for O(1) doc-to-index lookup
            doc_id_to_idx = {id(doc): idx for idx, doc in enumerate(documents)}
            num_docs = len(documents)

            # Map results to indices with scores, deduplicating near-identical content.
            # Without this, "what color is my dog?" could return 5 exchanges that all
            # say "dog named Max" — wasting the limited context budget on repetition.
            primary_hits = []
            seen_content = []
            for doc, score in results:
                if len(primary_hits) >= self.max_memories_to_use:
                    break
                idx = doc_id_to_idx.get(id(doc))
                if idx is None:
                    continue
                # Skip tool-only entries (no user_input) — these are noise from
                # write_tool_used() and pollute search results
                if not doc.get('user_input'):
                    continue
                # Check for duplicate content (same user_input or very similar)
                content_key = doc.get('user_input', '').lower().strip()
                is_dup = False
                for prev in seen_content:
                    if content_key and prev and self._is_similar_memory(content_key, prev):
                        is_dup = True
                        break
                if not is_dup:
                    primary_hits.append((idx, float(score)))
                    if content_key:
                        seen_content.append(content_key)

            if not primary_hits:
                return []

            # Context window expansion + recency scoring + time boosting
            expanded_memories = []
            seen_indices = set()

            for start_index, similarity in primary_hits:
                if include_context:
                    context_start = max(start_index - self.context_window_size, 0)
                    context_end = min(start_index + self.context_window_size + 1, num_docs)

                    for idx in range(context_start, context_end):
                        if idx not in seen_indices:
                            mem_doc = documents[idx]
                            recency_score = self._calculate_recency_score(mem_doc)
                            time_boost = self._calculate_time_boost(mem_doc, time_target, time_window) if time_target else 1.0

                            if idx == start_index:
                                combined_score = (0.8 * similarity + 0.2 * recency_score) * time_boost
                            else:
                                combined_score = (0.5 * similarity + 0.5 * recency_score) * time_boost

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
                    mem_doc = documents[start_index]
                    recency_score = self._calculate_recency_score(mem_doc)
                    time_boost = self._calculate_time_boost(mem_doc, time_target, time_window) if time_target else 1.0
                    combined_score = (0.7 * similarity + 0.3 * recency_score) * time_boost

                    expanded_memories.append({
                        'document': mem_doc,
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

            speaker = doc.get('speaker', '')
            speaker_label = speaker if (speaker and not speaker.startswith("Unknown")) else "User"
            if user_input and bot_response:
                formatted_parts.append(
                    f"{relevance_marker} [{relative_time}]\n"
                    f"  {speaker_label}: {user_input}\n"
                    f"  {self.char_name}: {bot_response}\n"
                )
            elif bot_response:
                formatted_parts.append(
                    f"{relevance_marker} [{relative_time}] {bot_response}\n"
                )

        formatted_parts.append("=== End of Past Conversations ===\n")
        return "\n".join(formatted_parts)

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

    def get_longterm_memory(self, user_input: str) -> str:
        try:
            if not self.long_mem_use:
                return ""

            context_parts = []

            # Transient activities (last 4h) — bridges the gap between
            # short-term conversation and permanent topics
            activity_ctx = self.get_current_activities(max_age_hours=4)
            if activity_ctx:
                context_parts.append(activity_ctx)
                context_parts.append("")

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
        """Episodic summary: what happened in the last N hours, grouped by time.

        Includes both user input and a truncated bot response so the LLM
        gets real context (not just a list of questions).
        """
        try:
            documents = self.hyper_db.documents
            cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

            today_entries = []
            yesterday_entries = []
            older_entries = []
            now = datetime.now()

            for doc in reversed(documents):
                timestamp = self._parse_timestamp(doc)
                if not timestamp or timestamp < cutoff_time:
                    continue
                user_input = doc.get('user_input', '')
                if not user_input:
                    continue

                # Truncate bot response to keep summary compact
                bot_short = doc.get('bot_response', '')
                if len(bot_short) > 60:
                    bot_short = bot_short[:57] + "..."

                entry = f"{user_input} -> {bot_short}" if bot_short else user_input

                # Skip near-duplicate entries (user asked same thing multiple times)
                all_so_far = today_entries + yesterday_entries + older_entries
                if any(self._is_similar_memory(user_input, prev.split(' -> ')[0]) for prev in all_so_far if prev):
                    continue

                delta = now - timestamp
                if delta.days == 0:
                    today_entries.append(entry)
                elif delta.days == 1:
                    yesterday_entries.append(entry)
                else:
                    older_entries.append(entry)

                if len(today_entries) + len(yesterday_entries) + len(older_entries) >= 12:
                    break

            if not today_entries and not yesterday_entries and not older_entries:
                return ""

            parts = []
            if today_entries:
                parts.append("Today: " + " | ".join(today_entries[:5]))
            if yesterday_entries:
                parts.append("Yesterday: " + " | ".join(yesterday_entries[:4]))
            if older_entries:
                parts.append("Earlier: " + " | ".join(older_entries[:3]))

            return "Recent activity: " + "\n  ".join(parts)

        except Exception:
            return ""

    def get_shortterm_memories_recent(self, max_entries: int) -> List[str]:
        return self.hyper_db.documents[-max_entries:]

    def get_shortterm_memories_tokenlimit(self, token_limit: int) -> str:
        accumulated_documents = []
        accumulated_length = 0

        for doc in reversed(self.hyper_db.documents):
            user_input = doc.get('user_input', "")
            bot_response = doc.get('bot_response', "")
            timestamp = doc.get('timestamp', "")
            speaker = doc.get('speaker', "")

            if not user_input or not bot_response:
                continue

            time_label = self._get_relative_time(timestamp) if timestamp else ""
            time_prefix = f"[{time_label}] " if time_label else ""

            # Use stored speaker name if available, otherwise fall back to {user} placeholder
            speaker_tag = speaker if (speaker and not speaker.startswith("Unknown")) else "{user}"
            text_str = f"{time_prefix}{speaker_tag}: {user_input}\n{{char}}: {bot_response}"
            # Fast approximation (~4 chars per token) to avoid expensive encoding per entry
            approx_tokens = len(text_str) // 4
            # Only do exact count when we're close to the limit (within 20%)
            if accumulated_length + approx_tokens > token_limit * 0.8:
                text_length = self.token_count(text_str)['length']
            else:
                text_length = approx_tokens

            if accumulated_length + text_length > token_limit:
                break

            accumulated_documents.append((user_input, bot_response, time_prefix, speaker_tag))
            accumulated_length += text_length

        formatted_output = '\n'.join(
            [f"{tp}{spk}: {ui}\n{{char}}: {br}" for ui, br, tp, spk in reversed(accumulated_documents)]
        )
        return formatted_output

    def write_tool_used(self, toolused: str):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        document = {
            "timestamp": current_time,
            "bot_response": toolused
        }
        self.hyper_db.add_document(document)
        self._mark_dirty()

    def load_initial_memory(self, json_file_path: str):
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

    def _get_tiktoken_encoder(self):
        """Return a cached tiktoken encoder, creating it once on first call."""
        if hasattr(self, '_tiktoken_enc'):
            return self._tiktoken_enc

        import tiktoken
        llm_backend = self.config['LLM']['llm_backend']
        override_encoding_model = self.config['LLM'].get('override_encoding_model', "cl100k_base")

        if llm_backend == "deepinfra":
            self._tiktoken_enc = tiktoken.get_encoding(override_encoding_model)
        else:
            if llm_backend == "other":
                model_name = self.config['LLM'].get('other_model', None) or self.config['LLM'].get('openai_model', None)
            else:
                model_name = self.config['LLM'].get('openai_model', None)
            try:
                self._tiktoken_enc = tiktoken.encoding_for_model(model_name)
            except KeyError:
                self._tiktoken_enc = tiktoken.get_encoding(override_encoding_model)

        return self._tiktoken_enc

    def token_count(self, text: str) -> dict:
        llm_backend = self.config['LLM']['llm_backend']

        if llm_backend == "grok":
            word_count = len(text.split())
            estimated_tokens = int(word_count / 0.75)
            return {"length": estimated_tokens}

        elif llm_backend in ["openai", "deepinfra", "other"]:
            try:
                enc = self._get_tiktoken_encoder()
                return {"length": len(enc.encode(text))}
            except Exception as e:
                if not hasattr(self, '_token_error_logged'):
                    queue_message(f"ERROR: Failed to calculate tokens using tiktoken: {e}")
                    self._token_error_logged = True
                return {"length": 0}

        else:
            queue_message(f"ERROR: Unsupported LLM backend: {llm_backend}")
            return {"length": 0}