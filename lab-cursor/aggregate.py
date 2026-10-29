# Agrega los resultados por ejecución (salida de analyze3.py) y da cifras conjuntas.
import json, sys, subprocess
import numpy as np
files = sys.argv[1:]
allrows, runs = [], []
for f in files:
    o = json.loads(subprocess.check_output(['python3', 'analyze3.py', f]))
    rows = json.load(open(f.replace('.json', '.res.json')))['rows']
    runs.append((f, o['conversor'].split('/')[-1], o['arranque_audio_menos_reloj_player_ms'], o['deriva_reloj_player_ms'], o['validacion_pico_ataque_promedio_ms'], len(rows), o['A_posicion_player_menos_evento_ms']['mediana'], o['C_cambio_DOM_menos_audio_renderizado_ms']['mediana'], o['D_frame_siguiente_menos_audio_oido_ms']['mediana'], o['outputLatency_ms']))
    olat = o['outputLatency_ms']
    for r in rows: r['D'] = r['C'] + r['F'] - olat; allrows.append(r)
def st(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    q1, md, q3 = np.percentile(x, [25, 50, 75]); p5, p95 = np.percentile(x, [5, 95])
    return dict(n=int(len(x)), mediana=round(md, 1), p25=round(q1, 1), p75=round(q3, 1), riq=round(q3 - q1, 1), p5=round(p5, 1), p95=round(p95, 1), min=round(x.min(), 1), max=round(x.max(), 1))
print('archivo | conversor | arranque_ms | deriva_ms | valid_ms | n | A_med | C_med | D_med | outLat')
for r in runs: print(' | '.join(str(x) for x in r))
for k in ('A', 'B', 'C', 'F', 'D'):
    print(k, st([r[k] for r in allrows]))
print('arranque por ejecución', st([r[2] for r in runs]))
