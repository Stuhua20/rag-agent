"""Compare retrieval on authored synthetic examples and an isolated CPU benchmark.

Default uses mock embeddings (mechanical smoke test only). --real-embeddings sends
only these synthetic examples to the configured embedding provider, never user files.
Query embeddings are precomputed identically for both engines to isolate ranking cost.
"""
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.embedding_service import embedding_service
from app.services.json_store_service import json_store
from app.services.retrieval_index_service import RetrievalIndexService, retrieval_index_service
from app.services.retrieval_service import retrieval_service


def seed(documents: list[dict], vectors: list[list[float]]) -> None:
    records, chunks, embeddings = [], [], []
    profile = embedding_service.profile()
    for item, vector in zip(documents, vectors):
        doc_id = item["id"]
        records.append({"id": doc_id, "file_name": item["file_name"], "status": "indexed"})
        chunk = {"id": doc_id, "document_id": doc_id, "sheet_id": doc_id, "sheet_name": item["sheet_name"],
                 "columns": item["columns"], "row_start": 1, "row_end": 1, "content": item["text"],
                 "metadata": {"file_name": item["file_name"], "sheet_name": item["sheet_name"]}}
        chunks.append(chunk)
        embeddings.append({"chunk_id": doc_id, "document_id": doc_id, "vector": vector,
                           "embedding_model": profile["model"], "embedding_profile": profile})
    json_store.write_batch({"documents.json": records, "chunks.json": chunks, "embeddings.json": embeddings})


def configure(engine: str, top_k: int) -> None:
    config = json_store.read_json("settings.json")
    config["retrieval"].update(engine=engine, search_mode="hybrid", top_k=top_k, max_chunks_per_doc=0)
    json_store.write_json("settings.json", config)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--real-embeddings", action="store_true")
    parser.add_argument("--benchmark-chunks", type=int, default=1000)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    if args.benchmark_chunks < 1 or args.top_k < 1:
        parser.error("benchmark-chunks and top-k must be positive")
    fixture = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/retrieval_cases.json").read_text())
    embedding_config = embedding_service._get_config()
    if args.real_embeddings and not embedding_config["api_key"]:
        parser.error("Real evaluation needs the configured EMBEDDING_API_KEY; no requests made")
    previous_data, previous_storage = json_store.data_dir, settings.storage_dir
    report = {"embedding_mode": "real" if args.real_embeddings else "mock", "model": embedding_config["model"],
              "label_note": fixture["note"], "top_k": args.top_k, "quality": {}, "benchmark": {}}
    try:
        with TemporaryDirectory(prefix="retrieval-evaluation-") as directory:
            json_store.data_dir, settings.storage_dir = Path(directory) / "data", Path(directory) / "original"
            json_store.initialize()
            config = json_store.read_json("settings.json")
            config["embedding"].update({key: embedding_config[key] for key in ("provider", "base_url", "model")},
                                       mock=not args.real_embeddings)
            json_store.write_json("settings.json", config)
            texts = [item["text"] for item in fixture["documents"]]
            questions = [item["question"] for item in fixture["queries"]]
            started = time.perf_counter()
            all_vectors = embedding_service.embed_batch(texts + questions)
            if len(all_vectors) != len(texts) + len(questions):
                raise ValueError("Embedding provider returned an incomplete batch")
            report["embedding_seconds"] = round(time.perf_counter() - started, 4)
            document_vectors = all_vectors[:len(texts)]
            query_vectors = dict(zip(questions, all_vectors[len(texts):]))
            seed(fixture["documents"], document_vectors)
            for engine in ("legacy", "bm25_faiss"):
                configure(engine, args.top_k)
                recalls, reciprocals, irrelevant, empty, details = [], [], [], [], []
                with patch.object(embedding_service, "embed_text", side_effect=lambda question: query_vectors[question]):
                    for case in fixture["queries"]:
                        results = retrieval_service.search(case["question"])
                        retrieved = [source["document_id"] for source in results]
                        expected = set(case["relevant"])
                        if expected:
                            recalls.append(len(expected.intersection(retrieved)) / len(expected))
                            reciprocals.append(next((1 / rank for rank, doc_id in enumerate(retrieved, 1) if doc_id in expected), 0))
                        else:
                            empty.append(not retrieved)
                        irrelevant.append(sum(doc_id not in expected for doc_id in retrieved) / max(1, len(retrieved)))
                        details.append({"question": case["question"], "expected": sorted(expected), "retrieved": retrieved})
                report["quality"][engine] = {"recall_at_k": float(np.mean(recalls)), "mrr": float(np.mean(reciprocals)),
                                             "irrelevant_result_fraction": float(np.mean(irrelevant)),
                                             "no_answer_empty_fraction": float(np.mean(empty)), "cases": details}

            # No additional remote embeddings are needed for the scaling benchmark.
            rng = np.random.default_rng(42)
            dim = len(document_vectors[0])
            benchmark_docs = [{"id": str(i), "file_name": f"document-{i}.csv", "sheet_name": "合同",
                               "columns": ["条款"], "text": f"合同编号 BENCH-{i:06d}，交货验收后付款，设备保修两年。"}
                              for i in range(args.benchmark_chunks)]
            seed(benchmark_docs, rng.normal(size=(args.benchmark_chunks, dim)).astype("float32").tolist())
            query_vector = rng.normal(size=dim).astype("float32").tolist()
            for engine in ("legacy", "bm25_faiss"):
                configure(engine, args.top_k)
                with patch.object(embedding_service, "embed_text", return_value=query_vector):
                    started = time.perf_counter()
                    retrieval_service.search("交货付款 BENCH-000001")
                    cold_ms = (time.perf_counter() - started) * 1000
                    timings = []
                    for _ in range(10):
                        started = time.perf_counter()
                        retrieval_service.search("交货付款 BENCH-000001")
                        timings.append((time.perf_counter() - started) * 1000)
                report["benchmark"][engine] = {"cold_ms": round(cold_ms, 3), "warm_p50_ms": round(float(np.median(timings)), 3),
                                               "warm_p95_ms": round(float(np.percentile(timings, 95)), 3)}
            index = retrieval_index_service.get()
            report["benchmark"].update(chunks=args.benchmark_chunks, dimension=dim,
                                       vector_index_bytes=args.benchmark_chunks * dim * 4,
                                       cached_scopes_limit=RetrievalIndexService.MAX_CACHED_SCOPES,
                                       built_vector_count=len(index.vector_rows),
                                       memory_note="Vector bytes only; excludes BM25, Python objects, JSON and additional cached scopes.")
    finally:
        json_store.data_dir, settings.storage_dir = previous_data, previous_storage
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "quality"}, ensure_ascii=False, indent=2))
    print("Quality metrics and per-query results:", args.output)


if __name__ == "__main__":
    main()
