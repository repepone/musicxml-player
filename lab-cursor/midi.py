# Lector mínimo de SMF: devuelve note-on (tiempo en ms, canal, nota) con mapa de tempo.
def read_vlq(b, i):
    v = 0
    while True:
        c = b[i]; i += 1
        v = (v << 7) | (c & 0x7F)
        if not c & 0x80: return v, i

def note_ons(data):
    b = bytes(data)
    assert b[:4] == b'MThd'
    ntrk = int.from_bytes(b[10:12], 'big'); div = int.from_bytes(b[12:14], 'big')
    i = 8 + int.from_bytes(b[4:8], 'big')
    events, tempos = [], []
    for _ in range(ntrk):
        ln = int.from_bytes(b[i + 4:i + 8], 'big'); j = i + 8; end = j + ln; i = end
        tick = 0; rs = None
        while j < end:
            dt, j = read_vlq(b, j); tick += dt
            st = b[j]
            if st == 0xFF:
                typ = b[j + 1]; ml, k = read_vlq(b, j + 2)
                if typ == 0x51: tempos.append((tick, int.from_bytes(b[k:k + 3], 'big')))
                j = k + ml; continue
            if st in (0xF0, 0xF7):
                ml, k = read_vlq(b, j + 1); j = k + ml; continue
            if st & 0x80: rs = st; j += 1
            hi = rs & 0xF0
            n = 1 if hi in (0xC0, 0xD0) else 2
            d = b[j:j + n]; j += n
            if hi == 0x90 and d[1] > 0: events.append((tick, rs & 0x0F, d[0]))
    tempos.sort()
    if not tempos or tempos[0][0] > 0: tempos.insert(0, (0, 500000))
    def ms(t):
        acc = 0.0; prev_t, prev_us = 0, tempos[0][1]
        for tt, us in tempos[1:]:
            if tt >= t: break
            acc += (tt - prev_t) * prev_us / div / 1000; prev_t, prev_us = tt, us
        return acc + (t - prev_t) * prev_us / div / 1000
    return sorted((ms(t), ch, nt) for t, ch, nt in events)
