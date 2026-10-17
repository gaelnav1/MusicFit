# -*- coding: utf-8 -*-
"""
Extracción de thumbnails: recorre el video, guarda los fotogramas candidatos,
descarta los negros, borrosos o repetidos y los ordena por calidad.
"""

import bisect
import os
import shutil
import zipfile

import numpy as np


def _guardar_jpg(ruta, img, calidad=92):
    import cv2
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    if ok:  # imencode + open() funciona también con tildes/ñ en Windows
        with open(ruta, "wb") as f:
            f.write(buf.tobytes())
    return ok


def _rango(x):
    x = np.asarray(x, dtype=float)
    lo, hi = np.percentile(x, 5), np.percentile(x, 95)
    if hi - lo < 1e-9:
        return np.full_like(x, 0.5)
    return np.clip((x - lo) / (hi - lo), 0, 1)


def _colorido(img):
    b, g, r = [c.astype(np.float32) for c in (img[..., 0], img[..., 1], img[..., 2])]
    rg, yb = r - g, 0.5 * (r + g) - b
    return float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))


def _nombre_tiempo(t):
    m = int(t // 60)
    return f"{m}m{t - 60 * m:05.2f}s"


def extraer_thumbnails(ruta_video, carpeta, cortes=None, intervalo=0.5, sin_filtro=False,
                       progreso=None):
    """
    Devuelve una lista de thumbnails (dicts) ordenada de mejor a peor y deja los
    JPG en `carpeta` más un ZIP con todos ellos en `carpeta`.zip.

    intervalo  : segundos entre fotogramas candidatos (0 = todos los fotogramas)
    sin_filtro : no descartar borrosos/negros/repetidos
    """
    import cv2

    cortes = sorted(cortes or [])
    base = os.path.splitext(os.path.basename(ruta_video))[0]

    cap = cv2.VideoCapture(ruta_video)
    if not cap.isOpened():
        raise RuntimeError("No se pudo abrir el video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps < 1 or fps > 240:
        fps = 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    paso = 1 if intervalo <= 0 else max(1, int(round(intervalo * fps)))

    try:
        caras = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if caras.empty():
            caras = None
    except Exception:
        caras = None

    if os.path.isdir(carpeta):
        shutil.rmtree(carpeta)
    tmp = carpeta + "__tmp"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)

    cands = []
    i = 0
    while True:
        if i % paso:
            if not cap.grab():
                break
            i += 1
            continue
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        alto, ancho = frame.shape[:2]
        esc = 480.0 / ancho
        peq = cv2.resize(frame, (480, max(1, int(alto * esc))), interpolation=cv2.INTER_AREA)
        gris = cv2.cvtColor(peq, cv2.COLOR_BGR2GRAY)

        n_caras = 0
        if caras is not None:
            det = caras.detectMultiScale(gris, scaleFactor=1.15, minNeighbors=6,
                                         minSize=(max(24, gris.shape[0] // 12),) * 2)
            n_caras = len(det)

        archivo = os.path.join(tmp, f"{i:07d}.jpg")
        if _guardar_jpg(archivo, frame):
            cands.append({
                "frame": i, "t": t, "archivo_tmp": archivo,
                "nitidez": float(cv2.Laplacian(gris, cv2.CV_64F).var()),
                "brillo": float(gris.mean()),
                "contraste": float(gris.std()),
                "color": _colorido(peq),
                "caras": int(n_caras),
                "firma": cv2.resize(gris, (32, 18), interpolation=cv2.INTER_AREA).astype(np.float32),
                "escena": bisect.bisect_right(cortes, t),
                "ancho": int(ancho), "alto": int(alto),
            })
        if progreso and total:
            progreso(min(1.0, i / total))
        i += 1
    cap.release()

    if not cands:
        shutil.rmtree(tmp, ignore_errors=True)
        return [], None

    # --- descartar fotogramas inútiles ---
    descartados = 0
    if not sin_filtro and len(cands) > 3:
        med_nitidez = float(np.median([c["nitidez"] for c in cands]))
        buenos = [c for c in cands
                  if 18 < c["brillo"] < 240 and c["contraste"] > 10
                  and c["nitidez"] > 0.3 * med_nitidez]
        if len(buenos) >= max(3, len(cands) // 10):  # no vaciar videos oscuros/suaves
            descartados += len(cands) - len(buenos)
            cands = buenos

    # --- puntuación de calidad 0-100 ---
    nit = _rango([np.log1p(c["nitidez"]) for c in cands])
    con = _rango([c["contraste"] for c in cands])
    col = _rango([c["color"] for c in cands])
    for k, c in enumerate(cands):
        expo = 1 - abs(c["brillo"] - 128) / 128
        cara = 1.0 if c["caras"] else 0.0
        c["puntuacion"] = round(100 * (0.38 * nit[k] + 0.18 * con[k] + 0.14 * col[k]
                                       + 0.12 * expo + 0.18 * cara), 1)

    cands.sort(key=lambda c: -c["puntuacion"])

    # --- quitar casi-duplicados (se queda el de mejor calidad) ---
    if not sin_filtro:
        unicos = []
        for c in cands:
            if all(np.mean(np.abs(c["firma"] - u["firma"])) >= 5.0 for u in unicos):
                unicos.append(c)
        descartados += len(cands) - len(unicos)
        cands = unicos

    # --- marcar el mejor de cada escena y el top 10 ---
    vistas = set()
    for pos, c in enumerate(cands):
        c["top"] = pos < 10
        c["mejor_escena"] = c["escena"] not in vistas
        vistas.add(c["escena"])

    # --- mover a la carpeta final con nombres legibles ---
    os.makedirs(carpeta, exist_ok=True)
    resultado = []
    for pos, c in enumerate(cands, 1):
        nombre = f"{base}_{_nombre_tiempo(c['t'])}_f{c['frame']}.jpg"
        destino = os.path.join(carpeta, nombre)
        shutil.move(c["archivo_tmp"], destino)
        resultado.append({
            "archivo": nombre, "t": round(c["t"], 3), "frame": c["frame"],
            "puntuacion": c["puntuacion"], "puesto": pos, "caras": c["caras"],
            "escena": c["escena"] + 1, "mejor_escena": c["mejor_escena"], "top": c["top"],
            "ancho": c["ancho"], "alto": c["alto"],
        })
    shutil.rmtree(tmp, ignore_errors=True)

    # --- ZIP con todos ---
    ruta_zip = carpeta + ".zip"
    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_STORED) as z:
        for r in sorted(resultado, key=lambda r: r["t"]):
            z.write(os.path.join(carpeta, r["archivo"]), r["archivo"])

    return resultado, {"fps": fps, "descartados": descartados}
