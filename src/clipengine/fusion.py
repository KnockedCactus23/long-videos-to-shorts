import numpy as np
from scipy.signal import find_peaks

from clipengine.energy import EnergyProfile


def fuse_signals(energy: EnergyProfile, applause: np.ndarray, energy_weight: float, applause_weight: float) -> np.ndarray:
    return energy_weight * energy.rms + applause_weight * applause


def smooth(curve: np.ndarray, times: np.ndarray, window_seconds: float) -> np.ndarray:
    """Media móvil con ventana ~ duración objetivo del clip, para que el pico
    refleje energía sostenida y no un transitorio de una sola muestra."""
    hop_seconds = float(times[1] - times[0])
    win = max(1, int(window_seconds / hop_seconds))
    kernel = np.ones(win) / win
    return np.convolve(curve, kernel, mode="same")


def find_local_peaks(curve: np.ndarray, times: np.ndarray, min_gap_seconds: float, prominence: float) -> list[tuple[float, float]]:
    hop_seconds = float(times[1] - times[0])
    distance = max(1, int(min_gap_seconds / hop_seconds))
    idx, _ = find_peaks(curve, distance=distance, prominence=prominence)
    return [(float(times[i]), float(curve[i])) for i in idx]
