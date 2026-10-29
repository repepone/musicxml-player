# Desplazamiento durante la reproducción: cuándo se mueve la página respecto al cambio
# de sistema, cuánto tarda y cuánta música queda visible por delante del cursor.
import json, sys
import numpy as np

d = json.load(open(sys.argv[1]))
F = d['frames']; R = d['rendererEvents']; M = d['measures']; sys_ = d['sys']
note_sys = d['noteSys']
def ev_sys(e):
    for i in R[e]['on']:
        if note_sys.get(i): return note_sys[i]
    return M[R[e]['measureEntry']]['systemId']

def st(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if not len(x): return None
    q1, md, q3 = np.percentile(x, [25, 50, 75])
    return dict(n=int(len(x)), mediana=round(md, 1), p25=round(q1, 1), p75=round(q3, 1), min=round(x.min(), 1), max=round(x.max(), 1))

out = {'archivo': sys.argv[1], 'horizontal': d['horizontal']}
raf = np.array([f['raf'] for f in F])
if not d['horizontal']:
    sy = np.array([f['sy'] for f in F]); vh = F[0]['vh']
    # Cambios de sistema según la nota resaltada.
    ch = d['changes']; prev = None; sc = []
    for c in ch:
        s = ev_sys(c['ev'])
        if prev is not None and s != prev: sc.append((c, s))
        prev = s
    lat_ini, dur, delta, top_before, bottom_before = [], [], [], [], []
    for c, s in sc:
        k = int(np.searchsorted(raf, c['p']))
        y0 = sy[k - 1] if k > 0 else sy[0]
        mv = np.nonzero(np.abs(sy[k:] - y0) > 0.5)[0]
        top_before.append(sys_[s]['top'] - y0); bottom_before.append(sys_[s]['bottom'] - y0)
        if not len(mv): lat_ini.append(np.nan); dur.append(np.nan); delta.append(0); continue
        k1 = k + mv[0]
        # fin: primer frame tras el cual no cambia durante 5 frames
        k2 = k1
        while k2 + 5 < len(sy) and np.any(np.abs(np.diff(sy[k2:k2 + 6])) > 0.5): k2 += 1
        lat_ini.append(raf[k1] - c['p']); dur.append(raf[k2] - raf[k1]); delta.append(sy[k2] - y0)
    out.update(alto_ventana_px=vh, cambios_de_sistema=len(sc),
               scroll_desde_cambio_hasta_primer_movimiento_ms=st(lat_ini),
               scroll_duracion_ms=st(dur), scroll_px=st(delta),
               sistema_nuevo_top_en_ventana_antes_px=st(top_before),
               sistema_nuevo_bottom_en_ventana_antes_px=st(bottom_before))
    # Música visible por delante: final del último sistema completamente visible.
    sys_order = []
    for m in M:
        if m['systemId'] not in sys_order: sys_order.append(m['systemId'])
    sys_start = {}
    for m in M: sys_start.setdefault(m['systemId'], m['timestamp'])
    ahead_ms, ahead_sys = [], []
    for f in F:
        if f['ev'] is None or f['ev'] >= len(R) or f['pos'] <= 0: continue
        cur = ev_sys(f['ev']); i = sys_order.index(cur)
        last = i
        while last + 1 < len(sys_order) and sys_[sys_order[last + 1]]['bottom'] <= f['sy'] + f['vh']: last += 1
        end_t = sys_start[sys_order[last + 1]] if last + 1 < len(sys_order) else None
        cur_t = R[f['ev']]['tstamp']
        if end_t is not None: ahead_ms.append(end_t - cur_t)
        ahead_sys.append(last - i)
    out.update(sistemas_visibles_por_delante=st(ahead_sys), musica_visible_por_delante_ms=st(ahead_ms))
else:
    sl = np.array([f['sl'] for f in F]); pos = np.array([f['pos'] for f in F])
    cx = np.array([f['cx'] - f['sx'] for f in F]); sw = F[0]['sw']
    play = pos > 0
    v = np.diff(sl[play]) / np.maximum(1e-6, np.diff(pos[play]))  # px por ms de música
    v = v[np.isfinite(v) & (v > 0)]
    vmed = float(np.median(v)) if len(v) else np.nan
    ahead_px = sw - cx[play]
    out.update(ancho_visible_px=sw, cursor_x_en_ventana_px=st(cx[play]),
               px_por_ms_mediana=round(vmed, 4), scroll_por_frame_px=st(np.abs(np.diff(sl[play]))),
               visible_por_delante_px=st(ahead_px), visible_por_delante_ms_aprox=st(ahead_px / vmed))
print(json.dumps(out, ensure_ascii=False, indent=1))
