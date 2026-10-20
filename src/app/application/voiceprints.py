"""Local speaker identification logic.

Pure functions over speaker embeddings: cosine similarity, matching an
embedding against enrolled voiceprints, and agglomerative clustering of
unknown speakers. Embeddings are plain lists of floats; nothing here touches
audio or the network.

The per-job sidecar (``Voiceprints.json``) stores each unlabeled segment's
embedding so a finished job can be re-labelled later without re-reading audio.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from app.domain.models import SpeakerInterval

Embedding = list[float]

DEFAULT_IDENTIFY_THRESHOLD = 0.5
DEFAULT_CLUSTER_THRESHOLD = 0.5

SIDECAR_VERSION = 1


def cosine_similarity(a: Embedding, b: Embedding) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def identify_speaker(
    embedding: Embedding,
    voiceprints: dict[str, Embedding],
    threshold: float = DEFAULT_IDENTIFY_THRESHOLD,
) -> str | None:
    """Return the enrolled name whose voiceprint best matches, or None."""
    best_name: str | None = None
    best_score = -1.0
    for name, reference in voiceprints.items():
        score = cosine_similarity(embedding, reference)
        if score > best_score:
            best_score = score
            best_name = name
    if best_name is not None and best_score >= threshold:
        return best_name
    return None


def cluster_speakers(
    embeddings: list[Embedding],
    threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> list[int]:
    """Greedy centroid clustering followed by a centroid-linkage merge pass.

    The merge pass consolidates clusters that the greedy pass split apart
    (a segment compared to an immature centroid can fall below the threshold),
    which otherwise leaves many near-duplicate ``Speaker N`` clusters.
    """
    if len(embeddings) <= 1:
        return list(range(len(embeddings)))
    labels = _greedy_cluster(embeddings, threshold)
    return _merge_clusters(embeddings, labels, threshold)


def _greedy_cluster(embeddings: list[Embedding], threshold: float) -> list[int]:
    labels: list[int] = []
    clusters: list[list[Embedding]] = []
    for embedding in embeddings:
        best_label = -1
        best_score = -1.0
        for label, members in enumerate(clusters):
            score = cosine_similarity(embedding, _centroid(members))
            if score > best_score:
                best_score = score
                best_label = label
        if best_label != -1 and best_score >= threshold:
            clusters[best_label].append(embedding)
            labels.append(best_label)
        else:
            clusters.append([embedding])
            labels.append(len(clusters) - 1)
    return labels


def _merge_clusters(embeddings: list[Embedding], labels: list[int], threshold: float) -> list[int]:
    members: dict[int, list[int]] = {}
    for index, label in enumerate(labels):
        members.setdefault(label, []).append(index)
    clusters = [list(members[label]) for label in sorted(members)]
    centroids = [_centroid([embeddings[i] for i in cluster]) for cluster in clusters]
    while len(clusters) > 1:
        best_pair = None
        best_score = -1.0
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                score = cosine_similarity(centroids[a], centroids[b])
                if score > best_score:
                    best_score = score
                    best_pair = (a, b)
        if best_pair is None or best_score < threshold:
            break
        a, b = best_pair
        clusters[a].extend(clusters[b])
        centroids[a] = _centroid([embeddings[i] for i in clusters[a]])
        del clusters[b]
        del centroids[b]
    label_of: dict[int, int] = {}
    for label, cluster in enumerate(clusters):
        for index in cluster:
            label_of[index] = label
    return [label_of[index] for index in range(len(embeddings))]


def speaker_label(index: int) -> str:
    """Human label for a 0-based cluster index (``Speaker 1`` …)."""
    return f"Speaker {index + 1}"


@dataclass(frozen=True)
class SpeakerSegment:
    start_ms: int
    end_ms: int
    embedding: Embedding


@dataclass(frozen=True)
class SpeakerCluster:
    label: str
    centroid: Embedding
    segments: list[tuple[int, int]]


@dataclass(frozen=True)
class SpeakerAnalysis:
    intervals: list[SpeakerInterval]
    clusters: list[SpeakerCluster]


def analyse_speakers(
    segments: list[tuple[int, int]],
    embeddings: list[Embedding],
    voiceprints: dict[str, Embedding],
    identify_threshold: float = DEFAULT_IDENTIFY_THRESHOLD,
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> SpeakerAnalysis:
    """Label segments (enrolled name or ``Speaker N``) and report the clusters.

    ``segments`` are ``(start_ms, end_ms)`` pairs aligned one-to-one with
    ``embeddings`` (already computed for the segments that had no speaker VTT
    label). ``clusters`` exposes each ``Speaker N`` group's centroid and its
    segment ranges so they can be enrolled by name afterwards.
    """
    if len(segments) != len(embeddings):
        raise ValueError("segments and embeddings must align")
    labels: list[str | None] = [
        identify_speaker(embedding, voiceprints, identify_threshold) for embedding in embeddings
    ]
    unlabelled = [index for index, name in enumerate(labels) if name is None]
    if unlabelled:
        cluster_ids = cluster_speakers(
            [embeddings[index] for index in unlabelled], cluster_threshold
        )
        for local, index in enumerate(unlabelled):
            labels[index] = speaker_label(cluster_ids[local])

    intervals = [
        SpeakerInterval(start_ms, end_ms, labels[index])
        for index, (start_ms, end_ms) in enumerate(segments)
    ]

    cluster_segments: dict[str, list[tuple[int, int]]] = {}
    cluster_embeddings: dict[str, list[Embedding]] = {}
    for index, label in enumerate(labels):
        if label is not None and label.startswith("Speaker "):
            cluster_segments.setdefault(label, []).append(segments[index])
            cluster_embeddings.setdefault(label, []).append(embeddings[index])
    clusters = [
        SpeakerCluster(label, _centroid(cluster_embeddings[label]), cluster_segments[label])
        for label in sorted(cluster_segments, key=_cluster_index)
    ]
    return SpeakerAnalysis(intervals, clusters)


def label_segments(
    segments: list[tuple[int, int]],
    embeddings: list[Embedding],
    voiceprints: dict[str, Embedding],
    identify_threshold: float = DEFAULT_IDENTIFY_THRESHOLD,
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> list[SpeakerInterval]:
    """Backward-compatible wrapper returning only the intervals."""
    return analyse_speakers(
        segments, embeddings, voiceprints, identify_threshold, cluster_threshold
    ).intervals


def write_voiceprint_sidecar(
    path: Path, segments: list[SpeakerSegment], clusters: list[SpeakerCluster]
) -> None:
    payload = {
        "version": SIDECAR_VERSION,
        "segments": [
            {"start_ms": s.start_ms, "end_ms": s.end_ms, "embedding": list(s.embedding)}
            for s in segments
        ],
        "clusters": [
            {
                "label": c.label,
                "centroid": list(c.centroid),
                "segments": [list(p) for p in c.segments],
            }
            for c in clusters
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_voiceprint_sidecar(path: Path) -> tuple[list[SpeakerSegment], list[SpeakerCluster]]:
    """Read a sidecar; returns ``([], [])`` on a missing or malformed file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not isinstance(payload, dict):
        return [], []
    segments = [
        SpeakerSegment(
            int(item.get("start_ms", 0)),
            int(item.get("end_ms", 0)),
            [float(value) for value in item["embedding"]],
        )
        for item in payload.get("segments", [])
        if isinstance(item, dict) and _is_float_list(item.get("embedding"))
    ]
    clusters = []
    for item in payload.get("clusters", []):
        if not (isinstance(item, dict) and isinstance(item.get("label"), str)):
            continue
        if not _is_float_list(item.get("centroid")):
            continue
        ranges = [
            (int(pair[0]), int(pair[1]))
            for pair in item.get("segments", [])
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        ]
        clusters.append(
            SpeakerCluster(item["label"], [float(value) for value in item["centroid"]], ranges)
        )
    return segments, clusters


def _is_float_list(value) -> bool:
    return (
        isinstance(value, (list, tuple))
        and bool(value)
        and all(isinstance(item, (int, float)) for item in value)
    )


def _cluster_index(label: str) -> int:
    try:
        return int(label.rsplit(" ", 1)[1])
    except (ValueError, IndexError):
        return 0


def _centroid(members: list[Embedding]) -> Embedding:
    width = len(members[0]) if members else 0
    total = [0.0] * width
    for member in members:
        for index, value in enumerate(member):
            total[index] += value
    return [value / len(members) for value in total]
