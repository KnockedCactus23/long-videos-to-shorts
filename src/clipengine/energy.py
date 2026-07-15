from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np


@dataclass
class EnergyProfile:
    times: np.ndarray
    rms: np.ndarray
    hop_length: int
    sr: int


def normalize(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()), float(x.max())
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


def compute_energy_profile(wav_path: Path, frame_length: int = 2048, hop_length: int = 512) -> EnergyProfile:
    y, sr = librosa.load(wav_path, sr=None, mono=True)
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    return EnergyProfile(times=times, rms=normalize(rms), hop_length=hop_length, sr=sr)
