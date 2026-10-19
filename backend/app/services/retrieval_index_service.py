"""Bounded, scoped retrieval indexes derived from a consistent JSON snapshot."""
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock

import faiss
import jieba
import numpy as np
from rank_bm25 import BM25Okapi

from app.agents.budget import check_budget
from app.services.embedding_service import embedding_service
from app.services.json_store_service import json_store


STOP_WORDS = frozenset("的 了 是 有 和 与 及 请 请问 查询 什么 哪些 多少 一下 吗 呢 是否 a an the is are what which how please of in to and".split())
TOKENIZER_VERSION = "jieba-code-v1"


def tokenize(text: str) -> list[str]:
    tokens = []
    for part in re.findall(r"[\u3400-\u9fff]+|[a-z0-9]+(?:[._/-][a-z0-9]+)*", text.casefold()):
        words = jieba.lcut(part, HMM=False) if re.search(r"[\u3400-\u9fff]", part) else [part]
        for word in words:
            if word.strip() and word not in STOP_WORDS:
                tokens.append(word)
    return tokens


def searchable_text(chunk: dict) -> str:
    return "\n".join([
        str(chunk.get("metadata", {}).get("file_name", "")),
        str(chunk.get("title", "")), str(chunk.get("sheet_name", "")),
        " ".join(str(column) for column in chunk.get("columns", [])),
        str(chunk.get("content", "")),
    ])


class IndexChanged(RuntimeError):
    pass


class VectorSearchUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class IndexSnapshot:
    version: tuple
    profile: dict
    chunks: tuple[dict, ...]
    embeddings: dict[str, dict]
    tokens: tuple[frozenset[str], ...]
    bm25: BM25Okapi | None
    vector_index: object | None
    vector_rows: tuple[int, ...]
    dimension: int
    incompatible_chunks: tuple[str, ...]


class RetrievalIndexService:
    MAX_CACHED_SCOPES = 8

    def __init__(self) -> None:
        self._lock = RLock()
        self._cache: OrderedDict[tuple, IndexSnapshot] = OrderedDict()

    def version(self) -> tuple:
        with json_store._lock:
            files = []
            for name in ("documents.json", "chunks.json", "embeddings.json"):
                path = json_store._path(name)
                stat = path.stat() if path.exists() else None
                files.append((name, stat.st_mtime_ns, stat.st_size, stat.st_ino) if stat else (name,))
            config = json_store.read_json("settings.json")
            retrieval = config.get("retrieval", {}) if isinstance(config, dict) else {}
            return (str(json_store.data_dir.resolve()), tuple(files),
                    json.dumps(embedding_service.profile(), sort_keys=True),
                    json.dumps(retrieval, sort_keys=True), TOKENIZER_VERSION)

    def assert_current(self, version: tuple) -> None:
        if self.version() != version:
            raise IndexChanged("本轮检索依赖的资料或配置已变更，请重新提问。")

    def get(self, filters: dict | None = None) -> IndexSnapshot:
        filters = filters or {}
        allowed = tuple(sorted(set(filters["document_ids"]))) if "document_ids" in filters else None
        with json_store._lock:
            version = self.version()
            key = (version, allowed, filters.get("sheet_name"))
            with self._lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    return cached
            profile = embedding_service.profile()
            documents = {item["id"] for item in json_store.list_items("documents.json")
                         if item.get("status") == "indexed" and (allowed is None or item["id"] in allowed)}
            chunks = tuple(sorted((item for item in json_store.list_items("chunks.json")
                                   if item.get("document_id") in documents
                                   and (not filters.get("sheet_name")
                                        or item.get("sheet_name") == filters["sheet_name"])), key=lambda item: item["id"]))
            embeddings = {item["chunk_id"]: item for item in json_store.list_items("embeddings.json")
                          if item.get("document_id") in documents}

        # Build off-lock; publish only a complete snapshot from an unchanged version.
        check_budget()
        token_lists = []
        for chunk in chunks:
            check_budget()
            token_lists.append(tokenize(searchable_text(chunk)))
        bm25 = BM25Okapi(token_lists) if any(token_lists) else None
        vectors, rows, incompatible = [], [], []
        for row, chunk in enumerate(chunks):
            check_budget()
            embedding = embeddings.get(chunk["id"], {})
            vector = embedding.get("vector", [])
            stored_profile = embedding.get("embedding_profile")
            # A model name alone cannot distinguish mock/real vectors or two API endpoints.
            # Historical records need one reindex before the new dense path can trust them.
            compatible = stored_profile == profile
            try:
                array = np.asarray(vector, dtype="float32")
                valid = array.ndim == 1 and array.size > 0 and np.isfinite(array).all() and np.linalg.norm(array) > 0
            except (ValueError, TypeError):
                valid = False
            if not compatible or not valid or (profile["mock"] and len(array) != profile["dim"]):
                incompatible.append(chunk["id"])
                continue
            rows.append(row)
            vectors.append(array)
        dimensions = {len(vector) for vector in vectors}
        index, dimension = None, 0
        if len(dimensions) == 1:
            dimension = dimensions.pop()
            matrix = np.ascontiguousarray(vectors, dtype="float32")
            faiss.normalize_L2(matrix)
            index = faiss.IndexFlatIP(dimension)
            index.add(matrix)
        elif vectors:
            incompatible.extend(chunks[row]["id"] for row in rows)
            rows = []
        snapshot = IndexSnapshot(version, profile, chunks, embeddings,
                                 tuple(frozenset(tokens) for tokens in token_lists), bm25,
                                 index, tuple(rows), dimension, tuple(incompatible))
        with json_store._lock:
            self.assert_current(version)
            with self._lock:
                self._cache[key] = snapshot
                self._cache.move_to_end(key)
                while len(self._cache) > self.MAX_CACHED_SCOPES:
                    self._cache.popitem(last=False)
        return snapshot


retrieval_index_service = RetrievalIndexService()
