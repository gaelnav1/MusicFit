#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MusicFit — analiza tus videos y tus canciones y decide en qué parte de cada
canción encaja mejor cada video. Luego exporta el video con la música debajo.

Uso rápido:
    1. Pon tus videos en la carpeta  videos/
    2. Pon tus canciones en la carpeta canciones/
    3. Ejecuta:  python musicfit.py
    Los videos terminados aparecen en  resultados/

Qué mira el programa
    Video   -> cortes de escena, cantidad de movimiento a lo largo del tiempo, duración
    Canción -> tempo, beats, compases, energía y secciones (intro, estrofa, coro...)
    Encaje  -> que los cortes del video caigan en beats, que la energía de la
               música suba y baje con el movimiento del video, que la canción
               empiece al inicio de una sección y termine en un punto natural.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import warnings


for _s in (sys.stdout, sys.stderr):  # que los acentos/emojis no rompan la consola de Windows
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _asegurar_dependencias():
    """Si faltan librerías (numpy, opencv, librosa...), las instala solo la primera vez."""
    import importlib
    import importlib.util
    faltan = [paq for mod, paq in [("numpy", "numpy"), ("cv2", "opencv-python-headless"),
                                   ("librosa", "librosa"), ("soundfile", "soundfile")]
              if importlib.util.find_spec(mod) is None]
    if not faltan:
        return
    print(f"\n📦 Primera vez: instalando lo que falta ({', '.join(faltan)})...")
    print("   Puede tardar unos minutos. Solo pasa una vez.\n", flush=True)
    req = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    objetivo = ["-r", req] if os.path.exists(req) else faltan
    r = subprocess.run(base + objetivo)
    if r.returncode != 0:  # sin permisos de administrador: instalar para este usuario
        r = subprocess.run(base + ["--user"] + objetivo)
    if r.returncode != 0:  # pip no viene instalado con este Python
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"])
        r = subprocess.run(base + ["--user"] + objetivo)
    importlib.invalidate_caches()
    if r.returncode != 0 or any(importlib.util.find_spec(m) is None
                                for m in ("numpy", "cv2", "librosa", "soundfile")):
        sys.exit("\n✗ No pude instalar las librerías automáticamente.\n"
                 "  Abre una terminal en esta carpeta y ejecuta:\n"
                 f'     "{sys.executable}" -m pip install -r requirements.txt\n')
    print("\n✓ Librerías instaladas.\n")


if __name__ == "__main__":
    _asegurar_dependencias()

import numpy as np  # noqa: E402

warnings.filterwarnings("ignore")

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".wmv", ".mts"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}

CURVE_HZ = 10  # resolución de las curvas de energía/movimiento (muestras por segundo)

PESOS = {
    "ritmo": 0.35,     # cortes del video sobre los beats
    "energia": 0.25,   # movimiento del video vs. energía de la música
    "inicio": 0.15,    # empieza en inicio de sección / compás
    "final": 0.15,     # termina en un punto natural
    "intensidad": 0.10 # nivel de energía del tramo acorde al video
}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def log(msg=""):
    print(msg, flush=True)


def listar(carpeta_o_archivos, extensiones):
    rutas = []
    for item in carpeta_o_archivos:
        if os.path.isdir(item):
            for nombre in sorted(os.listdir(item)):
                if os.path.splitext(nombre)[1].lower() in extensiones:
                    rutas.append(os.path.join(item, nombre))
        elif os.path.isfile(item) and os.path.splitext(item)[1].lower() in extensiones:
            rutas.append(item)
    return rutas


def fmt_t(seg):
    seg = max(0.0, float(seg))
    m = int(seg // 60)
    s = seg - 60 * m
    return f"{m}:{s:05.2f}"


def suavizar(x, ventana):
    ventana = max(1, int(ventana))
    if ventana <= 1 or len(x) < ventana:
        return x
    k = np.ones(ventana) / ventana
    return np.convolve(x, k, mode="same")


def normalizar(x):
    x = np.asarray(x, dtype=float)
    lo, hi = np.percentile(x, 5), np.percentile(x, 95)
    if hi - lo < 1e-9:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0, 1)


def tiene_audio(ruta):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=index", "-of", "csv=p=0", ruta],
            capture_output=True, text=True, timeout=60)
        return bool(out.stdout.strip())
    except Exception:
        return False


