"""Adds narration, sound effects and background music to the rendered Short.

    python flappy-marmot/tools/voiceover.py short.mp4 [out.mp4] [--voice am_michael+am_onyx]

Reads <short>.timeline.json written by record-short.mjs. Narration uses the
Kokoro TTS model (pip install kokoro-onnx soundfile numpy); put
kokoro-v1.0.int8.onnx and voices-v1.0.bin from
https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0
in flappy-marmot/tools/models/ (or pass --models DIR). Music and SFX are
synthesised here, so there is nothing to license.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 24000


def tone(freq, dur, kind="square", vol=1.0):
    t = np.arange(int(dur * SR)) / SR
    phase = 2 * np.pi * np.cumsum(np.broadcast_to(freq, t.shape)) / SR
    if kind == "square":
        wave = np.sign(np.sin(phase))
    elif kind == "triangle":
        wave = 2 / np.pi * np.arcsin(np.sin(phase))
    else:  # saw
        wave = 2 * ((phase / (2 * np.pi)) % 1) - 1
    env = np.minimum(1, np.minimum(t / 0.005, (dur - t) / 0.02).clip(0))
    return wave * env * vol


def sweep(f0, f1, dur, kind="saw", vol=1.0):
    n = int(dur * SR)
    freq = np.geomspace(f0, f1, n)
    fade = np.linspace(1, 0, n) ** 1.5
    return tone(freq, dur, kind, vol) * fade


def music(duration):
    """A bouncy 8-bit loop: I-vi-IV-V in C, arpeggio + bass, 132 bpm."""
    beat = 60 / 132
    chords = [(261.63, 329.63, 392.00), (220.00, 261.63, 329.63),
              (174.61, 220.00, 261.63), (196.00, 246.94, 293.66)]
    bar = []
    for root, third, fifth in chords:
        arp = [root * 2, third * 2, fifth * 2, third * 2] * 2
        notes = np.concatenate([tone(f, beat / 2, "square", 0.22) for f in arp])
        bass = np.concatenate([tone(root / 2, beat, "triangle", 0.5) for _ in range(4)])
        bar.append(notes[: len(bass)] + bass[: len(notes)])
    loop = np.concatenate(bar)
    reps = int(np.ceil(duration * SR / len(loop)))
    return np.tile(loop, reps)[: int(duration * SR)]


def place(track, clip, at):
    start = max(0, int(at * SR))
    end = min(len(track), start + len(clip))
    if end > start:
        track[start:end] += clip[: end - start]


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--voice", default="am_michael+am_onyx",
                    help="Kokoro voice, or several joined with + to blend them equally")
    ap.add_argument("--speed", type=float, default=1.05)
    ap.add_argument("--models", default=str(here / "models"))
    args = ap.parse_args()

    video = Path(args.video)
    out = Path(args.out or video.with_name(video.stem + "-final.mp4"))
    timeline = json.loads(video.with_suffix(".timeline.json").read_text())
    events, duration = timeline["events"], timeline["duration"]

    from kokoro_onnx import Kokoro
    models = Path(args.models)
    tts = Kokoro(str(models / "kokoro-v1.0.int8.onnx"), str(models / "voices-v1.0.bin"))

    names = args.voice.split("+")
    style = sum(tts.get_voice_style(v) for v in names) / len(names)
    lang = "en-gb" if all(v.startswith("b") for v in names) else "en-us"

    n = int(duration * SR)
    voice = np.zeros(n)
    sfx = np.zeros(n)

    lines = sorted((events[e] + delay, line) for e, delay, _dur, _html, line in timeline["captions"]
                   if e in events and line)
    for i, (at, line) in enumerate(lines):
        # Room until the next line starts; speak a little faster if it wouldn't fit.
        room = (lines[i + 1][0] if i + 1 < len(lines) else duration) - at - 0.1
        speed = args.speed
        for _ in range(3):
            audio, sr = tts.create(line, voice=style, speed=speed, lang=lang)
            if len(audio) / sr <= room or speed >= 1.35:
                break
            speed = min(1.35, speed * len(audio) / sr / room * 1.02)
        assert sr == SR
        place(voice, np.asarray(audio, dtype=float), at)

    for name, at in events.items():
        if name.startswith("flip"):
            place(sfx, sweep(180, 900, 0.5, "saw", 0.12), at)
        elif name.startswith("die"):
            place(sfx, sweep(1400, 120, 1.0, "saw", 0.15), at)
            place(sfx, tone(90, 0.25, "square", 0.1), at)

    # Duck the music while the narrator talks.
    env = np.convolve(np.abs(voice) > 0.01, np.ones(int(0.25 * SR)) / (0.25 * SR), "same")
    duck = 1 - 0.65 * np.clip(env * 4, 0, 1)
    voice *= 0.9 / max(1e-6, np.abs(voice).max())
    mix = voice + sfx + 0.12 * music(duration) * duck
    mix /= max(1.0, np.abs(mix).max() / 0.95)

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "mix.wav"
        sf.write(wav, mix, SR)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-i", str(wav),
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",  # YouTube's loudness target
                        "-ar", "48000", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", str(out)], check=True)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
