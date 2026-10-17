#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MusicFit Thumbnail Improver

Genera variantes de thumbnail de alta estimulacion visual a partir de una
imagen base. El objetivo no es "decorar", sino aumentar legibilidad en movil,
contraste local y separacion sujeto/fondo de forma reproducible.

Uso:
    python thumbnail_improver.py imagen.png
    python thumbnail_improver.py imagen.png --out thumbs_mejorados --variants 5

Requiere: numpy, opencv-python-headless
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def clamp(x, lo=0, hi=255):
    return np.clip(x, lo, hi).astype(np.uint8)


def resize_cover(img: np.ndarray, width: int, height: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = max(width / w, height / h)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    interp = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    r = cv2.resize(img, (nw, nh), interpolation=interp)
    x = max(0, (nw - width) // 2)
    y = max(0, (nh - height) // 2)
    return r[y:y + height, x:x + width]


def local_contrast(img: np.ndarray, strength: float) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.5 + 2.2 * strength, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    out = cv2.merge([l2, a, b])
    return cv2.cvtColor(out, cv2.COLOR_LAB2BGR)


def color_push(img: np.ndarray, strength: float) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] *= 1.0 + 0.28 * strength
    hsv[..., 2] *= 1.0 + 0.06 * strength
    hsv[..., 1] = np.clip(hsv[..., 1], 0, 255)
    hsv[..., 2] = np.clip(hsv[..., 2], 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # Empuje moderado de familias cromaticas que sobreviven bien en pantallas pequeñas.
    b, g, r = cv2.split(out.astype(np.float32))
    r *= 1.0 + 0.08 * strength
    b *= 1.0 + 0.045 * strength
    return clamp(cv2.merge([b, g, r]))


def unsharp(img: np.ndarray, strength: float) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), 1.15)
    return cv2.addWeighted(img, 1.0 + 0.65 * strength, blur, -0.65 * strength, 0)


def glow(img: np.ndarray, strength: float) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = hsv[..., 2]
    _, mask = cv2.threshold(mask, 175, 255, cv2.THRESH_BINARY)
    mask = cv2.GaussianBlur(mask, (0, 0), 12 + 12 * strength)
    glow_layer = cv2.GaussianBlur(img, (0, 0), 8 + 10 * strength)
    alpha = (mask.astype(np.float32) / 255.0 * (0.08 + 0.12 * strength))[..., None]
    return clamp(img.astype(np.float32) * (1 - alpha) + glow_layer.astype(np.float32) * alpha + 8 * alpha)


def center_separation(img: np.ndarray, strength: float) -> np.ndarray:
    """Heuristica sin segmentacion: preserva/realza el centro y comprime el borde."""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = w * 0.5, h * 0.48
    dx = (xx - cx) / (w * 0.56)
    dy = (yy - cy) / (h * 0.60)
    d = np.sqrt(dx * dx + dy * dy)
    center = np.clip(1.0 - d, 0, 1)
    center = cv2.GaussianBlur(center.astype(np.float32), (0, 0), 18)

    # Fondo ligeramente mas oscuro/desaturado; centro ligeramente mas brillante.
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    bg = 1.0 - center
    hsv[..., 1] *= 1.0 - bg * (0.10 * strength)
    hsv[..., 2] *= 1.0 - bg * (0.16 * strength)
    hsv[..., 2] *= 1.0 + center * (0.05 * strength)
    hsv = np.clip(hsv, 0, 255).astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def vignette(img: np.ndarray, strength: float) -> np.ndarray:
    h, w = img.shape[:2]
    kx = cv2.getGaussianKernel(w, w * 0.55)
    ky = cv2.getGaussianKernel(h, h * 0.55)
    mask = ky @ kx.T
    mask /= mask.max()
    mask = 1.0 - (1.0 - mask) * (0.18 * strength)
    return clamp(img.astype(np.float32) * mask[..., None])


def micro_zoom(img: np.ndarray, strength: float) -> np.ndarray:
    zoom = 1.0 + 0.018 * strength
    h, w = img.shape[:2]
    nw, nh = int(round(w * zoom)), int(round(h * zoom))
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_CUBIC)
    x = (nw - w) // 2
    y = (nh - h) // 2
    return r[y:y + h, x:x + w]


def improve(img: np.ndarray, level: int) -> np.ndarray:
    strength = level / 5.0
    out = local_contrast(img, strength)
    out = color_push(out, strength)
    out = center_separation(out, strength)
    out = unsharp(out, strength)
    out = glow(out, strength)
    out = vignette(out, strength)
    out = micro_zoom(out, strength)
    return out


def stimulus_score(img: np.ndarray) -> dict:
    """Score heuristico, no predictor de CTR. Sirve para ordenar variantes."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    contrast = float(gray.std()) / 64.0
    saturation = float(hsv[..., 1].mean()) / 255.0
    edges = cv2.Canny(gray, 80, 180)
    edge_density = float((edges > 0).mean())

    h, w = gray.shape
    cy0, cy1 = int(h * 0.2), int(h * 0.8)
    cx0, cx1 = int(w * 0.2), int(w * 0.8)
    center = gray[cy0:cy1, cx0:cx1]
    center_contrast = float(center.std()) / 64.0 if center.size else 0.0

    score = (
        0.31 * min(contrast, 1.5) +
        0.26 * saturation +
        0.20 * min(edge_density * 7.0, 1.2) +
        0.23 * min(center_contrast, 1.5)
    )
    return {
        "score": round(float(score), 4),
        "contrast": round(contrast, 4),
        "saturation": round(saturation, 4),
        "edge_density": round(edge_density, 4),
        "center_contrast": round(center_contrast, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera thumbnails de alta estimulacion visual")
    ap.add_argument("input", help="Imagen de entrada")
    ap.add_argument("--out", default="thumbnails_mejorados", help="Directorio de salida")
    ap.add_argument("--variants", type=int, default=5, help="Numero de intensidades 1-5")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] No existe: {src}")
        return 1

    img = cv2.imread(str(src), cv2.IMREAD_COLOR)
    if img is None:
        print(f"[ERROR] No pude leer la imagen: {src}")
        return 1

    base = resize_cover(img, args.width, args.height)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    n = max(1, min(5, args.variants))
    report = {
        "source": str(src),
        "size": [args.width, args.height],
        "note": "stimulus_score es heuristico; no representa CTR real",
        "variants": [],
    }

    stem = src.stem.replace(" ", "_")
    for level in range(1, n + 1):
        out = improve(base, level)
        metrics = stimulus_score(out)
        dst = out_dir / f"{stem}__stimulus_{level}.jpg"
        cv2.imwrite(str(dst), out, [cv2.IMWRITE_JPEG_QUALITY, 95])
        report["variants"].append({
            "level": level,
            "output": str(dst),
            "metrics": metrics,
        })
        print(f"[{level}/{n}] {dst}  score={metrics['score']}")

    report["variants"].sort(key=lambda x: x["metrics"]["score"], reverse=True)
    report_path = out_dir / f"{stem}__report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nListo.")
    print(f"Mejor segun heuristica: {report['variants'][0]['output']}")
    print(f"Reporte: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
