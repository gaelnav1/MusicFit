#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selector grafico de inputs para MusicFit.

Abre dialogos nativos de Windows para elegir exactamente los videos y canciones
que participaran en una corrida. Luego llama a musicfit.py con esas rutas.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--musica-fondo", action="store_true")
    args, extra = ap.parse_known_args()

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as exc:
        print(f"[ERROR] No pude abrir el selector grafico: {exc}")
        return 1

    root = tk.Tk()
    root.withdraw()
    root.update()

    video_types = [
        ("Videos", "*.mp4 *.mov *.mkv *.avi *.m4v *.webm *.wmv *.mts"),
        ("Todos los archivos", "*.*"),
    ]
    audio_types = [
        ("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma"),
        ("Todos los archivos", "*.*"),
    ]

    videos = filedialog.askopenfilenames(
        title="MusicFit — selecciona uno o varios VIDEOS",
        filetypes=video_types,
    )
    if not videos:
        root.destroy()
        return 0

    canciones = filedialog.askopenfilenames(
        title="MusicFit — selecciona una o varias CANCIONES",
        filetypes=audio_types,
    )
    if not canciones:
        messagebox.showinfo("MusicFit", "No seleccionaste canciones. Operacion cancelada.")
        root.destroy()
        return 0

    modo = "musica de fondo" if args.musica_fondo else "musica principal"
    resumen = (
        f"Videos seleccionados: {len(videos)}\n"
        f"Canciones seleccionadas: {len(canciones)}\n"
        f"Modo: {modo}\n\n"
        "MusicFit probara las canciones seleccionadas contra los videos seleccionados.\n\n"
        "¿Continuar?"
    )
    if not messagebox.askyesno("MusicFit — confirmar lote", resumen):
        root.destroy()
        return 0

    root.destroy()

    script = Path(__file__).resolve().with_name("musicfit.py")
    cmd = [sys.executable, str(script), "--videos", *videos, "--canciones", *canciones]
    if args.musica_fondo:
        cmd.append("--musica-fondo")
    cmd.extend(extra)

    print("\nMusicFit — lote seleccionado")
    print(f"  Videos: {len(videos)}")
    print(f"  Canciones: {len(canciones)}")
    print(f"  Modo: {modo}\n")

    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