def duracion_ffprobe(ruta):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", ruta],
        capture_output=True, text=True, timeout=60)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Análisis de video
# --------------------------------------------------------------------------- #

def analizar_video(ruta):
    import cv2

    cap = cv2.VideoCapture(ruta)
    if not cap.isOpened():
        raise RuntimeError("No se pudo abrir el video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps < 1 or fps > 240:
        fps = 30.0

    tiempos, movimiento, dist_hist = [], [], []
    prev_gray, prev_hist = None, None
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        i += 1
        small = cv2.resize(frame, (96, 54), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        if prev_gray is None:
            movimiento.append(0.0)
            dist_hist.append(0.0)
        else:
            movimiento.append(float(np.mean(np.abs(gray - prev_gray))))
            dist_hist.append(float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)))
        tiempos.append(t)
        prev_gray, prev_hist = gray, hist
    cap.release()

    if not tiempos:
        raise RuntimeError("El video no tiene fotogramas legibles")

    tiempos = np.array(tiempos)
    movimiento = np.array(movimiento)
    dist_hist = np.array(dist_hist)

    dur = duracion_ffprobe(ruta) or (tiempos[-1] + 1.0 / fps)

    # --- Cortes de escena: salto fuerte de color + salto de píxeles, adaptativo ---
    cortes = []
    if len(dist_hist) > 3:
        base = np.median(dist_hist) + 4 * np.std(dist_hist)
        umbral = max(0.35, min(base, 0.6))
        mov_ref = np.percentile(movimiento, 90) if len(movimiento) else 0
        ultimo = -10.0
        for k in range(1, len(dist_hist)):
            if dist_hist[k] > umbral and movimiento[k] > max(8.0, 0.8 * mov_ref * 0.5):
                if tiempos[k] - ultimo > 0.4:  # no dos cortes en menos de 0.4 s
                    cortes.append(float(tiempos[k]))
                    ultimo = tiempos[k]

    # --- Curva de movimiento a CURVE_HZ (sin contar los cortes, que son picos falsos) ---
    mov_sin_cortes = movimiento.copy()
    for c in cortes:
        k = int(round(c * fps))
        mov_sin_cortes[max(0, k - 1):k + 2] = np.median(movimiento)
    n = max(1, int(np.ceil(dur * CURVE_HZ)))
    curva = np.zeros(n)
    idx = np.minimum((tiempos * CURVE_HZ).astype(int), n - 1)
    cuenta = np.bincount(idx, minlength=n).astype(float)
    suma = np.bincount(idx, weights=mov_sin_cortes, minlength=n)
    curva = np.where(cuenta > 0, suma / np.maximum(cuenta, 1), 0)
    # rellenar huecos
    if np.any(cuenta == 0):
        validos = np.where(cuenta > 0)[0]
        curva = np.interp(np.arange(n), validos, curva[validos])
    curva = suavizar(curva, CURVE_HZ // 2)

    # --- Momentos de acción (picos de movimiento) por si el video no tiene cortes ---
    acentos = []
    if len(curva) > 5:
        d = np.diff(curva)
        umbral = np.percentile(d, 92)
        ultimo = -10
        for k in range(1, len(d) - 1):
            if d[k] > umbral and d[k] >= d[k - 1] and d[k] >= d[k + 1] and d[k] > 0:
                t = k / CURVE_HZ
                if t - ultimo > 0.6:
                    acentos.append(t)
                    ultimo = t

    return {
        "ruta": ruta,
        "nombre": os.path.basename(ruta),
        "duracion": float(dur),
        "fps": float(fps),
        "cortes": cortes,
        "acentos": acentos,
        "movimiento": curva,                     # bruto suavizado
        "movimiento_medio": float(np.mean(curva)),
        "tiene_audio": tiene_audio(ruta),
    }


# --------------------------------------------------------------------------- #
# Análisis de canción
# --------------------------------------------------------------------------- #

def analizar_cancion(ruta):
    import librosa

    sr = 22050
    y, sr = librosa.load(ruta, sr=sr, mono=True)
    if len(y) < sr:
        raise RuntimeError("La canción dura menos de 1 segundo")
    dur = len(y) / sr
    hop = 512

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=hop)
    tempo = float(np.atleast_1d(tempo)[0])
    beats = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
    if len(beats) < 8:  # canción sin pulso claro: rejilla cada 0.5 s
        beats = np.arange(0, dur, 0.5)
        beat_frames = librosa.time_to_frames(beats, sr=sr, hop_length=hop)

    # Compases (4/4): elegir la fase de 4 beats con más fuerza de ataque
    fuerza = onset_env[np.minimum(beat_frames, len(onset_env) - 1)]
    mejor_fase = int(np.argmax([fuerza[f::4].sum() for f in range(4)]))
    compases = beats[mejor_fase::4]

    # Energía (RMS) a CURVE_HZ
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    t_rms = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    n = int(np.ceil(dur * CURVE_HZ))
    energia = np.interp(np.arange(n) / CURVE_HZ, t_rms, rms)
    energia = suavizar(energia, CURVE_HZ // 2)

    # Secciones (intro / estrofa / coro...) por agrupamiento de timbre y armonía
    secciones = [0.0]
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)
        feats = np.vstack([librosa.util.normalize(chroma, axis=1),
                           librosa.util.normalize(mfcc, axis=1)])
        sinc = librosa.util.sync(feats, beat_frames, aggregate=np.median)
        k = int(np.clip(round(dur / 15), 3, 16))
        if sinc.shape[1] > k + 1:
            limites = librosa.segment.agglomerative(sinc, k)
            limites_frames = np.array(beat_frames)[np.minimum(limites, len(beat_frames) - 1)]
            secciones = sorted(set([0.0] + [float(t) for t in
                               librosa.frames_to_time(limites_frames, sr=sr, hop_length=hop)]))
    except Exception:
        pass
    # ajustar secciones al compás más cercano
    if len(compases):
        secciones = sorted(set(float(compases[np.argmin(np.abs(compases - s))]) if s > 0 else 0.0
                               for s in secciones))

    # dónde empieza el sonido de verdad (saltar silencio inicial)
    umbral_sil = 0.05 * np.max(energia)
    inicio_sonido = float(np.argmax(energia > umbral_sil) / CURVE_HZ)

    return {
        "ruta": ruta,
        "nombre": os.path.basename(ruta),
        "duracion": float(dur),
        "tempo": tempo,
        "beats": np.asarray(beats, dtype=float),
        "compases": np.asarray(compases, dtype=float),
        "secciones": np.asarray(secciones, dtype=float),
        "energia": energia,
        "energia_norm": normalizar(energia),
        "inicio_sonido": inicio_sonido,
    }


