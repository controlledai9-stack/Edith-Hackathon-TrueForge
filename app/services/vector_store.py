import logging
import threading
from pathlib import Path
from typing import List

from config import (
    LEARNING_DATA_DIR, VECTOR_STORE_DIR, EMBEDDING_MODEL,
    CHUNK_SIZE, CHUNK_OVERLAP, ENABLE_VECTOR_MEMORY,
)

logger = logging.getLogger("J.A.R.V.I.S")

_INDEX_FILE = VECTOR_STORE_DIR / "index.faiss"


class MemoryStore:
    """Wraps a local FAISS index over the user's learning_data/*.txt
    files plus prior conversation turns, using a local HuggingFace
    embedding model (no external API calls, no cost).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._store = None
        self._embeddings = None
        self._available = False
        self._init()

    def _init(self):
        if not ENABLE_VECTOR_MEMORY:
            logger.info("[MEMORY] Vector memory disabled for this runtime")
            return
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            from langchain_community.vectorstores import FAISS
            from langchain_core.documents import Document

            self._FAISS = FAISS
            self._Document = Document
            # Startup must never stall on Hugging Face network retries. The
            # embedding model is a local dependency; if it is not cached we
            # fall back immediately to no-memory mode and keep EDITH usable.
            self._embeddings = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL,
                model_kwargs={"local_files_only": True},
            )

            docs = self._load_learning_docs()

            if _INDEX_FILE.exists():
                self._store = FAISS.load_local(
                    str(VECTOR_STORE_DIR), self._embeddings,
                    allow_dangerous_deserialization=True,
                )
                if docs:
                    self._store.add_documents(docs)
                    self._save()
            elif docs:
                self._store = FAISS.from_documents(docs, self._embeddings)
                self._save()
            else:
                # Empty placeholder store so add_texts works later.
                self._store = FAISS.from_texts(["JARVIS memory store initialized."], self._embeddings)
                self._save()

            self._available = True
            logger.info("[MEMORY] Vector store ready (%d learning docs loaded)", len(docs))

        except Exception as e:
            logger.warning("[MEMORY] Vector store unavailable, falling back to no-memory mode: %s", e)
            self._available = False

    def _load_learning_docs(self) -> List:
        docs = []
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
            )
            for path in sorted(Path(LEARNING_DATA_DIR).glob("*.txt")):
                try:
                    text = path.read_text(encoding="utf-8").strip()
                    if not text:
                        continue
                    for chunk in splitter.split_text(text):
                        docs.append(self._Document(page_content=chunk, metadata={"source": path.name}))
                except Exception as e:
                    logger.warning("[MEMORY] Could not read %s: %s", path, e)
        except Exception as e:
            logger.warning("[MEMORY] Text splitter unavailable: %s", e)
        return docs

    def _save(self):
        try:
            self._store.save_local(str(VECTOR_STORE_DIR))
        except Exception as e:
            logger.warning("[MEMORY] Could not persist vector store: %s", e)

    @property
    def available(self) -> bool:
        return self._available

    def add_turn(self, session_id: str, user_msg: str, assistant_msg: str):
        """Index a finished conversation turn so future sessions can recall it."""
        if not self._available:
            return
        try:
            with self._lock:
                self._store.add_texts(
                    [f"User said: {user_msg}\nAssistant replied: {assistant_msg}"],
                    metadatas=[{"source": f"chat:{session_id}"}],
                )
                self._save()
        except Exception as e:
            logger.warning("[MEMORY] Could not index turn: %s", e)

    def retrieve(self, query: str, k: int = 5) -> str:
        """Return the top-k most relevant memory chunks, joined as context text."""
        if not self._available or not query.strip():
            return ""
        try:
            with self._lock:
                results = self._store.similarity_search(query, k=k)
            chunks = [r.page_content.strip() for r in results if r.page_content.strip()]
            return "\n---\n".join(chunks)
        except Exception as e:
            logger.warning("[MEMORY] Retrieval failed: %s", e)
            return ""

    def embed_query(self, text: str) -> list[float]:
        """Return a local embedding for session-scoped retrieval, when cached."""
        if not self._available or not str(text or "").strip():
            return []
        try:
            return [float(value) for value in self._embeddings.embed_query(str(text))]
        except Exception as e:
            logger.debug("[MEMORY] Query embedding unavailable: %s", e)
            return []

    def embed_documents(self, texts: List[str]) -> list[list[float]]:
        if not self._available or not texts:
            return []
        try:
            return [[float(value) for value in vector] for vector in self._embeddings.embed_documents(texts)]
        except Exception as e:
            logger.debug("[MEMORY] Document embeddings unavailable: %s", e)
            return []


_memory_singleton = None
_singleton_lock = threading.Lock()


def get_memory_store() -> MemoryStore:
    global _memory_singleton
    if _memory_singleton is None:
        with _singleton_lock:
            if _memory_singleton is None:
                _memory_singleton = MemoryStore()
    return _memory_singleton
