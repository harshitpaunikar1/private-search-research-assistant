"""
Private on-premises document retriever for the research assistant.
Indexes local documents with sentence embeddings and performs semantic search.
"""
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False


@dataclass
class Document:
    doc_id: str
    title: str
    content: str
    source_path: str
    doc_type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    doc_id: str
    title: str
    snippet: str
    source_path: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class DocumentLoader:
    """Loads text and markdown documents from a local directory."""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".rst", ".csv"}

    def load_file(self, file_path: str) -> Optional[Document]:
        path = Path(file_path)
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return None
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            content = self._clean(content)
            if len(content.split()) < 20:
                return None
            doc_id = hashlib.md5(str(path).encode()).hexdigest()[:16]
            return Document(
                doc_id=doc_id,
                title=path.stem.replace("_", " ").replace("-", " ").title(),
                content=content,
                source_path=str(path),
                doc_type=path.suffix.lstrip("."),
            )
        except Exception as exc:
            logger.error("Failed to load %s: %s", file_path, exc)
            return None

    def load_directory(self, directory: str) -> List[Document]:
        docs = []
        for path in Path(directory).rglob("*"):
            if path.is_file():
                doc = self.load_file(str(path))
                if doc:
                    docs.append(doc)
        return docs

    def _clean(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()


class TextChunker:
    """Splits documents into overlapping chunks for embedding."""

    def __init__(self, chunk_size: int = 400, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, doc: Document) -> List[Tuple[str, str, int]]:
        """Return list of (chunk_id, chunk_text, chunk_index)."""
        words = doc.content.split()
        chunks = []
        start = 0
        idx = 0
        while start < len(words):
            end = min(start + self.chunk_size, len(words))
            chunk_text = " ".join(words[start:end])
            chunk_id = f"{doc.doc_id}_{idx}"
            chunks.append((chunk_id, chunk_text, idx))
            start += self.chunk_size - self.overlap
            idx += 1
        return chunks


class LocalEmbedder:
    """Generates embeddings locally using sentence transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def _load(self) -> None:
        if not ST_AVAILABLE or self._model is not None:
            return
        self._model = SentenceTransformer(self.model_name)

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._load()
        if self._model is None:
            rng = np.random.default_rng(42)
            return [rng.standard_normal(384).tolist() for _ in texts]
        return self._model.encode(texts, show_progress_bar=False).tolist()


class PrivateRetriever:
    """
    Indexes private documents locally and retrieves semantically relevant chunks.
    No data leaves the local machine.
    """

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2",
                 qdrant_url: str = "http://localhost:6333",
                 collection_name: str = "private_docs",
                 vector_dim: int = 384,
                 chunk_size: int = 400):
        self.embedder = LocalEmbedder(model_name=embedding_model)
        self.chunker = TextChunker(chunk_size=chunk_size)
        self.qdrant_url = qdrant_url
        self.collection_name = collection_name
        self.vector_dim = vector_dim
        self._client = None
        self._in_memory_index: List[Tuple[str, str, str, List[float]]] = []
        self._doc_store: Dict[str, Document] = {}

    def _connect(self) -> bool:
        if not QDRANT_AVAILABLE:
            return False
        try:
            self._client = QdrantClient(url=self.qdrant_url)
            colls = [c.name for c in self._client.get_collections().collections]
            if self.collection_name not in colls:
                self._client.create_collection(
                    self.collection_name,
                    vectors_config=VectorParams(size=self.vector_dim, distance=Distance.COSINE),
                )
            return True
        except Exception:
            return False

    def index(self, docs: List[Document]) -> int:
        total = 0
        for doc in docs:
            self._doc_store[doc.doc_id] = doc
            chunks = self.chunker.chunk(doc)
            texts = [c[1] for c in chunks]
            embeddings = self.embedder.embed(texts)
            if self._client or self._connect():
                points = [
                    PointStruct(
                        id=abs(int(hashlib.md5(chunk_id.encode()).hexdigest(), 16)) % (2**63),
                        vector=emb,
                        payload={"doc_id": doc.doc_id, "title": doc.title,
                                 "source_path": doc.source_path,
                                 "chunk_index": idx, "text": text[:500]},
                    )
                    for (chunk_id, text, idx), emb in zip(chunks, embeddings)
                ]
                self._client.upsert(collection_name=self.collection_name, points=points)
                total += len(points)
            else:
                for (chunk_id, text, idx), emb in zip(chunks, embeddings):
                    self._in_memory_index.append((doc.doc_id, doc.title, text, emb))
                total += len(chunks)
        logger.info("Indexed %d chunks from %d documents.", total, len(docs))
        return total

    def _cosine_sim(self, a: List[float], b: List[float]) -> float:
        a_arr = np.array(a)
        b_arr = np.array(b)
        denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        return float(np.dot(a_arr, b_arr) / denom) if denom > 0 else 0.0

    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        query_vec = self.embedder.embed([query])[0]
        if self._client:
            try:
                hits = self._client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vec,
                    limit=top_k,
                )
                return [
                    SearchResult(
                        doc_id=h.payload["doc_id"],
                        title=h.payload["title"],
                        snippet=h.payload["text"][:300],
                        source_path=h.payload["source_path"],
                        score=round(h.score, 4),
                    )
                    for h in hits
                ]
            except Exception as exc:
                logger.error("Qdrant search failed: %s", exc)
        if self._in_memory_index:
            scored = [
                (doc_id, title, text, self._cosine_sim(query_vec, emb))
                for doc_id, title, text, emb in self._in_memory_index
            ]
            scored.sort(key=lambda x: x[3], reverse=True)
            return [
                SearchResult(doc_id=doc_id, title=title, snippet=text[:300],
                             source_path=self._doc_store.get(doc_id, Document("", "", "", "")).source_path,
                             score=round(score, 4))
                for doc_id, title, text, score in scored[:top_k]
            ]
        return []

    def index_directory(self, directory: str) -> int:
        loader = DocumentLoader()
        docs = loader.load_directory(directory)
        logger.info("Loaded %d documents from %s", len(docs), directory)
        return self.index(docs)

    def stats(self) -> Dict:
        return {
            "docs_indexed": len(self._doc_store),
            "in_memory_chunks": len(self._in_memory_index),
            "qdrant_connected": self._client is not None,
        }


if __name__ == "__main__":
    retriever = PrivateRetriever(
        embedding_model="all-MiniLM-L6-v2",
        collection_name="private_research",
    )
    from document_loader_stub import Document
    sample_docs = [
        Document("d001", "Machine Learning Basics", "Supervised learning involves training a model on labeled data to make predictions. Common algorithms include linear regression, decision trees, and neural networks.", "/docs/ml_basics.txt"),
        Document("d002", "Deep Learning Overview", "Deep learning uses multi-layer neural networks to learn hierarchical representations. Applications include computer vision, NLP, and speech recognition.", "/docs/dl_overview.txt"),
        Document("d003", "NLP Fundamentals", "Natural language processing enables machines to understand human language. Key tasks include tokenization, named entity recognition, and sentiment analysis.", "/docs/nlp.txt"),
    ]
    for doc in sample_docs:
        retriever._doc_store[doc.doc_id] = doc
        chunks = retriever.chunker.chunk(doc)
        texts = [c[1] for c in chunks]
        embeddings = retriever.embedder.embed(texts)
        for (chunk_id, text, idx), emb in zip(chunks, embeddings):
            retriever._in_memory_index.append((doc.doc_id, doc.title, text, emb))

    results = retriever.search("What algorithms are used in machine learning?", top_k=3)
    print("Search results for 'What algorithms are used in machine learning?':")
    for r in results:
        print(f"  [{r.score:.3f}] {r.title}: {r.snippet[:100]}...")
    print("\nStats:", retriever.stats())
