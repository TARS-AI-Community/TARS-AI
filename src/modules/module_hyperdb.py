# MIT License
# 
# Copyright (c) [YEAR] [YOUR NAME]
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
import gzip
import pickle
import numpy as np
import random
import requests
from typing import List, Union
import bm25s
import Stemmer
from sentence_transformers import CrossEncoder
import configparser
import torch

from modules.module_config import get_api_key
from modules.module_messageQue import queue_message

config = configparser.ConfigParser()
config.read('config.ini')

def get_embedding_new(documents):
    base_url = config.getboolean('LLM', 'base_url')  # Replace with your API base URL
    api_key = get_api_key(config['LLM']['llm_backend'])
    encoding_format = "text/plain"
    
    url = f"{base_url}/v1/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    if isinstance(documents, str):
        documents = [documents]

    data = {
        "input": documents,
        "encoding_format": encoding_format
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        try:
            # Assuming the API response contains a list of embeddings under 'data'
            embeddings_list = response.json().get("data", [])
            if embeddings_list:
                embeddings = [embedding["embedding"] for embedding in embeddings_list]

                # Format embeddings in scientific notation
                formatted_embeddings = [[f"{val:0.8e}" for val in embedding] for embedding in embeddings]

                #queue_message("Embeddings:", formatted_embeddings)
                return formatted_embeddings
            else:
                queue_message("Error: 'data' key not found in API response.")
                return None
        except KeyError:
            queue_message("Error: 'data' key not found in API response.")
            return None
    else:
        queue_message("Error:", response.status_code, response.text)
        return None

from sentence_transformers import SentenceTransformer
EMBEDDING_MODEL = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu')

def get_embedding(documents, key=None):
    """Default embedding function that uses OpenAI Embeddings."""
    if isinstance(documents, list):
        if isinstance(documents[0], dict):
            texts = []
            if isinstance(key, str):
                if "." in key:
                    key_chain = key.split(".")
                else:
                    key_chain = [key]
                for doc in documents:
                    for key in key_chain:
                        doc = doc[key]
                    texts.append(doc.replace("\n", " "))
            elif key is None:
                for doc in documents:
                    text = ", ".join([f"{key}: {value}" for key, value in doc.items()])
                    texts.append(text)
        elif isinstance(documents[0], str):
            texts = documents

    embeddings = EMBEDDING_MODEL.encode(texts)
    return embeddings

def get_norm_vector(vector):
    if len(vector.shape) == 1:
        return vector / np.linalg.norm(vector)
    else:
        return vector / np.linalg.norm(vector, axis=1)[:, np.newaxis]

def dot_product(vectors, query_vector):
    similarities = np.dot(vectors, query_vector.T)
    return similarities

def cosine_similarity(vectors, query_vector):
    norm_vectors = get_norm_vector(vectors)
    norm_query_vector = get_norm_vector(query_vector)
    similarities = np.dot(norm_vectors, norm_query_vector.T)
    return similarities

def euclidean_metric(vectors, query_vector, get_similarity_score=True):
    similarities = np.linalg.norm(vectors - query_vector, axis=1)
    if get_similarity_score:
        similarities = 1 / (1 + similarities)
    return similarities

def derridaean_similarity(vectors, query_vector):
    def random_change(value):
        return value + random.uniform(-0.2, 0.2)

    similarities = cosine_similarity(vectors, query_vector)
    derrida_similarities = np.vectorize(random_change)(similarities)
    return derrida_similarities

def adams_similarity(vectors, query_vector):
    def adams_change(value):
        return 0.42

    similarities = cosine_similarity(vectors, query_vector)
    adams_similarities = np.vectorize(adams_change)(similarities)
    return adams_similarities

def hyper_SVM_ranking_algorithm_sort(vectors, query_vector, top_k=5, metric=cosine_similarity):
    """HyperSVMRanking (Such Vector, Much Ranking) algorithm proposed by Andrej Karpathy (2023) https://arxiv.org/abs/2303.18231"""
    similarities = metric(vectors, query_vector)
    top_indices = np.argsort(similarities, axis=0)[-top_k:][::-1]
    return top_indices.flatten(), similarities[top_indices].flatten()
  
class HyperDB:
    def __init__(
        self,
        documents=None,
        vectors=None,
        key=None,
        embedding_function=None,
        similarity_metric="cosine",
        rag_strategy="naive",
    ):
        """
            Initialize HyperDB with configurable RAG strategy.

            Parameters:
            - documents: Initial documents to index
            - vectors: Pre-computed vectors for documents
            - key: Key to extract text from documents
            - embedding_function: Function to compute embeddings
            - similarity_metric: Metric for vector similarity
            - rag_strategy: 'naive' for vector-only or 'hybrid' for vector+BM25
        """
        self.documents = documents or []
        self.documents = []
        self.vectors = None
        self.embedding_function = embedding_function or (
            #lambda docs: get_embedding(docs, key=key)
            lambda docs: get_embedding(docs)
        )
        self.rag_strategy = rag_strategy

        if rag_strategy == "hybrid":
            try:
                self.reranker = CrossEncoder(
                    'BAAI/bge-reranker-base',
                    device='cuda' if torch.cuda.is_available() else 'cpu', 
                    max_length=256,
                )
                queue_message("INFO: BGE reranker model loaded successfully")
            except Exception as e:
                queue_message(f"WARNING: Failed to load BGE reranker model: {e}")
                self.reranker = None

        # Initialize BM25 components
        queue_message(f"INFO: Initializing HyperDB with {rag_strategy} RAG strategy")
        if self.rag_strategy == "hybrid":
            self.stemmer = Stemmer.Stemmer("english")
            self.bm25_retriever = bm25s.BM25(method="lucene")
            self.corpus_tokens = None
            self.corpus_texts = []
        else:
            self.stemmer = None
            self.bm25_retriever = None
            self.corpus_tokens = None
            self.corpus_texts = None

        if vectors is not None:
            self.vectors = vectors
            self.documents = documents
            if self.rag_strategy == "hybrid" and documents:
                self._init_bm25_index()
        else:
            self.add_documents(documents)

        if similarity_metric.__contains__("dot"):
            self.similarity_metric = dot_product
        elif similarity_metric.__contains__("cosine"):
            self.similarity_metric = cosine_similarity
        elif similarity_metric.__contains__("euclidean"):
            self.similarity_metric = euclidean_metric
        elif similarity_metric.__contains__("derrida"):
            self.similarity_metric = derridaean_similarity
        elif similarity_metric.__contains__("adams"):
            self.similarity_metric = adams_similarity
        else:
            raise Exception(
                "Similarity metric not supported. Please use either 'dot', 'cosine', 'euclidean', 'adams', or 'derrida'."
            )

    def _init_bm25_index(self):
        """Initialize BM25 index with current documents"""
        if self.rag_strategy != "hybrid":
            return

        self.corpus_texts = []
        for doc in self.documents:
            if isinstance(doc, dict):
                text = ""
                if "user_input" in doc:
                    text += doc["user_input"] + " "
                if "bot_response" in doc:
                    text += doc["bot_response"]
                if not text:  # If no specific fields found, use all text fields
                    text = " ".join(str(v) for v in doc.values() if isinstance(v, (str, int, float)))
            else:
                text = str(doc)
            self.corpus_texts.append(text.strip())
            
        self.corpus_tokens = bm25s.tokenize(self.corpus_texts, stopwords="en", stemmer=self.stemmer)
        self.bm25_retriever.index(self.corpus_tokens)

    def dict(self, vectors=False):
        if vectors:
            return [
                {"document": document, "vector": vector.tolist(), "index": index}
                for index, (document, vector) in enumerate(
                    zip(self.documents, self.vectors)
                )
            ]
        return [
            {"document": document, "index": index}
            for index, document in enumerate(self.documents)
        ]

    def add(self, documents, vectors=None):
        if not isinstance(documents, list):
            return self.add_document(documents, vectors)
        self.add_documents(documents, vectors)

    def add_document_new(self, document: dict, vector=None):
        # These changes were for an old version
        # here I also changed the line:
        # vector = vector or self.embedding_function([document])[0]
        # to:
        # if vector is None:
        #     vector = self.embedding_function([document])
        # else:
        #     vector = vector
        # this is because I ran into an error: "ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()"

        vector = vector if vector is not None else self.embedding_function([document])
        if vector is not None and len(vector) > 0:
            vector = vector[0]
        else:
            # Handle the case where the embedding function returns None or an empty list
            queue_message("Error: Unable to get embeddings for the document.")
            return

        if self.vectors is None:
            self.vectors = np.empty((0, len(vector)), dtype=np.float32)
        elif len(vector) != self.vectors.shape[1]:
            raise ValueError("All vectors must have the same length.")

        self.vectors = np.vstack([self.vectors, vector]).astype(np.float32)
        self.documents.append(document)

    def add_document(self, document: dict, vector=None):

        vector = vector if vector is not None else self.embedding_function([document])
        if vector is not None and len(vector) > 0:
            vector = vector[0]
        else:
            # Handle the case where the embedding function returns None or an empty list
            queue_message("Error: Unable to get embeddings for the document.")
            return

        if self.vectors is None:
            self.vectors = np.empty((0, len(vector)), dtype=np.float32)
        elif len(vector) != self.vectors.shape[1]:
            raise ValueError("All vectors must have the same length.")
        self.vectors = np.vstack([self.vectors, vector]).astype(np.float32)
        self.documents.append(document)

        # Update BM25 index if using hybrid strategy
        if self.rag_strategy == "hybrid":
            self._init_bm25_index()

    def add_documents(self, documents, vectors=None):
        if not documents:
            return
        vectors = vectors or np.array(self.embedding_function(documents)).astype(
            np.float32
        )
        for vector, document in zip(vectors, documents):
            self.add_document(document, vector)

    def remove_document(self, index):
        """Remove a document by its index"""
        self.vectors = np.delete(self.vectors, index, axis=0)
        self.documents.pop(index)
        if self.rag_strategy == "hybrid":
            self.corpus_texts.pop(index)
            self._init_bm25_index()

    def save(self, storage_file: str):
        """
        Save the database state - only save essential data (vectors and documents).
        The RAG strategy is a runtime configuration and should not be persisted.
        """
        data = {
            "vectors": self.vectors,
            "documents": self.documents
        }
        
        try:
            if storage_file.endswith(".gz"):
                with gzip.open(storage_file, "wb") as f:
                    pickle.dump(data, f)
            else:
                with open(storage_file, "wb") as f:
                    pickle.dump(data, f)
        except Exception as e:
            queue_message(f"ERROR: Failed to save database: {e}")

    def load(self, storage_file: str) -> bool:
        """
        Load the database state.
        The RAG strategy remains as configured during initialization.
        """
        try:
            if storage_file.endswith(".gz"):
                with gzip.open(storage_file, "rb") as f:
                    data = pickle.load(f)
            else:
                with open(storage_file, "rb") as f:
                    data = pickle.load(f)

            # Load only vectors and documents
            if "vectors" in data and data["vectors"] is not None:
                self.vectors = data["vectors"].astype(np.float32)
            else:
                self.vectors = None

            self.documents = data.get("documents", [])
            
            # Re-initialize BM25 if we're in hybrid mode
            if self.rag_strategy == "hybrid" and self.documents:
                self._init_bm25_index()
                    
            return True

        except Exception as e:
            queue_message(f"Error loading memory: {e}")
            import traceback
            traceback.print_exc()
            return False

    def query(self, query_text: str, top_k: int = 5, return_similarities: bool = True):
        """
        Query the database using the configured RAG strategy.
        For backward compatibility, this uses either vector-only search or hybrid search
        based on the configured rag_strategy.
        
        Parameters:
            query_text (str): The text to search for
            top_k (int): Number of results to return
            return_similarities (bool): Whether to return similarity scores
            
        Returns:
            List of documents or (document, score) tuples if return_similarities is True
        """
        if self.rag_strategy == "naive":
            return self._vector_query(query_text, top_k, return_similarities)
        else:  # hybrid
            return self.hybrid_query(query_text, top_k, return_similarities=return_similarities)

    def _vector_query(self, query_text: str, top_k: int = 5, return_similarities: bool = True):
        """
        Perform vector-only search.
        
        Parameters:
            query_text (str): The text to search for
            top_k (int): Number of results to return
            return_similarities (bool): Whether to return similarity scores
            
        Returns:
            List of documents or (document, score) tuples if return_similarities is True
        """
        query_vector = self.embedding_function([query_text])[0]
        ranked_results, similarities = hyper_SVM_ranking_algorithm_sort(
            self.vectors, query_vector, top_k=top_k, metric=self.similarity_metric
        )
        if return_similarities:
            return list(
                zip([self.documents[index] for index in ranked_results], similarities)
            )
        return [self.documents[index] for index in ranked_results]

    def _rerank_results(self, query: str, candidate_docs: list) -> list:
        """
        Rerank candidate documents using the BGE reranker model.
        
        Parameters:
        - query: The search query
        - candidate_docs: List of candidate documents to rerank
        
        Returns:
        - List of (doc, score) tuples after reranking
        """
        if not hasattr(self, 'reranker') or not self.reranker or not candidate_docs:
            return candidate_docs

        try:
            # Prepare pairs for reranking
            pairs = []
            for doc in candidate_docs:
                # Extract text from document based on its type
                if isinstance(doc, dict):
                    text = ""
                    if "user_input" in doc:
                        text += doc["user_input"] + " "
                    if "bot_response" in doc:
                        text += doc["bot_response"]
                    if not text:  # If no specific fields found, use all text fields
                        text = " ".join(str(v) for v in doc.values() if isinstance(v, (str, int, float)))
                else:
                    text = str(doc)
                # Format pairs for CrossEncoder
                pairs.append([query, text])

            scores = self.reranker.predict(pairs)
            
            # Ensure scores are in the right format
            if isinstance(scores, (list, np.ndarray)):
                rerank_scores = [float(score) for score in scores]
            else:
                rerank_scores = [float(scores)]

            # Safety check for scores
            if len(rerank_scores) != len(candidate_docs):
                queue_message(f"WARNING: Mismatch between scores ({len(rerank_scores)}) and docs ({len(candidate_docs)})")
                return candidate_docs
            
            # Sort documents by reranking scores
            reranked_results = list(zip(candidate_docs, rerank_scores))
            reranked_results.sort(key=lambda x: x[1], reverse=True)
            
            return reranked_results
            
        except Exception as e:
            queue_message(f"WARNING: Reranking failed: {e}. Returning original order.")
            import traceback
            traceback.print_exc()
            return candidate_docs

    def hybrid_query(
        self, 
        query_text: str, 
        top_k: int = 5, 
        return_similarities: bool = True,
        rrf_k: int = 60
    ):
        """
        Hybrid search using RRF fusion and BGE reranker.
        The pipeline: vector search -> BM25 -> RRF fusion -> BGE reranking.
        """
        if not self.documents or not self.vectors.size:
            queue_message("WARNING: Empty database, returning empty results")
            return [] if not return_similarities else []

        if self.rag_strategy != "hybrid":
            queue_message("WARNING: Hybrid query called but RAG strategy is 'naive'. Falling back to vector search.")
            return self._vector_query(query_text, top_k, return_similarities)

        try:
            # Vector Search
            query_vector = self.embedding_function([query_text])[0]
            vector_results, vector_scores = hyper_SVM_ranking_algorithm_sort(
                self.vectors, query_vector, top_k=min(top_k * 2, len(self.documents)), 
                metric=self.similarity_metric
            )
            
            # BM25 Search
            query_tokens = bm25s.tokenize([query_text], stopwords="en", stemmer=self.stemmer)
            bm25_results, bm25_scores = self.bm25_retriever.retrieve(query_tokens, k=min(top_k * 2, len(self.documents)))
            
            # Validate BM25 results
            if not isinstance(bm25_results, (list, np.ndarray)) or not isinstance(bm25_scores, (list, np.ndarray)):
                queue_message("WARNING: Invalid BM25 results format, falling back to vector search")
                return self._vector_query(query_text, top_k, return_similarities)

            try:
                bm25_results = bm25_results[0]
                bm25_scores = bm25_scores[0]
            except (IndexError, TypeError) as e:
                queue_message(f"WARNING: Error processing BM25 results: {e}")
                return self._vector_query(query_text, top_k, return_similarities)

            # RRF Fusion
            vector_ranks = {doc_id: rank + 1 for rank, doc_id in enumerate(vector_results) 
                        if isinstance(doc_id, (int, np.integer)) and doc_id < len(self.documents)}
            bm25_ranks = {doc_id: rank + 1 for rank, doc_id in enumerate(bm25_results) 
                        if isinstance(doc_id, (int, np.integer)) and doc_id < len(self.documents)}

            if not vector_ranks and not bm25_ranks:
                queue_message("WARNING: No valid ranks found")
                return self._vector_query(query_text, top_k, return_similarities)

            # Calculate RRF scores
            rrf_scores = {}
            all_doc_ids = set(vector_ranks.keys()) | set(bm25_ranks.keys())
            
            for doc_id in all_doc_ids:
                if not isinstance(doc_id, (int, np.integer)) or doc_id >= len(self.documents):
                    continue
                vector_rank = vector_ranks.get(doc_id, len(self.documents) + 1)
                bm25_rank = bm25_ranks.get(doc_id, len(self.documents) + 1)
                rrf_score = (1 / (rrf_k + vector_rank)) + (1 / (rrf_k + bm25_rank))
                rrf_scores[doc_id] = rrf_score

            # Reranking
            rrf_ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
            rrf_ranked = rrf_ranked[:min(top_k * 2, len(rrf_ranked))]
            
            # Create candidate docs
            candidate_docs = []
            valid_indices = []
            for idx, score in rrf_ranked:
                if isinstance(idx, (int, np.integer)) and idx < len(self.documents):
                    candidate_docs.append(self.documents[idx])
                    valid_indices.append(idx)

            if not candidate_docs:
                queue_message("WARNING: No valid candidates for reranking")
                return self._vector_query(query_text, top_k, return_similarities)

            # Apply reranking
            reranked_results = self._rerank_results(query_text, candidate_docs)
            
            # Process results
            try:
                if reranked_results and isinstance(reranked_results[0], tuple):
                    final_results = reranked_results[:min(top_k, len(reranked_results))]

                    if return_similarities:
                        return final_results
                    return [doc for doc, _ in final_results]
                else:
                    queue_message("WARNING: Reranking failed, using RRF results")
                    candidate_docs = candidate_docs[:min(top_k, len(candidate_docs))]
                    if return_similarities:
                        return [(doc, rrf_scores[idx]) for doc, idx in zip(candidate_docs, valid_indices[:len(candidate_docs)])]
                    return candidate_docs

            except (IndexError, TypeError) as e:
                queue_message(f"WARNING: Error processing results: {e}")
                candidate_docs = candidate_docs[:min(top_k, len(candidate_docs))]
                if return_similarities:
                    return [(doc, rrf_scores[idx]) for doc, idx in zip(candidate_docs, valid_indices[:len(candidate_docs)])]
                return candidate_docs

        except Exception as e:
            queue_message(f"WARNING: Hybrid query failed: {e}")
            import traceback
            traceback.print_exc()
            return self._vector_query(query_text, top_k, return_similarities)
