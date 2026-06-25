import numpy as np


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    a_vec = np.array(a, dtype=float)
    b_vec = np.array(b, dtype=float)
    denominator = np.linalg.norm(a_vec) * np.linalg.norm(b_vec)
    if denominator == 0:
        return 0.0
    return float(np.dot(a_vec, b_vec) / denominator)

