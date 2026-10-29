// Arnés de medición: carga la demo del repo en Chromium headless, toca un ejemplo
// y registra (a) cada cambio de nota resaltada y (b) el audio real del sintetizador.
// Uso: node run.js <sheet> <segundos> <salida.json> [horizontal]
const { chromium } = require('playwright');
const fs = require('fs');

const [, , sheet, secs, out, mode] = process.argv;
const horizontal = mode === 'horizontal';

const STUB = `export class Playlist{constructor(){this.songs=[]}}
export const Converter={convert(){return ''}};
export const Version={name:'stub',version:'0'};`;

const TAP = `class Tap extends AudioWorkletProcessor{
  constructor(){super();this.buf=[];this.n=0;}
  process(inputs){
    const ch=inputs[0];
    if(ch&&ch.length){
      const len=ch[0].length; const H=16;
      for(let i=0;i<len;i+=H){let m=0;for(let c=0;c<ch.length;c++){const d=ch[c];for(let j=i;j<i+H&&j<len;j++){const v=d[j]<0?-d[j]:d[j];if(v>m)m=v;}}this.buf.push(m);}
    } else { for(let i=0;i<8;i++) this.buf.push(0); }
    if(this.n===0) this.start=currentFrame;
    this.n++;
    if(this.n>=64){this.port.postMessage({start:this.start,env:this.buf});this.buf=[];this.n=0;}
    return true;
  }
}
registerProcessor('tap',Tap);`;