# --------------------------------------------------------------------------- #
# Encaje video <-> canción
# --------------------------------------------------------------------------- #

def _dist_min(t, arr):
    if len(arr) == 0:
        return 99.0
    i = np.searchsorted(arr, t)
    cand = []
    if i < len(arr):
        cand.append(abs(arr[i] - t))
    if i > 0:
        cand.append(abs(arr[i - 1] - t))
    return min(cand)


def _corr(a, b):
    if len(a) < 5 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def evaluar(video, cancion, estilo="auto"):
    """Prueba cada beat como posible inicio y devuelve el mejor tramo."""
    D = video["duracion"]
    S = cancion["duracion"]
    beats = cancion["beats"]
    compases = cancion["compases"]
    secciones = cancion["secciones"]
    energia_n = cancion["energia_norm"]

    puntos = video["cortes"] if len(video["cortes"]) >= 2 else video["acentos"]
    puntos = [p for p in puntos if 0.3 < p < D - 0.3]
    mov = normalizar(video["movimiento"])
    nv = len(mov)

    corta = S < D
    if corta:
        candidatos = [0.0]
    else:
        candidatos = [b for b in beats if b >= cancion["inicio_sonido"] - 0.05 and b + D <= S + 0.05]
        if cancion["inicio_sonido"] < 0.3:
            candidatos = [0.0] + candidatos
        if not candidatos:
            candidatos = [max(0.0, S - D)]

    # nivel deseado de intensidad
    if estilo == "energetico":
        objetivo = 0.85
    elif estilo == "tranquilo":
        objetivo = 0.35
    else:  # auto: según cuánto se mueve el video
        objetivo = float(np.clip(0.35 + video["movimiento_medio"] / 25.0, 0.35, 0.9))

    mejor = None
    for s in candidatos:
        # 1) Ritmo: cortes sobre beats (tolerancia ~1 fotograma y medio)
        if puntos:
            d = np.array([_dist_min(s + p, beats) for p in puntos])
            ritmo = float(np.mean(np.exp(-(d / 0.06) ** 2)))
            en_compas = np.array([_dist_min(s + p, compases) for p in puntos])
            ritmo = 0.8 * ritmo + 0.2 * float(np.mean(np.exp(-(en_compas / 0.08) ** 2)))
        else:
            ritmo = 0.5  # video de una sola toma sin acentos: neutro

        # 2) Energía: el movimiento del video sube y baja con la música
        i0 = int(round(s * CURVE_HZ))
        tramo = energia_n[i0:i0 + nv]
        if len(tramo) < nv:  # canción más corta: se repite
            tramo = np.resize(energia_n, nv) if corta else np.pad(tramo, (0, nv - len(tramo)), mode="edge")
        energia = (_corr(mov, tramo) + 1) / 2 if np.std(mov) > 0.05 else 0.5

        # 3) Inicio natural
        if _dist_min(s, secciones) < 0.15:
            inicio = 1.0
        elif _dist_min(s, compases) < 0.05:
            inicio = 0.7
        else:
            inicio = 0.4
        if s == 0.0:
            inicio = max(inicio, 0.9)

        # 4) Final natural: termina en cambio de sección, fin de canción o compás
        e = s + D
        if corta:
            final = 0.3
        elif abs(S - e) < 1.0:
            final = 1.0
        elif _dist_min(e, secciones) < 0.4:
            final = 0.95
        elif _dist_min(e, compases) < 0.08:
            final = 0.65
        else:
            final = 0.3

        # 5) Intensidad del tramo
        nivel = float(np.mean(tramo)) if len(tramo) else 0
        intensidad = float(np.exp(-((nivel - objetivo) / 0.25) ** 2))

        parciales = {"ritmo": ritmo, "energia": energia, "inicio": inicio,
                     "final": final, "intensidad": intensidad}
        total = sum(PESOS[k] * v for k, v in parciales.items())
        if corta:
            total *= 0.75
        if mejor is None or total > mejor["puntuacion"]:
            mejor = {"inicio": float(s), "fin": float(min(e, S)), "puntuacion": float(total),
                     "detalle": parciales, "cortes_usados": len(puntos), "repite": corta}

    mejor["cancion"] = cancion["nombre"]
    mejor["ruta_cancion"] = cancion["ruta"]
    mejor["tempo"] = cancion["tempo"]
    return mejor


