# MusicFit — pon la canción justa debajo de cada video

MusicFit analiza cada video y cada canción y decide qué canción y qué tramo de ella encaja mejor con cada video. Después exporta el video con la música debajo.

## Instalación (una sola vez)

1. **Python 3.9 o superior**: https://www.python.org/downloads/ (en Windows, marca "Add Python to PATH").
2. **ffmpeg**:
   - Windows: `winget install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`
3. **Librerías** (desde esta carpeta):
   ```
   pip install -r requirements.txt
   ```

## Uso

1. Copia tus videos en la carpeta `videos/`.
2. Copia tus canciones en la carpeta `canciones/`.
3. Ejecuta el programa:
   ```
   python musicfit.py
   ```
   En Windows también puedes hacer doble clic en `ejecutar.bat`.
4. Los videos terminados aparecen en `resultados/`, junto con:
   - `ranking.csv`: todas las combinaciones video × canción con su puntuación (se abre en Excel).
   - `informe.json`: el detalle técnico de cada elección.

## Música de fondo (segundo plano)

Si quieres que lo importante sea el audio original (voces, entrevistas, ambiente) y la canción quede solo de fondo:

```
python musicfit.py --musica-fondo
```

En Windows también puedes hacer doble clic en `ejecutar_fondo.bat`.

Este modo hace dos cosas:

1. **Nivela la música automáticamente.** Mide el volumen del audio original de cada video y coloca la canción **14 dB por debajo**. Así queda bien en cualquier video, suene fuerte o suave.
2. **Ducking.** Cuando alguien habla o hay sonido en el video, la música **baja sola**, y en los silencios vuelve a subir un poco.

Ajustes:

```
python musicfit.py --musica-fondo --fondo-db 20    # música aún más bajita
python musicfit.py --musica-fondo --fondo-db 8     # música un poco más presente
python musicfit.py --musica-fondo --sin-ducking    # nivel fijo, sin bajar con la voz
```

Si un video casi no tiene sonido propio, la música se pone a volumen normal, porque no hay nada que tapar.

## Thumbnails

Además de la música, MusicFit saca **todos los thumbnails posibles** de cada video y al terminar abre una **galería en tu navegador**:

- **Todos los fotogramas candidatos**, ordenados por calidad. Se tiene en cuenta la nitidez, el contraste, el color, la exposición y si aparecen caras. Los negros, borrosos y casi repetidos se descartan solos.
- **Filtros**: todos, los 10 mejores, el mejor de cada escena o solo los que tienen caras. También puedes ordenarlos por tiempo.
- **Descargar** cada thumbnail con un clic (JPG a la resolución original) o **todos juntos en un .zip**.
- **Reproductor** con botones para avanzar o retroceder **fotograma a fotograma** y el botón **📸 Capturar este fotograma**, que descarga en PNG exactamente el fotograma que estás viendo. Así puedes sacar cualquier fotograma del video, no solo los sugeridos.
- Al hacer clic en un thumbnail lo ves en grande, y con "Ver" el video salta a ese momento.

Atajos en la galería: **← / →** para moverte un fotograma, **C** para capturar y **Esc** para cerrar la vista grande.

Los JPG también quedan guardados en `resultados/thumbnails/<nombre del video>/`.

```
python musicfit.py --galeria                 # volver a abrir la galería en otro momento
python musicfit.py --solo-thumbnails         # solo thumbnails, sin canciones
python musicfit.py --thumbs-intervalo 0      # revisar TODOS los fotogramas (más lento)
python musicfit.py --thumbs-intervalo 2      # un candidato cada 2 s (más rápido)
python musicfit.py --thumbs-sin-filtro       # no descartar borrosos, negros ni repetidos
python musicfit.py --sin-thumbnails          # solo música
python musicfit.py --no-abrir                # no abrir la galería al terminar
```

En Windows puedes abrir la galería con doble clic en `ver_galeria.bat`. Mientras la usas, deja abierta la ventana negra del programa; es lo que permite reproducir el video y capturar fotogramas.

## Qué analiza

| | Qué mide |
|---|---|
| **Video** | Cortes de escena, cuánto movimiento hay en cada momento y la duración. |
| **Canción** | Tempo (BPM), beats, compases, energía y secciones (intro, estrofa, coro…). |

Después prueba **cada beat de cada canción** como posible punto de inicio y puntúa el encaje de 0 a 100 según cinco criterios:

- **Ritmo (35%)**: que los cortes del video caigan sobre los beats.
- **Energía (25%)**: que la música suba cuando el video se mueve más y baje cuando se calma.
- **Inicio (15%)**: que la canción arranque al comienzo de una sección o de un compás.
- **Final (15%)**: que termine en un punto natural, como un cambio de sección o el final de la canción.
- **Intensidad (10%)**: que el nivel del tramo vaya con el video (más energía si es un video movido).

## Opciones útiles

```
python musicfit.py --estilo energetico      # prefiere los tramos fuertes (coros, drops)
python musicfit.py --estilo tranquilo       # prefiere los tramos suaves
python musicfit.py --no-repetir             # no usa la misma canción en dos videos
python musicfit.py --solo-musica            # quita el audio original del video
python musicfit.py --vol-musica 0.4         # música más baja (por defecto 0.6)
python musicfit.py --vol-original 0.8       # baja un poco el audio original
python musicfit.py --solo-analizar          # solo el ranking, sin exportar videos
python musicfit.py --top 5                  # muestra 5 opciones por video
python musicfit.py --videos clip.mp4 --canciones tema.mp3   # archivos concretos
```

## Notas

- Si una canción es más corta que el video, se repite y se le baja la puntuación.
- Funciona mejor con canciones que tengan un pulso claro (pop, urbano, electrónica). Con música muy libre, como piano lento o ambient, el criterio de ritmo pesa menos.
- El video original no se recodifica, así que no pierde calidad.