(async () => {
  const browser = await chromium.launch({
    args: ['--autoplay-policy=no-user-gesture-required'],
  });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.route('https://cdn.jsdelivr.net/**', (r) =>
    r.fulfill({ status: 200, contentType: 'application/javascript', body: STUB }),
  );
  await page.route('https://buttons.github.io/**', (r) => r.abort());
  page.on('console', (m) => { if (m.type() === 'error') console.error('[page]', m.text()); });

  if (horizontal) {
    await page.addInitScript(() => {
      localStorage.setItem('musicxml-player', JSON.stringify({
        params: [], options: { unroll: false, horizontal: true, follow: true, mute: false },
      }));
    });
  }
  const upload = mode === 'upload';
  await page.goto(upload ? 'http://localhost:8765/' : `http://localhost:8765/?sheet=${encodeURIComponent(sheet)}`);
  await page.waitForFunction(() => window.g_state?.player && document.querySelector('.sheet-page svg'), null, { timeout: 120000 });
  if (upload) {
    // Ficheros de data/ que no están en el desplegable: se cargan por el input de subida de la demo.
    await page.evaluate(() => { window.__old = window.g_state.player; window.g_state.params.set('converter', 'vrv'); window.g_state.params.set('renderer', 'vrv'); });
    await page.setInputFiles('#upload', require('path').resolve('/home/user/musicxml-player/demo', sheet));
    await page.waitForFunction(() => window.g_state.player && window.g_state.player !== window.__old && document.querySelector('.sheet-page svg'), null, { timeout: 120000 });
  }
  await page.waitForTimeout(1500);

  await page.evaluate(async (TAP) => {
    const player = window.g_state.player;
    const ctx = player.context;
    const r = player._options.renderer;
    const L = (window.__lab = {
      sr: ctx.sampleRate, baseLatency: ctx.baseLatency, outputLatency: [],
      changes: [], frames: [], audio: [], ots: [], moves: [],
      rendererEvents: r._events.map((e) => ({ tstamp: e.tstamp, tempo: e.tempo, off: e.off ?? [], on: [...(e.on ?? []), ...(e.restsOn ?? [])], measureEntry: e.measureEntry })),
      measures: r._measures.map((m) => ({ timestamp: m.timestamp, eventEntry: m.eventEntry, systemId: m.systemId, measureId: m.measureId })),
      converterTimemap: player._options.converter.timemap,
      horizontal: player._options.horizontal,
    });
    const url = URL.createObjectURL(new Blob([TAP], { type: 'application/javascript' }));
    await ctx.audioWorklet.addModule(url);
    const tap = new AudioWorkletNode(ctx, 'tap');
    tap.port.onmessage = (e) => L.audio.push(e.data);
    const sink = ctx.createGain(); sink.gain.value = 0;
    tap.connect(sink); sink.connect(ctx.destination);
    player.connect(tap);

    // Llamadas al renderer: qué posición le pasa el Player en cada frame.
    const orig = r.moveTo.bind(r);
    r.moveTo = (i, s, o, d) => {
      const p = performance.now(); const ct = ctx.currentTime;
      const ret = orig(i, s, o, d);
      L.moves.push({ p, ct, i, s, o, d, cost: performance.now() - p });
      return ret;
    };
    // Coste del recálculo de geometría que dispara cada evento 'scroll' de la ventana.
    const origEv = r.onEvent.bind(r);
    L.onEvent = [];
    r.onEvent = (...a) => { const p = performance.now(); const ret = origEv(...a); L.onEvent.push({ p, cost: performance.now() - p }); return ret; };

    // Cambios de nota: el renderer pone fill naranja en las notas activas.
    const HL = 'rgb(234, 107, 36)';
    const mo = new MutationObserver((muts) => {
      const ids = [];
      for (const m of muts) {
        if (m.attributeName === 'fill' && m.target.getAttribute('fill') === HL && m.oldValue !== HL) ids.push(m.target.id);
      }
      if (!ids.length) return;
      const p = performance.now();
      const rec = {
        p, ct: ctx.currentTime, seq: player._sequencer.currentTime * 1000, pos: player.position,
        ev: r._currentEventEntry, ids, nextRaf: null,
        loc: { ...r._currentLocation },
      };
      L.changes.push(rec);
      requestAnimationFrame((t) => { rec.nextRaf = t; });
    });
    mo.observe(document.getElementById('sheet-container'), { subtree: true, attributes: true, attributeFilter: ['fill'], attributeOldValue: true });

    // Muestreo por frame: reloj de salida de audio, scroll y cursor.
    const sheet = document.querySelector('.player-sheet');
    const cursor = document.querySelector('.player-cursor');
    const tick = (t) => {
      const o = ctx.getOutputTimestamp();
      L.ots.push({ raf: t, p: performance.now(), ct: ctx.currentTime, oct: o.contextTime, op: o.performanceTime });
      L.outputLatency.push(ctx.outputLatency);
      const cr = cursor.getBoundingClientRect();
      const sr = sheet.getBoundingClientRect();
      L.frames.push({ raf: t, p: performance.now(), sy: window.scrollY, sl: sheet.scrollLeft, cx: cr.left, cy: cr.top, ch: cr.height, sw: sheet.clientWidth, sx: sr.left, vh: window.innerHeight, ev: r._currentEventEntry, pos: player.position });
      if (!L.stop) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, TAP);

  await page.click('#play');
  await page.waitForTimeout(Number(secs) * 1000);
  await page.click('#pause');
  await page.waitForTimeout(300);
  const data = await page.evaluate(() => {
    window.__lab.stop = true;
    // Ligaduras de prolongación según el MEI que Verovio tiene cargado (solo VerovioRenderer).
    let ties = [];
    const vrv = window.g_state.player._options.renderer._vrv;
    if (vrv) {
      const mei = new DOMParser().parseFromString(vrv.getMEI(), 'application/xml');
      ties = [...mei.getElementsByTagName('tie')].map((t) => ({ start: (t.getAttribute('startid') || '').replace('#', ''), end: (t.getAttribute('endid') || '').replace('#', '') }));
    }
    window.__lab.ties = ties;
    const L = window.__lab;
    // Geometría de sistemas y notas (en coordenadas de documento) para el análisis de scroll.
    const sys = {};
    document.querySelectorAll('g.system').forEach((g) => {
      const b = g.getBoundingClientRect();
      sys[g.id] = { top: b.top + window.scrollY, bottom: b.bottom + window.scrollY };
    });
    const pages = [...document.querySelectorAll('.sheet-page')].map((p) => { const b = p.getBoundingClientRect(); return { top: b.top + window.scrollY, h: b.height, w: b.width }; });
    const noteSys = {};
    L.rendererEvents.forEach((e) => e.on.forEach((id) => { const el = document.getElementById(id); const s = el?.closest('g.system'); noteSys[id] = s?.id; }));
    return { ...L, sys, pages, noteSys, docH: document.documentElement.scrollHeight, midi: Array.from(new Uint8Array(window.g_state.player.midi)), version: window.g_state.player.version, duration: window.g_state.player.duration, origMidi: Array.from(new Uint8Array(window.g_state.player._options.converter.midi)) };
  });
  fs.writeFileSync(out, JSON.stringify(data));
  console.log('ok', out, 'changes', data.changes.length, 'audio blocks', data.audio.length, 'frames', data.frames.length);
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
