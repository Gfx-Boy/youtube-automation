"""Module 5 — Audio Analysis.

Uses librosa to extract BPM, beat timestamps, onset peaks, energy
curve, drop candidates, and section boundaries from the audio track.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import librosa
import numpy as np

from app.core.logging import get_logger
from app.core.schemas import AudioSection, BeatMap, SectionType

log = get_logger(__name__)


def analyse_audio(
    audio_path: str | Path,
    *,
    sr: int = 22050,
) -> BeatMap:
    """Full audio analysis → BeatMap object."""
    audio_path = str(audio_path)
    log.info("Analysing audio: %s …", Path(audio_path).name)

    y, sr_actual = librosa.load(audio_path, sr=sr, mono=True)
    duration = librosa.get_duration(y=y, sr=sr_actual)

    # ── BPM & beats ────────────────────────────────────────────────
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr_actual)
    # tempo may be an ndarray in newer librosa
    bpm = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr_actual).tolist()

    # ── onsets ──────────────────────────────────────────────────────
    onset_env = librosa.onset.onset_strength(y=y, sr=sr_actual)
    onset_frames = librosa.onset.onset_detect(
        y=y, sr=sr_actual, onset_envelope=onset_env, backtrack=False
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr_actual).tolist()

    # ── energy curve (RMS) ──────────────────────────────────────────
    rms = librosa.feature.rms(y=y)[0]
    # normalise to 0–1
    rms_norm = rms / (rms.max() + 1e-8)
    energy_curve = rms_norm.tolist()

    # ── drop candidates (big energy jumps) ──────────────────────────
    drop_candidates = _find_drops(rms_norm, sr_actual)

    # ── section estimation ──────────────────────────────────────────
    sections = _estimate_sections(y, sr_actual, duration, bpm, beat_times, rms_norm)

    beat_map = BeatMap(
        bpm=bpm,
        beat_times=beat_times,
        onset_times=onset_times,
        energy_curve=energy_curve,
        drop_candidates=drop_candidates,
        sections=sections,
    )
    log.info("BPM=%.1f | beats=%d | onsets=%d | drops=%d | sections=%d",
             bpm, len(beat_times), len(onset_times),
             len(drop_candidates), len(sections))
    return beat_map


# ── helpers ─────────────────────────────────────────────────────────

def _find_drops(
    rms_norm: np.ndarray,
    sr: int,
    hop_length: int = 512,
    percentile: float = 90.0,
) -> list[float]:
    """Find timestamps where energy jumps abruptly (likely drops)."""
    diff = np.diff(rms_norm)
    threshold = np.percentile(diff[diff > 0], percentile) if np.any(diff > 0) else 0.5
    indices = np.where(diff > threshold)[0]
    times = librosa.frames_to_time(indices, sr=sr, hop_length=hop_length)
    return times.tolist()


def _estimate_sections(
    y: np.ndarray,
    sr: int,
    duration: float,
    bpm: float,
    beat_times: list[float],
    rms_norm: np.ndarray,
) -> list[AudioSection]:
    """Rough section estimation based on energy and structure.

    This is a heuristic; can be replaced with a learned model later.
    Splits the track into intro → buildup → drop → verse cycles → outro.
    """
    if duration < 5:
        return [AudioSection(section_type=SectionType.INTRO, start_time=0, end_time=duration)]

    sections: list[AudioSection] = []

    # Simple approach: split into N equal chunks and label by energy
    n_chunks = max(4, int(duration / 10))
    chunk_size = len(rms_norm) // n_chunks

    for i in range(n_chunks):
        start_idx = i * chunk_size
        end_idx = min((i + 1) * chunk_size, len(rms_norm))
        chunk_energy = float(np.mean(rms_norm[start_idx:end_idx]))

        start_time = (i / n_chunks) * duration
        end_time = ((i + 1) / n_chunks) * duration

        if i == 0:
            stype = SectionType.INTRO
        elif i == n_chunks - 1:
            stype = SectionType.OUTRO
        elif chunk_energy > 0.7:
            stype = SectionType.DROP
        elif chunk_energy > 0.45:
            stype = SectionType.CHORUS
        elif chunk_energy > 0.25:
            stype = SectionType.VERSE
        else:
            stype = SectionType.BUILDUP

        sections.append(AudioSection(
            section_type=stype,
            start_time=round(start_time, 3),
            end_time=round(end_time, 3),
        ))

    # Merge consecutive same-type sections
    merged: list[AudioSection] = [sections[0]]
    for s in sections[1:]:
        if s.section_type == merged[-1].section_type:
            merged[-1].end_time = s.end_time
        else:
            merged.append(s)

    return merged
