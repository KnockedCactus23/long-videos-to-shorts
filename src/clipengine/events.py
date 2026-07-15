from pathlib import Path

import librosa
import numpy as np

from clipengine.energy import normalize


def compute_applause_score(wav_path: Path, hop_length: int = 512) -> np.ndarray:
    """Heurística de aplausos/vítores: ruido de banda ancha (alta spectral flatness)
    combinado con energía sostenida (alto RMS). No usa un clasificador de eventos de
    audio tipo YAMNet/PANNs a propósito: esta fase no debe depender de un modelo de
    IA/aprendizaje profundo (TensorFlow/PyTorch)."""
    y, sr = librosa.load(wav_path, sr=None, mono=True)
    flatness = librosa.feature.spectral_flatness(y=y, hop_length=hop_length)[0]
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    return normalize(flatness) * normalize(rms)
