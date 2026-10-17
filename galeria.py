# -*- coding: utf-8 -*-
"""
Galería de thumbnails: genera galeria.html y la sirve en el navegador con un
pequeño servidor local (necesario para reproducir el video, saltar a cualquier
fotograma y capturarlo en PNG).
"""

import json
import mimetypes
import os
import socket
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATOS = "galeria_datos.json"


# --------------------------------------------------------------------------- #
# Datos
# --------------------------------------------------------------------------- #

def cargar_datos(salida):
    ruta = os.path.join(salida, DATOS)
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"videos": []}


def guardar_galeria(salida, nuevos):
    """Mezcla los videos nuevos con los de ejecuciones anteriores y escribe la galería."""
    datos = cargar_datos(salida)
    por_nombre = {v["nombre"]: v for v in datos["videos"]}
    for v in nuevos:
        por_nombre[v["nombre"]] = v
    # quitar los que ya no existen en disco
    videos = [v for v in por_nombre.values() if os.path.exists(v["ruta_fuente"])]
    videos.sort(key=lambda v: v["nombre"].lower())
    for i, v in enumerate(videos):
        v["id"] = i
    datos = {"videos": videos}
    with open(os.path.join(salida, DATOS), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)

    publicos = []
    for v in videos:
        p = {k: val for k, val in v.items() if k != "ruta_fuente"}
        publicos.append(p)
    html = PLANTILLA.replace("__DATOS__", json.dumps(publicos, ensure_ascii=False).replace("</", "<\\/"))
    with open(os.path.join(salida, "galeria.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return os.path.join(salida, "galeria.html")


# --------------------------------------------------------------------------- #
# Servidor local con soporte de Range (para poder adelantar el video)
# --------------------------------------------------------------------------- #

def _handler(raiz, fuentes):
    raiz = os.path.realpath(raiz)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _ruta(self):
            camino = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
            if camino in ("", "/"):
                camino = "/galeria.html"
            if camino.startswith("/fuente/"):
                try:
                    return fuentes[int(camino.split("/")[2])]
                except (ValueError, KeyError, IndexError):
                    return None
            real = os.path.realpath(os.path.join(raiz, camino.lstrip("/")))
            if not real.startswith(raiz + os.sep) and real != raiz:
                return None
            return real if os.path.isfile(real) else None

        def _enviar(self, cuerpo=True):
            ruta = self._ruta()
            if not ruta:
                self.send_error(404)
                return
            tam = os.path.getsize(ruta)
            tipo = mimetypes.guess_type(ruta)[0] or "application/octet-stream"
            ini, fin = 0, tam - 1
            rango = self.headers.get("Range")
            if rango and rango.startswith("bytes="):
                a, _, b = rango[6:].split(",")[0].partition("-")
                try:
                    if a:
                        ini = int(a)
                        fin = int(b) if b else tam - 1
                    else:
                        ini = max(0, tam - int(b))
                except ValueError:
                    ini, fin = 0, tam - 1
                fin = min(fin, tam - 1)
                if ini > fin:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{tam}")
                    self.end_headers()
                    return
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(fin - ini + 1))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if not cuerpo:
                return
            try:
                with open(ruta, "rb") as f:
                    f.seek(ini)
                    resta = fin - ini + 1
                    while resta > 0:
                        bloque = f.read(min(1 << 20, resta))
                        if not bloque:
                            break
                        self.wfile.write(bloque)
                        resta -= len(bloque)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            self._enviar(True)

        def do_HEAD(self):
            self._enviar(False)

    return H


def _puerto_libre(preferido):
    for p in range(preferido, preferido + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return 0


def servir(salida, puerto=8765, abrir=True):
    datos = cargar_datos(salida)
    if not datos["videos"]:
        print("Todavía no hay thumbnails. Ejecuta primero:  python musicfit.py")
        return
    fuentes = {v["id"]: v["ruta_fuente"] for v in datos["videos"]}
    puerto = _puerto_libre(puerto)
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), _handler(salida, fuentes))
    url = f"http://localhost:{puerto}/galeria.html"
    print(f"\n🖼  Galería abierta en {url}")
    print("   (deja esta ventana abierta mientras la usas; Ctrl+C para cerrar)\n")
    if abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Galería cerrada.")
    finally:
        srv.server_close()


# --------------------------------------------------------------------------- #
# Página
# --------------------------------------------------------------------------- #

PLANTILLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MusicFit · Thumbnails</title>
<style>
:root{
  --bg:#f6f5f2; --panel:#ffffff; --ink:#1c1b19; --mute:#6d6a63; --line:#e3e0d9;
  --acc:#e2572b; --acc-ink:#fff; --ok:#2f8a57; --chip:#efece6; --shadow:0 1px 2px rgba(0,0,0,.06),0 4px 14px rgba(0,0,0,.05);
}
@media (prefers-color-scheme: dark){
  :root{ --bg:#141412; --panel:#1d1c1a; --ink:#f1efe9; --mute:#9d998f; --line:#2f2d29;
    --chip:#2a2825; --shadow:0 1px 2px rgba(0,0,0,.4); }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{display:flex;align-items:center;gap:16px;padding:14px 20px;border-bottom:1px solid var(--line);background:var(--panel);position:sticky;top:0;z-index:5}
header h1{font-size:16px;margin:0;letter-spacing:.2px}
header h1 b{color:var(--acc)}
#tabs{display:flex;gap:6px;overflow-x:auto;flex:1}
.tab{border:1px solid var(--line);background:var(--chip);color:var(--ink);padding:6px 12px;border-radius:999px;cursor:pointer;white-space:nowrap;font:inherit}
.tab.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
main{display:grid;grid-template-columns:minmax(320px,44%) 1fr;gap:20px;padding:20px;max-width:1700px;margin:0 auto}
@media (max-width:900px){main{grid-template-columns:1fr;padding:12px}}
.player{position:sticky;top:76px;align-self:start;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px;box-shadow:var(--shadow)}
@media (max-width:900px){.player{position:static}}
video{width:100%;max-height:62vh;background:#000;border-radius:8px;display:block}
.ctrl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}
button,.btn{font:inherit;border:1px solid var(--line);background:var(--chip);color:var(--ink);padding:7px 12px;border-radius:8px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px}
button:hover,.btn:hover{border-color:var(--mute)}
.prim{background:var(--acc);color:var(--acc-ink);border-color:var(--acc)}
.prim:hover{filter:brightness(1.05);border-color:var(--acc)}
.tc{font-variant-numeric:tabular-nums;color:var(--mute);margin-left:auto}
.meta{color:var(--mute);font-size:13px;margin-top:8px}
.switch{display:flex;gap:4px;margin-top:10px}
.switch button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.capturas{display:flex;gap:8px;overflow-x:auto;margin-top:10px}
.capturas img{height:56px;border-radius:6px;border:1px solid var(--line)}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:14px}
.bar select{font:inherit;padding:7px 10px;border-radius:8px;border:1px solid var(--line);background:var(--panel);color:var(--ink)}
.count{color:var(--mute)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:var(--shadow);display:flex;flex-direction:column}
.card .im{position:relative;cursor:zoom-in;background:#000;aspect-ratio:16/9}
.card img{width:100%;height:100%;object-fit:contain;display:block}
.badge{position:absolute;top:6px;left:6px;background:rgba(0,0,0,.65);color:#fff;font-size:12px;padding:2px 7px;border-radius:999px;font-variant-numeric:tabular-nums}
.star{position:absolute;top:6px;right:6px;background:var(--acc);color:#fff;font-size:11px;padding:2px 7px;border-radius:999px}
.card .info{display:flex;align-items:center;gap:6px;padding:8px 10px;font-size:12.5px}
.score{font-weight:600}
.score i{display:inline-block;width:42px;height:5px;background:var(--chip);border-radius:3px;margin-left:6px;vertical-align:middle;overflow:hidden;position:relative}
.score i b{position:absolute;inset:0 auto 0 0;background:var(--ok)}
.card .acts{display:flex;gap:6px;padding:0 10px 10px}
.card .acts>*{flex:1;justify-content:center;font-size:12.5px;padding:6px 8px}
.tags{color:var(--mute);margin-left:auto}
#lb{position:fixed;inset:0;background:rgba(10,10,10,.92);display:none;align-items:center;justify-content:center;z-index:20;flex-direction:column;gap:12px;padding:16px}
#lb.on{display:flex}
#lb img{max-width:96vw;max-height:80vh;border-radius:6px}
#lb .ctrl{margin:0}
#lb .tc{color:#bbb}
.empty{padding:40px;text-align:center;color:var(--mute)}
.aviso{background:#fff4d6;color:#5c4400;border:1px solid #f0d78a;padding:8px 12px;border-radius:8px;margin-top:10px;font-size:13px;display:none}
</style>
</head>
<body>
<header><h1>Music<b>Fit</b> · Thumbnails</h1><nav id="tabs"></nav></header>
<main>
  <section class="player">
    <video id="vid" controls preload="auto" playsinline></video>
    <div class="switch" id="sw"></div>
    <div class="ctrl">
      <button id="atras" title="Fotograma anterior (←)">◀ 1 fotograma</button>
      <button id="adelante" title="Fotograma siguiente (→)">1 fotograma ▶</button>
      <button id="capturar" class="prim" title="Descargar este fotograma en PNG (C)">📸 Capturar este fotograma</button>
      <span class="tc" id="tc">0:00.00</span>
    </div>
    <div class="aviso" id="aviso">Para capturar fotogramas abre la galería desde el programa (python musicfit.py --galeria), no con doble clic en el archivo.</div>
    <div class="meta" id="meta"></div>
    <div class="capturas" id="capturas"></div>
  </section>
  <section>
    <div class="bar">
      <select id="filtro">
        <option value="todos">Todos</option>
        <option value="top">Los 10 mejores</option>
        <option value="escena">El mejor de cada escena</option>
        <option value="caras">Con caras</option>
      </select>
      <select id="orden">
        <option value="calidad">Ordenar por calidad</option>
        <option value="tiempo">Ordenar por tiempo</option>
      </select>
      <span class="count" id="count"></span>
      <a class="btn prim" id="zip" download style="margin-left:auto">⬇ Descargar todos (.zip)</a>
    </div>
    <div class="grid" id="grid"></div>
  </section>
</main>
<div id="lb">
  <img id="lbimg" alt="">
  <div class="ctrl">
    <button id="lbprev">◀</button>
    <span class="tc" id="lbinfo"></span>
    <button id="lbnext">▶</button>
    <a class="btn prim" id="lbdl" download>⬇ Descargar</a>
    <button id="lbver">Ver en el video</button>
    <button id="lbcerrar">Cerrar ✕</button>
  </div>
</div>
<script>
const VIDEOS = __DATOS__;
const $ = s => document.querySelector(s);
const enc = s => s.split('/').map(encodeURIComponent).join('/');
let cur = null, lista = [], lbi = 0, modo = 'original';

function fmt(t){ t=Math.max(0,t); const m=Math.floor(t/60); return m+':'+(t-60*m).toFixed(2).padStart(5,'0'); }

function tabs(){
  const nav = $('#tabs'); nav.innerHTML='';
  VIDEOS.forEach(v=>{
    const b=document.createElement('button'); b.className='tab'; b.textContent=v.nombre;
    b.onclick=()=>abrir(v.id); b.dataset.id=v.id; nav.appendChild(b);
  });
}

function abrir(id){
  cur = VIDEOS.find(v=>v.id===id);
  document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on', +b.dataset.id===id));
  try{ localStorage.setItem('mf_video', id); }catch(e){}
  modo='original';
  const sw=$('#sw'); sw.innerHTML='';
  if(cur.resultado){
    [['original','Video original'],['musica','Con música']].forEach(([k,txt])=>{
      const b=document.createElement('button'); b.textContent=txt; b.className=k===modo?'on':'';
      b.onclick=()=>{ const t=$('#vid').currentTime; modo=k; fuente(t); sw.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b)); };
      sw.appendChild(b);
    });
  }
  fuente(0);
  $('#meta').textContent = `${cur.ancho}×${cur.alto} · ${cur.fps.toFixed(2)} fps · ${fmt(cur.duracion)} · ${cur.thumbs.length} thumbnails`
    + (cur.descartados? ` (${cur.descartados} descartados por borrosos, negros o repetidos)`:'')
    + (cur.cancion? ` · música: ${cur.cancion}`:'');
  $('#zip').href = enc(cur.zip); $('#zip').setAttribute('download', cur.zip.split('/').pop());
  $('#capturas').innerHTML='';
  pintar();
}

function fuente(t){
  const v=$('#vid');
  v.src = modo==='musica' && cur.resultado ? enc(cur.resultado) : 'fuente/'+cur.id;
  v.addEventListener('loadedmetadata', ()=>{ v.currentTime=t||0; }, {once:true});
}

function pintar(){
  const f=$('#filtro').value, o=$('#orden').value;
  lista = cur.thumbs.filter(t=> f==='todos' || (f==='top'&&t.top) || (f==='escena'&&t.mejor_escena) || (f==='caras'&&t.caras>0));
  lista.sort((a,b)=> o==='tiempo' ? a.t-b.t : b.puntuacion-a.puntuacion);
  $('#count').textContent = lista.length+' de '+cur.thumbs.length;
  const g=$('#grid'); g.innerHTML='';
  if(!lista.length){ g.innerHTML='<div class="empty">No hay thumbnails con este filtro.</div>'; return; }
  const frag=document.createDocumentFragment();
  lista.forEach((t,i)=>{
    const src = enc(cur.carpeta+'/'+t.archivo);
    const c=document.createElement('div'); c.className='card';
    c.innerHTML = `<div class="im"><img loading="lazy" src="${src}" alt=""><span class="badge">${fmt(t.t)}</span>${t.top?'<span class="star">★ top '+t.puesto+'</span>':''}</div>
      <div class="info"><span class="score">${Math.round(t.puntuacion)}<i><b style="width:${t.puntuacion}%"></b></i></span>
      <span class="tags">esc. ${t.escena}${t.caras?' · 🙂 '+t.caras:''}</span></div>
      <div class="acts"><button>▶ Ver</button><a class="btn" href="${src}" download="${t.archivo}">⬇ Descargar</a></div>`;
    c.querySelector('.im').onclick=()=>lb(i);
    c.querySelector('button').onclick=()=>ir(t.t);
    frag.appendChild(c);
  });
  g.appendChild(frag);
}

function ir(t){ const v=$('#vid'); v.pause(); v.currentTime=t+0.001; window.scrollTo({top:0,behavior:'smooth'}); }

function lb(i){
  lbi=(i+lista.length)%lista.length; const t=lista[lbi]; const src=enc(cur.carpeta+'/'+t.archivo);
  $('#lbimg').src=src; $('#lbdl').href=src; $('#lbdl').setAttribute('download',t.archivo);
  $('#lbinfo').textContent = `${lbi+1}/${lista.length} · ${fmt(t.t)} · calidad ${Math.round(t.puntuacion)} · ${t.ancho}×${t.alto}`;
  $('#lb').classList.add('on');
}
$('#lbprev').onclick=()=>lb(lbi-1); $('#lbnext').onclick=()=>lb(lbi+1);
$('#lbcerrar').onclick=()=>$('#lb').classList.remove('on');
$('#lbver').onclick=()=>{ $('#lb').classList.remove('on'); ir(lista[lbi].t); };
$('#lb').onclick=e=>{ if(e.target.id==='lb') $('#lb').classList.remove('on'); };

function paso(n){ const v=$('#vid'); v.pause(); v.currentTime=Math.min(v.duration||1e9, Math.max(0, v.currentTime + n/(cur.fps||30))); }
$('#atras').onclick=()=>paso(-1); $('#adelante').onclick=()=>paso(1);
$('#vid').addEventListener('timeupdate',()=>{ $('#tc').textContent = fmt($('#vid').currentTime)+' · fotograma '+Math.round($('#vid').currentTime*cur.fps); });
$('#vid').addEventListener('seeked',()=>{ $('#tc').textContent = fmt($('#vid').currentTime)+' · fotograma '+Math.round($('#vid').currentTime*cur.fps); });

$('#capturar').onclick=()=>{
  const v=$('#vid'); if(!v.videoWidth) return;
  const c=document.createElement('canvas'); c.width=v.videoWidth; c.height=v.videoHeight;
  c.getContext('2d').drawImage(v,0,0,c.width,c.height);
  try{
    c.toBlob(b=>{
      const url=URL.createObjectURL(b), a=document.createElement('a');
      const t=v.currentTime, m=Math.floor(t/60);
      a.href=url; a.download=`${cur.base}_${m}m${(t-60*m).toFixed(2).padStart(5,'0')}s_captura.png`; a.click();
      const im=new Image(); im.src=url; im.title=fmt(t); $('#capturas').prepend(im);
    },'image/png');
  }catch(e){ $('#aviso').style.display='block'; }
};

document.addEventListener('keydown',e=>{
  if(e.target.tagName==='SELECT') return;
  if($('#lb').classList.contains('on')){
    if(e.key==='ArrowLeft') lb(lbi-1); else if(e.key==='ArrowRight') lb(lbi+1); else if(e.key==='Escape') $('#lb').classList.remove('on');
    return;
  }
  if(e.key==='ArrowLeft'){ e.preventDefault(); paso(-1); }
  else if(e.key==='ArrowRight'){ e.preventDefault(); paso(1); }
  else if(e.key==='c'||e.key==='C'){ $('#capturar').click(); }
});
$('#filtro').onchange=pintar; $('#orden').onchange=pintar;
if(location.protocol==='file:') $('#aviso').style.display='block';

tabs();
if(VIDEOS.length){
  let id=VIDEOS[0].id; try{ const s=+localStorage.getItem('mf_video'); if(VIDEOS.some(v=>v.id===s)) id=s; }catch(e){}
  abrir(id);
} else { $('#grid').innerHTML='<div class="empty">No hay videos todavía.</div>'; }
</script>
</body>
</html>
"""
