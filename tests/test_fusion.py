import numpy as np

from clipengine.energy import EnergyProfile, normalize
from clipengine.fusion import fuse_signals, smooth, find_local_peaks


def test_normalize_flat_array_returns_zeros():
    flat = np.ones(10)
    result = normalize(flat)
    assert np.allclose(result, 0.0)


def test_normalize_scales_to_0_1():
    x = np.array([0.0, 5.0, 10.0])
    result = normalize(x)
    assert result.min() == 0.0
    assert result.max() == 1.0


def test_fuse_signals_weighted_sum():
    energy = EnergyProfile(times=np.array([0.0, 1.0]), rms=np.array([1.0, 0.0]), hop_length=512, sr=16000)
    applause = np.array([0.0, 1.0])
    fused = fuse_signals(energy, applause, energy_weight=0.7, applause_weight=0.3)
    assert np.allclose(fused, [0.7, 0.3])


def test_find_local_peaks_detects_known_bursts():
    times = np.linspace(0, 60, 600)
    curve = np.zeros_like(times)
    for center in (10, 30, 50):
        curve += np.exp(-((times - center) ** 2) / (2 * 1.0 ** 2))
    curve = smooth(curve, times, window_seconds=1.0)
    peaks = find_local_peaks(curve, times, min_gap_seconds=5.0, prominence=0.1)
    peak_times = sorted(t for t, _ in peaks)
    assert len(peak_times) == 3
    for expected, actual in zip((10, 30, 50), peak_times):
        assert abs(expected - actual) < 1.0
