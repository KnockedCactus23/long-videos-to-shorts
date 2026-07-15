from dataclasses import replace
from pathlib import Path

from clipengine.audio_extract import extract_audio, probe_duration
from clipengine.candidates import RankedClip, build_candidates, select_top_n
from clipengine.config import ClipConfig
from clipengine.energy import compute_energy_profile
from clipengine.events import compute_applause_score
from clipengine.fusion import find_local_peaks, fuse_signals, smooth
from clipengine.ingest import download_audio_only, download_video_segment, is_url, resolve_local_input
from clipengine.llm.dispatcher import rank_and_title
from clipengine.logging_utils import warn
from clipengine.metadata import build_metadata, write_metadata
from clipengine.render import render_clip
from clipengine.subtitles import slice_transcript, write_srt
from clipengine.transcribe import transcribe_audio


def run_pipeline(input_source: str, config: ClipConfig) -> Path:
    config.work_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    remote = is_url(input_source)
    # Para una URL, acá solo se baja el audio — nunca el directo completo. El video
    # (siempre liviano: solo los rangos de los clips finales) se descarga más abajo,
    # una vez que ya sabemos qué timestamps nos interesan.
    source_for_analysis = download_audio_only(input_source, config.work_dir) if remote else resolve_local_input(input_source)

    duration = probe_duration(source_for_analysis)
    wav_path = extract_audio(source_for_analysis, config.work_dir / "audio.wav", config.sample_rate)

    energy = compute_energy_profile(wav_path)
    applause = compute_applause_score(wav_path)
    curve = fuse_signals(energy, applause, config.energy_weight, config.applause_weight)
    curve = smooth(curve, energy.times, config.clip_target_duration)
    peaks = find_local_peaks(curve, energy.times, config.min_gap_seconds, config.peak_prominence)

    candidates = build_candidates(
        peaks, config.clip_target_duration, config.clip_min_duration, config.clip_max_duration, duration
    )

    # Selección base (Fase 1): siempre se calcula, es el fallback garantizado si la IA
    # está apagada o falla por cualquier motivo.
    baseline_selected = select_top_n(candidates, config.num_clips, config.min_gap_seconds)
    ranked: list[RankedClip] = [
        RankedClip(candidate=c, title=f"Momento destacado {i + 1}")
        for i, c in enumerate(baseline_selected)
    ]

    transcript = None
    if config.use_ai_layer:
        transcript = transcribe_audio(
            wav_path, config.whisper_model_size, config.whisper_device, config.whisper_compute_type,
            config.whisper_language,
        )

        if transcript is not None:
            pool_n = min(len(candidates), config.num_clips * config.ai_candidate_pool_multiplier)
            pool = select_top_n(candidates, pool_n, config.min_gap_seconds)
            ai_result = rank_and_title(transcript, pool, config)
            if ai_result:
                ranked = ai_result[: config.num_clips]

    if transcript is not None and config.burn_subtitles:
        for i, r in enumerate(ranked):
            segments = slice_transcript(transcript, r.candidate.start, r.candidate.end)
            r.subtitles_path = write_srt(segments, config.work_dir / f"clip_{i + 1:02d}.srt")

    clip_paths = []
    for i, r in enumerate(ranked):
        out_path = config.output_dir / f"clip_{i + 1:02d}.mp4"

        if remote:
            # Baja solo el rango [start, end] (absolutos, del directo original) de video
            # para este clip. El archivo resultante empieza en el segundo 0, así que
            # render_clip necesita un candidato con tiempos relativos a ese archivo —
            # los tiempos absolutos originales se preservan intactos en metadata.json.
            video_source = download_video_segment(
                input_source, r.candidate.start, r.candidate.end, config.work_dir / f"clip_{i + 1:02d}_src.mp4"
            )
            render_candidate = replace(r.candidate, start=0.0, end=r.candidate.end - r.candidate.start)
        else:
            video_source = source_for_analysis
            render_candidate = r.candidate

        try:
            render_clip(
                video_source, render_candidate, out_path, config.output_width, config.output_height, config.crf,
                r.subtitles_path,
            )
        except RuntimeError:
            if r.subtitles_path is None:
                raise
            warn(f"Fallo al renderizar el clip {i + 1} con subtítulos quemados; reintentando sin subtítulos.")
            r.subtitles_path = None
            render_clip(
                video_source, render_candidate, out_path, config.output_width, config.output_height, config.crf
            )
        clip_paths.append(out_path)

    metadata = build_metadata(ranked, {"input": input_source, "duration": duration}, clip_paths)
    write_metadata(metadata, config.output_dir / "metadata.json")
    return config.output_dir
