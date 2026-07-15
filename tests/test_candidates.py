from clipengine.candidates import ClipCandidate, build_candidates, select_top_n


def test_build_candidates_clamps_to_bounds():
    peaks = [(5.0, 0.9), (100.0, 0.8)]
    candidates = build_candidates(
        peaks, target_duration=40, min_duration=20, max_duration=60, total_duration=110
    )
    assert len(candidates) == 2
    first = candidates[0]
    assert first.start == 0.0  # clamp al borde izquierdo
    assert first.end - first.start <= 60

    second = candidates[1]
    assert second.end <= 110  # clamp al borde derecho


def test_build_candidates_drops_short_clips_at_edge():
    peaks = [(2.0, 0.5)]
    candidates = build_candidates(
        peaks, target_duration=40, min_duration=30, max_duration=60, total_duration=110
    )
    # start clamp a 0, end = 40 -> duración 40 >= min_duration=30, se mantiene
    assert len(candidates) == 1


def test_select_top_n_avoids_overlap():
    candidates = [
        ClipCandidate(start=0, end=30, peak_time=15, score=0.9),
        ClipCandidate(start=10, end=40, peak_time=25, score=0.95),  # solapa con el anterior
        ClipCandidate(start=100, end=130, peak_time=115, score=0.7),
    ]
    selected = select_top_n(candidates, n=5, min_gap=5)
    # el de mayor score (0.95) gana el solapamiento; el tercero no solapa y se incluye
    assert len(selected) == 2
    scores = {c.score for c in selected}
    assert 0.95 in scores
    assert 0.7 in scores
    assert 0.9 not in scores


def test_select_top_n_respects_n_limit():
    candidates = [
        ClipCandidate(start=i * 100, end=i * 100 + 30, peak_time=i * 100 + 15, score=1.0 - i * 0.1)
        for i in range(5)
    ]
    selected = select_top_n(candidates, n=2, min_gap=5)
    assert len(selected) == 2
