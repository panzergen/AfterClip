from app.application.voiceprints import (
    SpeakerSegment,
    analyse_speakers,
    cluster_speakers,
    cosine_similarity,
    identify_speaker,
    label_segments,
    load_voiceprint_sidecar,
    speaker_label,
    write_voiceprint_sidecar,
)


def test_cosine_similarity_known_values():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0


def test_cosine_similarity_guards_zero_and_mismatched():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0


def test_identify_speaker_returns_best_match_above_threshold():
    voiceprints = {
        "Alice": [1.0, 0.0, 0.0],
        "Bob": [0.0, 1.0, 0.0],
    }
    assert identify_speaker([0.9, 0.1, 0.0], voiceprints, threshold=0.7) == "Alice"


def test_identify_speaker_returns_none_below_threshold():
    voiceprints = {"Alice": [1.0, 0.0]}
    assert identify_speaker([0.0, 1.0], voiceprints, threshold=0.7) is None


def test_identify_speaker_returns_none_for_empty_voiceprints():
    assert identify_speaker([1.0, 0.0], {}) is None


def test_cluster_speakers_groups_similar_embeddings():
    embeddings = [
        [1.0, 0.0],  # speaker A
        [0.9, 0.1],  # speaker A
        [0.0, 1.0],  # speaker B
        [1.0, 0.0],  # speaker A again
    ]
    labels = cluster_speakers(embeddings, threshold=0.7)
    assert labels[0] == labels[1] == labels[3]
    assert labels[2] != labels[0]


def test_cluster_speakers_separates_dissimilar():
    labels = cluster_speakers([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0, 1.0]], threshold=0.7)
    assert len(set(labels)) == 3


def test_cluster_speakers_empty():
    assert cluster_speakers([]) == []


def test_cluster_speakers_consolidates_noisy_duplicates():
    base_a = [1.0, 0.0, 0.0]
    base_b = [0.0, 1.0, 0.0]
    embeddings = []
    for i in range(20):
        base = base_a if i % 2 == 0 else base_b
        noise = [(i % 3) * 0.01, (i % 5) * 0.01, (i % 7) * 0.01]
        embeddings.append([base[j] + noise[j] for j in range(3)])
    labels = cluster_speakers(embeddings, threshold=0.5)
    assert len(set(labels)) == 2
    assert labels[0] == labels[2] == labels[4]
    assert labels[1] == labels[3]
    assert labels[0] != labels[1]


def test_speaker_label_is_one_based():
    assert speaker_label(0) == "Speaker 1"
    assert speaker_label(2) == "Speaker 3"


def test_label_segments_identifies_and_clusters():
    segments = [(0, 1000), (1000, 2000), (2000, 3000)]
    embeddings = [
        [1.0, 0.0],  # matches Alice
        [0.0, 1.0],  # unknown -> Speaker 1
        [0.0, 0.9],  # unknown, same cluster as previous
    ]
    voiceprints = {"Alice": [1.0, 0.0]}
    labelled = label_segments(segments, embeddings, voiceprints)
    assert labelled[0].speaker == "Alice"
    assert labelled[0].start_ms == 0
    assert labelled[0].end_ms == 1000
    assert labelled[1].speaker == "Speaker 1"
    assert labelled[2].speaker == "Speaker 1"


def test_label_segments_requires_aligned_inputs():
    try:
        label_segments([(0, 1)], [[1.0], [2.0]], {})
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched lengths must raise")


def test_analyse_speakers_reports_clusters_with_centroids():
    segments = [(0, 1000), (1000, 2000), (2000, 3000), (3000, 4000)]
    embeddings = [
        [1.0, 0.0],
        [0.9, 0.1],  # same speaker as first
        [0.0, 1.0],  # different speaker
        [0.0, 0.9],  # same as third
    ]
    analysis = analyse_speakers(segments, embeddings, {})
    assert len(analysis.clusters) == 2
    labels = {cluster.label for cluster in analysis.clusters}
    assert labels == {"Speaker 1", "Speaker 2"}
    for cluster in analysis.clusters:
        assert len(cluster.centroid) == 2
        assert len(cluster.segments) == 2


def test_voiceprint_sidecar_round_trip(tmp_path):
    segments = [
        SpeakerSegment(0, 1000, [0.1, 0.2, 0.3]),
        SpeakerSegment(1000, 2000, [0.4, 0.5, 0.6]),
    ]
    from app.application.voiceprints import SpeakerCluster

    clusters = [SpeakerCluster("Speaker 1", [0.25, 0.35, 0.45], [(0, 1000), (1000, 2000)])]
    path = tmp_path / "Voiceprints.json"
    write_voiceprint_sidecar(path, segments, clusters)
    loaded_segments, loaded_clusters = load_voiceprint_sidecar(path)
    assert len(loaded_segments) == 2
    assert loaded_segments[0].embedding == [0.1, 0.2, 0.3]
    assert loaded_clusters[0].label == "Speaker 1"
    assert loaded_clusters[0].segments == [(0, 1000), (1000, 2000)]


def test_voiceprint_sidecar_missing_returns_empty(tmp_path):
    segments, clusters = load_voiceprint_sidecar(tmp_path / "nope.json")
    assert segments == []
    assert clusters == []
