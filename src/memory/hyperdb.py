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

import configparser

from module_config import get_api_key

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

                #print("Embeddings:", formatted_embeddings)
                return formatted_embeddings
            else:
                print("Error: 'data' key not found in API response.")
                return None
        except KeyError:
            print("Error: 'data' key not found in API response.")
            return None
    else:
        print("Error:", response.status_code, response.text)
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

        # Initialize BM25 components
        print(f"INFO: Initializing HyperDB with {rag_strategy} RAG strategy")
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
            print("Error: Unable to get embeddings for the document.")
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
            print("Error: Unable to get embeddings for the document.")
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
        """Save the database to a file"""
        data = {
            "vectors": self.vectors,
            "documents": self.documents,
        }
        # Only save corpus_texts if they exist (for hybrid compatibility)
        if hasattr(self, 'corpus_texts') and self.corpus_texts:
            data["corpus_texts"] = self.corpus_texts

        if storage_file.endswith(".gz"):
            with gzip.open(storage_file, "wb") as f:
                pickle.dump(data, f)
        else:
            with open(storage_file, "wb") as f:
                pickle.dump(data, f)

    def load(self, storage_file: str) -> bool:
        """Load the database from a file"""
        try:
            if storage_file.endswith(".gz"):
                with gzip.open(storage_file, "rb") as f:
                    data = pickle.load(f)
            else:
                with open(storage_file, "rb") as f:
                    data = pickle.load(f)

            if "vectors" in data and data["vectors"] is not None:
                self.vectors = data["vectors"].astype(np.float32)
            else:
                self.vectors = None

            self.documents = data.get("documents", [])
            
            # Load corpus_texts if they exist (for hybrid compatibility)
            if "corpus_texts" in data:
                self.corpus_texts = data["corpus_texts"]
                
            # Re-initialize BM25 if we're in hybrid mode and have documents
            if self.rag_strategy == "hybrid" and self.documents:
                self._init_bm25_index()
                
            return True

        except Exception as e:
            print(f"Error loading memory: {e}")
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
            return self.hybrid_query(query_text, top_k, vector_weight=0.5, return_similarities=return_similarities)

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

    def hybrid_query(
        self, 
        query_text: str, 
        top_k: int = 5, 
        vector_weight: float = 0.5, 
        return_similarities: bool = True
    ):
        """
        The hybrid search combines vector similarity and BM25 scoring through these steps:
        
        1. Vector Search:
        - Convert query to vector using embedding model
        - Calculate similarity scores with document vectors
        - Get top_k * 2 results to have a larger candidate pool
        
        2. BM25 Search:
        - Tokenize query text
        - Calculate BM25 scores for documents
        - Get top_k * 2 results
        
        3. Score Normalization:
        - Normalize both vector and BM25 scores to 0-1 range
        - This makes scores comparable regardless of their original scales
        
        4. Score Combination:
        - For each document found by either method:
            * Final_Score = (vector_weight × Vector_Score) + 
                            ((1 - vector_weight) × BM25_Score)
        - This weighted sum combines both relevance signals
        
        5. Final Ranking:
        - Sort documents by combined scores
        - Return top_k results
        """
        if self.rag_strategy != "hybrid":
            print("Warning: Hybrid query called but RAG strategy is 'naive'. Falling back to vector search.")
            return self._vector_query(query_text, top_k, return_similarities)

        # Get vector search results
        query_vector = self.embedding_function([query_text])[0]
        vector_results, vector_scores = hyper_SVM_ranking_algorithm_sort(
            self.vectors, query_vector, top_k=top_k * 2, metric=self.similarity_metric
        )
        
        # Get BM25 results
        query_tokens = bm25s.tokenize([query_text], stopwords="en", stemmer=self.stemmer)
        bm25_results, bm25_scores = self.bm25_retriever.retrieve(query_tokens, k=top_k * 2)
        bm25_results = bm25_results[0]  # First query's results
        bm25_scores = bm25_scores[0]    # First query's scores
        
        # Normalize scores to 0-1 range
        if len(vector_scores) > 0:
            vector_scores = (vector_scores - np.min(vector_scores)) / (np.max(vector_scores) - np.min(vector_scores) + 1e-6)
        if len(bm25_scores) > 0:
            bm25_scores = (bm25_scores - np.min(bm25_scores)) / (np.max(bm25_scores) - np.min(bm25_scores) + 1e-6)
        
        # Combine results
        doc_scores = {}
        for idx, score in zip(vector_results, vector_scores):
            doc_scores[idx] = vector_weight * score
            
        for idx, score in zip(bm25_results, bm25_scores):
            if idx in doc_scores:
                doc_scores[idx] += (1 - vector_weight) * score
            else:
                doc_scores[idx] = (1 - vector_weight) * score
                
        # Sort and get top results
        ranked_results = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        if return_similarities:
            return [(self.documents[idx], score) for idx, score in ranked_results]
        return [self.documents[idx] for idx, score in ranked_results]