# --------------------------------------------------------------------------- #
# Exportar
# --------------------------------------------------------------------------- #

def volumen_medio(ruta, inicio=None, duracion=None, mapa=None):
    """Volumen medio en dB (ffmpeg volumedetect). None si no se puede medir."""
    import re
    cmd = ["ffmpeg", "-hide_banner", "-nostats"]
    if inicio is not None:
        cmd += ["-ss", f"{inicio:.3f}"]
    if duracion is not None:
        cmd += ["-t", f"{duracion:.3f}"]
    cmd += ["-i", ruta]
    if mapa:
        cmd += ["-map", mapa]
    cmd += ["-vn", "-af", "volumedetect", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", r.stderr)
    if not m or m.group(1) == "-inf":
        return None
    return float(m.group(1))


def exportar(video, eleccion, salida, vol_musica, vol_original, solo_musica,
             fondo=False, fondo_db=14.0, ducking=True):
    D = video["duracion"]
    s = eleccion["inicio"]
    fade_in = 0.05 if eleccion["detalle"]["inicio"] >= 0.9 else 0.4
    fade_out = 0.4 if eleccion["detalle"]["final"] >= 0.95 else min(2.0, D / 4)
    fo_ini = max(0.0, D - fade_out)
    con_original = video["tiene_audio"] and not solo_musica

    info = ""
    ganancia = f"volume={vol_musica}"
    if fondo and con_original:
        # Nivelar: la música queda `fondo_db` dB por debajo del audio original
        db_orig = volumen_medio(video["ruta"], mapa="0:a:0")
        db_mus = volumen_medio(eleccion["ruta_cancion"], 0 if eleccion["repite"] else s, D)
        if db_orig is not None and db_orig > -55 and db_mus is not None:
            ajuste = (db_orig + 20 * np.log10(max(vol_original, 1e-3)) - fondo_db) - db_mus
            ajuste = float(np.clip(ajuste, -40, 6))
            ganancia = f"volume={ajuste:.2f}dB"
            info = f"música {ajuste:+.1f} dB → {fondo_db:.0f} dB por debajo del original"
        else:  # el video casi no tiene sonido: no hay nada que tapar
            ganancia = f"volume={vol_musica}"
            info = "el video casi no tiene sonido: música a volumen normal"
            ducking = False

    musica = (f"[1:a]atrim=start={s:.3f}:duration={D:.3f},asetpts=PTS-STARTPTS,"
              f"aresample=48000,aformat=channel_layouts=stereo,"
              f"afade=t=in:st=0:d={fade_in},afade=t=out:st={fo_ini:.3f}:d={fade_out:.3f},"
              f"{ganancia}[m]")

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video["ruta"]]
    if eleccion["repite"]:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", eleccion["ruta_cancion"]]

    if con_original:
        orig = f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume={vol_original}"
        if fondo and ducking:
            # ducking: cuando suena el original (voz, ruido de escena) la música baja sola
            filtro = (musica + ";" + orig + ",asplit=2[o][sc];"
                      "[m][sc]sidechaincompress=threshold=0.015:ratio=6:attack=15:release=350:"
                      "makeup=1:knee=4[md];"
                      "[o][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
            info += (" · " if info else "") + "ducking activado"
        else:
            filtro = (musica + ";" + orig + "[o];"
                      "[o][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    else:
        filtro = musica.replace("[m]", "[a]")

    cmd += ["-filter_complex", filtro, "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{D:.3f}",
            "-movflags", "+faststart", salida]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:  # algunos contenedores no aceptan copiar el video: recodificar
        cmd[cmd.index("copy")] = "libx264"
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[-400:])
    return info


# --------------------------------------------------------------------------- #
# Programa principal
# --------------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(
        description="Analiza videos y canciones, pone a cada video la canción y el tramo que mejor le "
                    "encajan, y extrae todos los thumbnails posibles de cada video.")
    p.add_argument("--videos", nargs="+", default=["videos"], help="carpeta(s) o archivos de video")
    p.add_argument("--canciones", nargs="+", default=["canciones"], help="carpeta(s) o archivos de audio")
    p.add_argument("--salida", default="resultados", help="carpeta de resultados")
    p.add_argument("--estilo", choices=["auto", "energetico", "tranquilo"], default="auto",
                   help="qué tipo de tramo prefieres (auto = según el movimiento del video)")
    p.add_argument("--no-repetir", action="store_true",
                   help="no usar la misma canción en dos videos")
    p.add_argument("--vol-musica", type=float, default=0.6, help="volumen de la canción (0-1)")
    p.add_argument("--vol-original", type=float, default=1.0, help="volumen del audio original del video")
    p.add_argument("--solo-musica", action="store_true", help="quitar el audio original del video")
    p.add_argument("--musica-fondo", action="store_true",
                   help="la música queda en segundo plano: por debajo del audio original y "
                        "baja sola cuando hay voz o sonido en el video")
    p.add_argument("--fondo-db", type=float, default=14.0,
                   help="cuántos dB por debajo del audio original queda la música (por defecto 14; "
                        "más número = más bajita")
    p.add_argument("--sin-ducking", action="store_true",
                   help="con --musica-fondo, no bajar la música automáticamente cuando hay voz")
    p.add_argument("--solo-analizar", action="store_true", help="no exportar videos, solo el informe")
    p.add_argument("--top", type=int, default=3, help="cuántas opciones mostrar por video")
    g = p.add_argument_group("thumbnails")
    g.add_argument("--solo-thumbnails", action="store_true",
                   help="solo sacar thumbnails (no hace falta tener canciones)")
    g.add_argument("--sin-thumbnails", action="store_true", help="no sacar thumbnails")
    g.add_argument("--thumbs-intervalo", type=float, default=0.5,
                   help="segundos entre fotogramas candidatos (0 = revisar TODOS los fotogramas)")
    g.add_argument("--thumbs-sin-filtro", action="store_true",
                   help="guardar también los borrosos, oscuros y repetidos")
    g.add_argument("--galeria", action="store_true",
                   help="solo abrir la galería de thumbnails ya generada")
    g.add_argument("--no-abrir", action="store_true", help="no abrir la galería al terminar")
    g.add_argument("--puerto", type=int, default=8765, help="puerto local de la galería")
    a = p.parse_args()

    import galeria

    if a.galeria:
        galeria.servir(a.salida, a.puerto, abrir=True)
        return

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit("Falta ffmpeg. Instálalo (ver LEEME.md) y vuelve a intentarlo.")

    videos = listar(a.videos, VIDEO_EXT)
    if not videos:
        sys.exit(f"No encontré videos en: {', '.join(a.videos)}")
    canciones = [] if a.solo_thumbnails else listar(a.canciones, AUDIO_EXT)
    hacer_musica = bool(canciones)
    hacer_thumbs = not a.sin_thumbnails
    if not hacer_musica and not a.solo_thumbnails:
        log(f"\n⚠  No encontré canciones en: {', '.join(os.path.abspath(c) for c in a.canciones)}")
        log(f"   Formatos que acepto: {', '.join(sorted(AUDIO_EXT))}")
        log("   Por ahora solo saco thumbnails.")
    if not hacer_musica and not hacer_thumbs:
        sys.exit("No hay nada que hacer: faltan canciones y los thumbnails están desactivados.")
    os.makedirs(a.salida, exist_ok=True)

    an_canciones = []
    if hacer_musica:
        log(f"\n🎵 Analizando {len(canciones)} canción(es)...")
        for r in canciones:
            try:
                c = analizar_cancion(r)
                an_canciones.append(c)
                log(f"   ✓ {c['nombre']}  ({fmt_t(c['duracion'])}, {c['tempo']:.0f} BPM, "
                    f"{len(c['secciones'])} secciones)")
            except Exception as e:
                log(f"   ✗ {os.path.basename(r)}: {e}")

    log(f"\n🎬 Analizando {len(videos)} video(s)...")
    an_videos = []
    for r in videos:
        try:
            v = analizar_video(r)
            an_videos.append(v)
            log(f"   ✓ {v['nombre']}  ({fmt_t(v['duracion'])}, {len(v['cortes'])} cortes, "
                f"movimiento {v['movimiento_medio']:.1f})")
        except Exception as e:
            log(f"   ✗ {os.path.basename(r)}: {e}")
    if not an_videos:
        sys.exit("No se pudo analizar ningún video.")

    elegidas, exportados = {}, {}
    if hacer_musica and an_canciones:
        elegidas, exportados = musica(a, an_videos, an_canciones)

    if hacer_thumbs:
        thumbs(a, an_videos, elegidas, exportados, galeria)

    log("\n✅ Listo.")
    if hacer_thumbs and not a.no_abrir:
        galeria.servir(a.salida, a.puerto, abrir=True)
    elif hacer_thumbs:
        log(f"   Para ver los thumbnails:  python musicfit.py --galeria\n")


