# Análisis v3. Ancla el audio real al MIDI cargado por el primer sonido tras el silencio
# y lo valida con un promedio de la envolvente alineada a todos los note-on.
# Mide por cada cambio de nota resaltada su distancia al sonido de esa nota.
import json, sys
import numpy as np
from midi import note_ons

d = json.load(open(sys.argv[1]))
sr = d['sr']; H = 16; hop = H / sr
env = np.concatenate([b['env'] for b in d['audio']]).astype(float)
t0 = d['audio'][0]['start'] / sr
t = t0 + np.arange(len(env)) * hop

# Reloj del Player en el hilo principal: ct - posición = instante de arranque supuesto.
total = sum(e['duration'] for e in d['converterTimemap'])
starts = np.array([m['ct'] - (m['s'] + m['o']) / 1000 for m in d['moves'] if m['d'] and m['s'] + m['o'] < total - 50])
abs_start = float(np.median(starts[:20]))

ons = note_ons(d['midi'])
uniq = []
for ms, ch, nt in ons:
    if not uniq or ms - uniq[-1] > 5: uniq.append(ms)
uniq = np.array(uniq)

# 1) Ancla por primer sonido (la salida es cero exacto antes de la primera nota).
i_first = int(np.argmax((env > 1e-4) & (t > abs_start - 0.1)))
a_first = t[i_first] - uniq[0] / 1000

# 2) Validación: envolvente promedio alineada con todos los note-on previstos; el ataque
#    debería empezar en desfase 0. Se busca el máximo de la derivada media.
lags = np.arange(int(-0.08 / hop), int(0.08 / hop))
pred_idx = np.round((a_first + uniq / 1000 - t0) / hop).astype(int)
ok = (pred_idx + lags[0] > 0) & (pred_idx + lags[-1] + 1 < len(env))
eta = np.array([env[pred_idx[ok] + L].mean() for L in lags])
deriv = np.diff(eta)
lag_peak_ms = float(lags[int(np.argmax(deriv))] * hop * 1000)
# Contraste: lo mismo con desfases falsos de ±25 ms para ver que el pico se mueve.

rows = []; skipped = 0
R = d['rendererEvents']; M = d['measures']
for c in d['changes']:
    e = c['ev']; loc = c['loc']
    intended = loc['start'] + (R[e]['tstamp'] - M[loc['index']]['timestamp'])
    j = int(np.argmin(np.abs(uniq - intended)))
    if abs(uniq[j] - intended) > 60:
        skipped += 1; continue
    audio_ct = a_first + uniq[j] / 1000
    rows.append(dict(ev=e, intended=round(intended, 1), midi_ms=round(float(uniq[j]), 1),
                     A=c['seq'] - intended, B=float(uniq[j]) - intended,
                     C=(c['ct'] - audio_ct) * 1000,
                     F=(c['nextRaf'] - c['p']) if c['nextRaf'] else np.nan))

def st(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    if not len(x): return None
    q1, md, q3 = np.percentile(x, [25, 50, 75])
    return dict(n=int(len(x)), mediana=round(md, 1), p25=round(q1, 1), p75=round(q3, 1),
                riq=round(q3 - q1, 1), min=round(x.min(), 1), max=round(x.max(), 1))

olat = float(np.median(d['outputLatency'])) * 1000
C = np.array([r['C'] for r in rows]); F = np.array([r['F'] for r in rows])
out = {
    'archivo': sys.argv[1], 'conversor': d['version']['converter'], 'renderer': d['version']['renderer'],
    'horizontal': d['horizontal'], 'sr': sr, 'baseLatency_ms': d['baseLatency'] * 1000, 'outputLatency_ms': olat,
    'primer_noteon_midi_ms': float(uniq[0]),
    'arranque_audio_menos_reloj_player_ms': round((a_first - abs_start) * 1000, 1),
    'deriva_reloj_player_ms': round(float((starts.max() - starts.min()) * 1000), 1),
    'validacion_pico_ataque_promedio_ms': round(lag_peak_ms, 1), 'validacion_noteon_usados': int(ok.sum()),
    'cambios_visuales': len(d['changes']), 'cambios_sin_noteon_cercano': skipped,
    'A_posicion_player_menos_evento_ms': st([r['A'] for r in rows]),
    'B_noteon_midi_menos_evento_ms': st([r['B'] for r in rows]),
    'C_cambio_DOM_menos_audio_renderizado_ms': st(C),
    'F_cambio_DOM_a_frame_siguiente_ms': st(F),
    'D_frame_siguiente_menos_audio_oido_ms': st(C + F - olat),
    'frames_ms': st(np.diff([f['raf'] for f in d['frames']])),
}
print(json.dumps(out, ensure_ascii=False))
json.dump(dict(out=out, rows=rows), open(sys.argv[1].replace('.json', '.res.json'), 'w'), ensure_ascii=False, indent=1)
