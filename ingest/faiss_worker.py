"""Greedy FAISS clustering, run in its own process.

faiss and torch each bundle an OpenMP runtime on macOS and crash or abort when they share a process,
so the caller (which has torch loaded to make the embeddings) runs this as a subprocess.
Reads a .npy of unit-length embeddings on stdin and prints a JSON list of cluster ids.
"""
import io
import json
import sys

import faiss
import numpy as np

faiss.omp_set_num_threads(1)


def cluster(embeddings: np.ndarray, threshold: float) -> list[int]:
    index = faiss.IndexFlatIP(embeddings.shape[1])
    cluster_of_rep: list[int] = []  # FAISS row -> cluster id of that representative
    labels: list[int] = []
    for emb in embeddings.astype("float32"):
        if index.ntotal:
            sims, ids = index.search(emb[None, :], 1)
            if sims[0][0] >= threshold:
                labels.append(cluster_of_rep[int(ids[0][0])])
                continue
        cluster_of_rep.append(len(cluster_of_rep))
        index.add(emb[None, :])
        labels.append(cluster_of_rep[-1])
    return labels


if __name__ == "__main__":
    emb = np.load(io.BytesIO(sys.stdin.buffer.read()))
    print(json.dumps(cluster(emb, float(sys.argv[1]))))
