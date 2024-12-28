import gzip
import pickle
import numpy as np
import random
import requests
from typing import List, Union

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
    ):
        self.documents = documents or []
        self.documents = []
        self.vectors = None
        self.embedding_function = embedding_function or (
            #lambda docs: get_embedding(docs, key=key)
            lambda docs: get_embedding(docs)
        )
        if vectors is not None:
            self.vectors = vectors
            self.documents = documents
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

    def add_documents(self, documents, vectors=None):
        if not documents:
            return
        vectors = vectors or np.array(self.embedding_function(documents)).astype(
            np.float32
        )
        for vector, document in zip(vectors, documents):
            self.add_document(document, vector)

    def remove_document(self, index):
        self.vectors = np.delete(self.vectors, index, axis=0)
        self.documents.pop(index)

    def save(self, storage_file):
        data = {"vectors": self.vectors, "documents": self.documents}
        if storage_file.endswith(".gz"):
            with gzip.open(storage_file, "wb") as f:
                pickle.dump(data, f)
        else:
            with open(storage_file, "wb") as f:
                pickle.dump(data, f)

    def load(self, storage_file):
        #print(f"loading {storage_file}")
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
            return True  # Indicate successful loading

        except Exception as e:
            print(f"Error loading memory: {e}")
            import traceback
            traceback.print_exc()  # Print detailed traceback for debugging
            return False

    def query(self, query_text, top_k=5, return_similarities=True):
        query_vector = self.embedding_function([query_text])[0]
        ranked_results, similarities = hyper_SVM_ranking_algorithm_sort(
            self.vectors, query_vector, top_k=top_k, metric=self.similarity_metric
        )
        if return_similarities:
            return list(
                zip([self.documents[index] for index in ranked_results], similarities)
            )
        return [self.documents[index] for index in ranked_results]