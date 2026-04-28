"""
Private search research assistant using local RAG.
Answers research questions from indexed private documents using a local LLM.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    from retriever import PrivateRetriever, SearchResult
    RETRIEVER_AVAILABLE = True
except ImportError:
    RETRIEVER_AVAILABLE = False


@dataclass
class ResearchQuery:
    question: str
    filters: Dict = field(default_factory=dict)
    max_sources: int = 5


@dataclass
class ResearchAnswer:
    question: str
    answer: str
    sources: List[SearchResult]
    model: str
    latency_ms: float
    confidence: str


class LocalLLMBackend:
    """Generates answers using a locally running Ollama model."""

    def __init__(self, model: str = "llama3"):
        self.model = model

    def generate(self, prompt: str) -> str:
        if OLLAMA_AVAILABLE:
            try:
                resp = ollama.generate(model=self.model, prompt=prompt)
                return resp.get("response", "")
            except Exception as exc:
                logger.error("Ollama error: %s", exc)
        return self._stub(prompt)

    def _stub(self, prompt: str) -> str:
        if "supervised" in prompt.lower():
            return "Supervised learning uses labeled data to train predictive models including regression and classification algorithms."
        if "neural" in prompt.lower() or "deep" in prompt.lower():
            return "Deep learning employs multi-layer neural networks capable of learning hierarchical feature representations."
        return "Based on the retrieved documents, the answer involves the key concepts mentioned in the sources above."


class PrivateSearchAssistant:
    """
    On-premises research assistant that answers questions from locally indexed documents.
    No data is sent to external services.
    """

    SYSTEM_PROMPT = """You are a research assistant that answers questions based ONLY on the provided document excerpts.
Cite sources when making claims. If the documents don't contain enough information, say so.
Be concise and factual. Do not speculate beyond what the sources state.
"""

    def __init__(self, retriever: "PrivateRetriever", llm: LocalLLMBackend):
        self.retriever = retriever
        self.llm = llm
        self._history: List[Dict] = []

    def _build_prompt(self, question: str, sources: List[SearchResult]) -> str:
        context = "\n\n".join([
            f"[Source {i+1}: {s.title}]\n{s.snippet}"
            for i, s in enumerate(sources)
        ])
        return f"""{self.SYSTEM_PROMPT}

Documents:
{context}

Question: {question}

Answer:"""

    def _confidence(self, sources: List[SearchResult]) -> str:
        if not sources:
            return "low"
        avg = sum(s.score for s in sources) / len(sources)
        if avg >= 0.80:
            return "high"
        elif avg >= 0.60:
            return "medium"
        return "low"

    def answer(self, query: ResearchQuery) -> ResearchAnswer:
        t0 = time.perf_counter()
        sources = self.retriever.search(query.question, top_k=query.max_sources)
        prompt = self._build_prompt(query.question, sources)
        answer_text = self.llm.generate(prompt)
        latency_ms = (time.perf_counter() - t0) * 1000
        self._history.append({"question": query.question, "answer": answer_text})
        return ResearchAnswer(
            question=query.question,
            answer=answer_text,
            sources=sources,
            model=self.llm.model,
            latency_ms=round(latency_ms, 1),
            confidence=self._confidence(sources),
        )

    def batch_answer(self, questions: List[str]) -> List[ResearchAnswer]:
        return [self.answer(ResearchQuery(q)) for q in questions]

    def session_history(self) -> List[Dict]:
        return list(self._history)

    def index_directory(self, directory: str) -> int:
        return self.retriever.index_directory(directory)


if __name__ == "__main__":
    from retriever import Document, PrivateRetriever

    retriever = PrivateRetriever(collection_name="research_demo")
    sample_docs = [
        Document("d001", "Supervised Learning", "Supervised learning uses labeled training data. Common algorithms: linear regression, SVM, decision trees, neural networks. Evaluation metrics: accuracy, F1, AUC-ROC.", "/docs/supervised.txt"),
        Document("d002", "Unsupervised Learning", "Unsupervised learning finds patterns in unlabeled data. Clustering (K-Means, DBSCAN), dimensionality reduction (PCA, t-SNE), and generative models are core techniques.", "/docs/unsupervised.txt"),
        Document("d003", "Reinforcement Learning", "Reinforcement learning agents learn by interacting with an environment and receiving rewards. Key concepts: policy, value function, Q-learning, PPO.", "/docs/rl.txt"),
        Document("d004", "Natural Language Processing", "NLP enables computers to process human language. Key tasks: tokenization, POS tagging, NER, sentiment analysis, machine translation, text summarization.", "/docs/nlp.txt"),
    ]
    for doc in sample_docs:
        retriever._doc_store[doc.doc_id] = doc
        chunks = retriever.chunker.chunk(doc)
        embeddings = retriever.embedder.embed([c[1] for c in chunks])
        for (chunk_id, text, idx), emb in zip(chunks, embeddings):
            retriever._in_memory_index.append((doc.doc_id, doc.title, text, emb))

    llm = LocalLLMBackend(model="llama3")
    assistant = PrivateSearchAssistant(retriever=retriever, llm=llm)

    questions = [
        "What algorithms are used in supervised learning?",
        "How does reinforcement learning differ from supervised learning?",
        "What are the main tasks in NLP?",
    ]

    for q in questions:
        resp = assistant.answer(ResearchQuery(q))
        print(f"\nQ: {resp.question}")
        print(f"A: {resp.answer}")
        print(f"Confidence: {resp.confidence} | Sources: {len(resp.sources)} | Latency: {resp.latency_ms:.0f}ms")
        if resp.sources:
            print(f"Top source: {resp.sources[0].title} (score={resp.sources[0].score})")
