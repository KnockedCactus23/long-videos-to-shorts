import numpy as np
import soundfile as sf

from clipengine.energy import compute_energy_profile
from clipengine.events import compute_applause_score


def _write_wav(path, sr=16000, duration=6.0):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # primera mitad: tono suave (baja energía); segunda mitad: ruido blanco fuerte (simula aplausos)
    half = len(t) // 2
    quiet = 0.02 * np.sin(2 * np.pi * 220 * t[:half])
    rng = np.random.default_rng(42)
    loud_noise = 0.9 * rng.standard_normal(len(t) - half)
    y = np.concatenate([quiet, loud_noise]).astype(np.float32)
    sf.write(path, y, sr)


def test_compute_energy_profile_higher_in_loud_half(tmp_path):
    wav_path = tmp_path / "synthetic.wav"
    _write_wav(wav_path)

    profile = compute_energy_profile(wav_path)
    midpoint_time = profile.times[-1] / 2
    first_half_mask = profile.times < midpoint_time
    second_half_mask = ~first_half_mask

    assert profile.rms[second_half_mask].mean() > profile.rms[first_half_mask].mean()


def test_compute_applause_score_higher_in_noisy_half(tmp_path):
    wav_path = tmp_path / "synthetic.wav"
    _write_wav(wav_path)

    score = compute_applause_score(wav_path)
    midpoint = len(score) // 2
    # el ruido blanco (banda ancha + energético) debe puntuar más alto que el tono puro
    assert score[midpoint:].mean() > score[:midpoint].mean()