def musica(a, an_videos, an_canciones):
    log("\n🔎 Buscando el mejor encaje...")
    tabla = []
    for v in an_videos:
        opciones = sorted((evaluar(v, c, a.estilo) for c in an_canciones),
                          key=lambda o: -o["puntuacion"])
        tabla.append((v, opciones))

    # asignación (opcionalmente sin repetir canción; primero los videos con mejor opción)
    usadas, elegidas = set(), {}
    for v, opciones in sorted(tabla, key=lambda x: -x[1][0]["puntuacion"]):
        for o in opciones:
            if not a.no_repetir or o["cancion"] not in usadas:
                elegidas[v["ruta"]] = o
                usadas.add(o["cancion"])
                break
        else:
            elegidas[v["ruta"]] = opciones[0]

    filas, informe = [], []
    for v, opciones in tabla:
        e = elegidas[v["ruta"]]
        log(f"\n━━ {v['nombre']} ({fmt_t(v['duracion'])})")
        for n, o in enumerate(opciones[:a.top], 1):
            marca = "★" if o is e else " "
            d = o["detalle"]
            log(f"  {marca} {n}. {o['cancion']}  desde {fmt_t(o['inicio'])} hasta {fmt_t(o['fin'])}"
                f"  → {o['puntuacion'] * 100:.0f}/100"
                f"   [ritmo {d['ritmo']*100:.0f} · energía {d['energia']*100:.0f} · "
                f"inicio {d['inicio']*100:.0f} · final {d['final']*100:.0f} · "
                f"intensidad {d['intensidad']*100:.0f}]"
                + ("  (la canción es más corta: se repite)" if o["repite"] else ""))
        for o in opciones:
            filas.append({
                "video": v["nombre"], "cancion": o["cancion"],
                "inicio_seg": round(o["inicio"], 2), "inicio": fmt_t(o["inicio"]),
                "fin": fmt_t(o["fin"]), "puntuacion": round(o["puntuacion"] * 100, 1),
                **{k: round(val * 100, 1) for k, val in o["detalle"].items()},
                "elegida": "sí" if o is e else "",
            })
        informe.append({
            "video": v["nombre"], "duracion": round(v["duracion"], 2),
            "cortes_detectados": [round(c, 2) for c in v["cortes"]],
            "eleccion": {k: (round(val, 3) if isinstance(val, float) else val)
                         for k, val in e.items() if k != "detalle"},
            "detalle": {k: round(val, 3) for k, val in e["detalle"].items()},
        })

    with open(os.path.join(a.salida, "ranking.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    with open(os.path.join(a.salida, "informe.json"), "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)
    log(f"\n📄 Ranking completo en {os.path.join(a.salida, 'ranking.csv')}")

    exportados = {}
    if not a.solo_analizar:
        log("\n💾 Exportando videos con música"
            + (" de fondo..." if a.musica_fondo else "..."))
        for v, _ in tabla:
            e = elegidas[v["ruta"]]
            base = os.path.splitext(v["nombre"])[0]
            cancion = os.path.splitext(e["cancion"])[0]
            nombre = f"{base} + {cancion}.mp4"
            try:
                info = exportar(v, e, os.path.join(a.salida, nombre), a.vol_musica, a.vol_original,
                                a.solo_musica, a.musica_fondo, a.fondo_db, not a.sin_ducking)
                exportados[v["ruta"]] = nombre
                log(f"   ✓ {os.path.join(a.salida, nombre)}" + (f"   ({info})" if info else ""))
            except Exception as ex:
                log(f"   ✗ {v['nombre']}: {ex}")
    return elegidas, exportados


def thumbs(a, an_videos, elegidas, exportados, galeria):
    from thumbnails import extraer_thumbnails

    log("\n🖼  Sacando thumbnails...")
    raiz = os.path.join(a.salida, "thumbnails")
    os.makedirs(raiz, exist_ok=True)
    nuevos = []
    for v in an_videos:
        base = os.path.splitext(v["nombre"])[0]
        carpeta = os.path.join(raiz, base)

        def progreso(x, nombre=v["nombre"]):
            print(f"\r   … {nombre}: {x * 100:5.1f}%", end="", flush=True)

        try:
            lista, info = extraer_thumbnails(v["ruta"], carpeta, v["cortes"], a.thumbs_intervalo,
                                             a.thumbs_sin_filtro, progreso)
        except Exception as ex:
            print()
            log(f"   ✗ {v['nombre']}: {ex}")
            continue
        print("\r" + " " * 70 + "\r", end="")
        if not lista:
            log(f"   ✗ {v['nombre']}: no se pudo leer ningún fotograma")
            continue
        log(f"   ✓ {v['nombre']}: {len(lista)} thumbnails"
            + (f" ({info['descartados']} descartados)" if info["descartados"] else "")
            + f"  → {carpeta}")
        e = elegidas.get(v["ruta"])
        nuevos.append({
            "nombre": v["nombre"], "base": base, "ruta_fuente": os.path.abspath(v["ruta"]),
            "carpeta": f"thumbnails/{base}", "zip": f"thumbnails/{base}.zip",
            "fps": info["fps"], "duracion": v["duracion"],
            "ancho": lista[0]["ancho"], "alto": lista[0]["alto"],
            "descartados": info["descartados"],
            "resultado": exportados.get(v["ruta"]),
            "cancion": e["cancion"] if e else None,
            "thumbs": lista,
        })
    if nuevos:
        ruta = galeria.guardar_galeria(a.salida, nuevos)
        log(f"\n🖼  Galería: {ruta}")


if __name__ == "__main__":
    main()
