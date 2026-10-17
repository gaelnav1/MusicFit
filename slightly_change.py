#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MusicFit Slightly Change

Genera variantes REALES y reproducibles de un asset de video y reconstruye
su metadata tecnica desde cero. Cada salida incluye un manifest JSON con los
cambios aplicados para poder medir posteriormente su rendimiento.

Incluye microcambios visuales/audio y pequenas variaciones de duracion.
Requiere ffmpeg y ffprobe disponibles en PATH.

Ejemplos:
    python slightly_change.py videos/video.mp4
    python slightly_change.py videos/video.mp4 --variants 6 --out variantes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Fallo el comando: {' '.join(cmd)}")


def probe(path: Path) -> dict:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "ffprobe fallo")
    return json.loads(p.stdout)


def duration_seconds(probe_data: dict) -> float:
    try:
        return float(probe_data.get("format", {}).get("duration", 0.0))
    except (TypeError, ValueError):
        return 0.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_profile(i: int, rng: random.Random) -> dict:
    saturation = round(rng.uniform(0.96, 1.10), 3)
    contrast = round(rng.uniform(0.97, 1.08), 3)
    brightness = round(rng.uniform(-0.018, 0.018), 3)
    speed = round(rng.uniform(0.985, 1.025), 4)
    zoom = round(rng.uniform(1.000, 1.035), 4)
    audio_gain = round(rng.uniform(-0.8, 0.8), 2)

    # Variacion adicional de duracion, deliberadamente pequena.
    # Valores negativos acortan; positivos alargan con congelado final.
    duration_delta = round(rng.uniform(-0.45, 0.45), 3)
    trim_start = round(rng.uniform(0.0, 0.18), 3) if duration_delta < 0 else 0.0

    return {
        "variant_index": i,
        "saturation": saturation,
        "contrast": contrast,
        "brightness": brightness,
        "speed": speed,
        "zoom": zoom,
        "audio_gain_db": audio_gain,
        "duration_delta_s": duration_delta,
        "trim_start_s": trim_start,
    }


def video_filter(profile: dict) -> str:
    speed = profile["speed"]
    zoom = profile["zoom"]
    filters = [
        f"setpts=PTS/{speed}",
        f"eq=saturation={profile['saturation']}:contrast={profile['contrast']}:brightness={profile['brightness']}",
        f"scale=iw*{zoom}:ih*{zoom}",
        "crop=trunc(iw/" + str(zoom) + "/2)*2:trunc(ih/" + str(zoom) + "/2)*2",
    ]

    if profile["duration_delta_s"] > 0:
        filters.append(f"tpad=stop_mode=clone:stop_duration={profile['duration_delta_s']}")

    return ",".join(filters)


def audio_filter(profile: dict) -> str:
    speed = profile["speed"]
    filters = [f"atempo={speed}", f"volume={profile['audio_gain_db']}dB"]
    if profile["duration_delta_s"] > 0:
        filters.append(f"apad=pad_dur={profile['duration_delta_s']}")
    return ",".join(filters)


def render(src: Path, dst: Path, profile: dict, asset_id: str, source_duration: float) -> None:
    created = datetime.now(timezone.utc).isoformat()
    delta = profile["duration_delta_s"]
    trim_start = profile["trim_start_s"]

    # La velocidad ya altera levemente la duracion. Este target agrega una
    # segunda variacion controlada, de unas decimas de segundo.
    sped_duration = max(0.1, source_duration / profile["speed"])
    target_duration = max(0.1, sped_duration + delta - trim_start)

    cmd = ["ffmpeg", "-y"]
    if trim_start > 0:
        cmd += ["-ss", f"{trim_start:.3f}"]
    cmd += [
        "-i", str(src),
        "-map_metadata", "-1",
        "-vf", video_filter(profile),
        "-af", audio_filter(profile),
        "-t", f"{target_duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-metadata", f"title=MusicFit Variant {profile['variant_index']:02d}",
        "-metadata", f"comment=asset_id={asset_id}",
        "-metadata", "software=MusicFit Slightly Change",
        "-metadata", f"creation_time={created}",
        str(dst),
    ]
    run(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera microvariantes trazables de un video")
    ap.add_argument("input", help="Video de entrada")
    ap.add_argument("--variants", type=int, default=4, help="Numero de variantes (default: 4)")
    ap.add_argument("--out", default="variantes", help="Directorio de salida")
    ap.add_argument("--seed", type=int, default=None, help="Semilla reproducible opcional")
    args = ap.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("[ERROR] ffmpeg/ffprobe no estan disponibles en PATH.")
        return 1

    src = Path(args.input).resolve()
    if not src.exists():
        print(f"[ERROR] No existe: {src}")
        return 1

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    seed = args.seed if args.seed is not None else random.SystemRandom().randint(1, 2**31 - 1)
    rng = random.Random(seed)
    source_probe = probe(src)
    source_duration = duration_seconds(source_probe)
    source_hash = sha256(src)

    if source_duration <= 0:
        print("[ERROR] No pude determinar la duracion del video.")
        return 1

    batch_id = uuid.uuid4().hex[:12]
    batch_manifest = {
        "schema": "musicfit.slightly_change.v2",
        "batch_id": batch_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(src),
            "sha256": source_hash,
            "duration_s": source_duration,
            "probe": source_probe,
        },
        "seed": seed,
        "variants": [],
    }

    for i in range(1, max(1, args.variants) + 1):
        asset_id = uuid.uuid4().hex
        profile = build_profile(i, rng)
        stem = src.stem.replace(" ", "_")
        dst = out_dir / f"{stem}__v{i:02d}__{asset_id[:8]}.mp4"
        manifest_path = dst.with_suffix(".json")

        print(f"[{i}/{args.variants}] Generando {dst.name}")
        render(src, dst, profile, asset_id, source_duration)
        output_probe = probe(dst)
        output_duration = duration_seconds(output_probe)

        item = {
            "asset_id": asset_id,
            "parent_sha256": source_hash,
            "output": str(dst),
            "output_sha256": sha256(dst),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "changes": profile,
            "duration": {
                "source_s": round(source_duration, 3),
                "output_s": round(output_duration, 3),
                "actual_delta_s": round(output_duration - source_duration, 3),
            },
            "technical_metadata": {
                "inherited_metadata_removed": True,
                "container": "mp4",
                "video_codec": "h264",
                "audio_codec": "aac",
                "faststart": True,
            },
            "distribution": {
                "platform": None,
                "objective": None,
                "trajectory": None,
                "title": None,
                "description": None,
                "tags": [],
                "thumbnail": None,
                "hypothesis": None,
            },
        }

        manifest_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        batch_manifest["variants"].append(item)

    batch_path = out_dir / f"batch__{batch_id}.json"
    batch_path.write_text(json.dumps(batch_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nListo.")
    print(f"Variantes: {out_dir}")
    print(f"Manifest del lote: {batch_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
