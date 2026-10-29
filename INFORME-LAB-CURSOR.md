# Informe LAB-CURSOR — cómo sigue el audio musicxml-player

Rama `lab-cursor` del fork `repepone/musicxml-player`, versión estudiada 1.5.1 (commit `0eb25c2`). Fecha: 2026-10-29.

## Resumen en llano

- La licencia es **GPL-3.0**. De aquí solo se toman **ideas**: no se copia código a un visor propio.
- El reproductor no conoce el audio de verdad. Genera un MIDI, lo toca con un sintetizador web y lee la hora de ese sintetizador unas 60 veces por segundo. Con esa hora busca en una tabla qué compás suena y, dentro del compás, qué nota resaltar.
- No admite una grabación humana. Lo más parecido es darle un MIDI y una tabla de **compases** en milisegundos. No acepta una tabla por nota.
- Medido en Chromium sin pantalla, con 1158 cambios de nota en 6 partituras de ejemplo: el resaltado llega una mediana de **10 ms** después del instante de la nota según su propio reloj. Respecto al sonido real que sale del sintetizador, llega una mediana de **6 ms** después.
- No compensa la latencia de salida del audio. En esta máquina, donde el navegador declara 32 ms, el resaltado se veía unos **10 ms antes** de que sonara la nota. Con altavoces Bluetooth la diferencia sería mucho mayor (no medido).
- Repeticiones, anacrusa y cambio de tempo salieron bien en las pruebas. En las ligaduras de prolongación, el resaltado salta a la segunda nota aunque esta no suena.
- En vertical no se adelanta: centra el sistema nuevo un fotograma después de que se ilumine su primera nota, con una animación de unos 200 ms. En horizontal deja el cursor fijo a unos 200-290 px del borde izquierdo y enseña unos 7 s de música por delante.

Las etiquetas significan:
- **«leído»**: sale de leer el código. Se cita fichero y línea del repo, o el fuente de una dependencia tal como viene en `build/musicxml-player.mjs.map`.
- **«medido»**: sale de las ejecuciones descritas en §2. Los scripts y las cifras brutas están en `lab-cursor/`.

---

## 0. Licencia

- `LICENSE` contiene el texto de la «GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007» **«leído»**.
- En `package.json`, `"license": "GPL-3.0-only"` **«leído»**.
- Consecuencia: este informe solo estudia ideas y comportamiento. No se propone copiar ni adaptar código suyo a un visor que no sea GPL. Las citas de fichero y línea sirven para localizar el comportamiento, no para trasladarlo.

---

## 1. Del tiempo de audio a la nota resaltada

### 1.1 De dónde sale la hora

1. **La hora es la del sintetizador, no la de un audio externo** **«leído»**.
   - `Player.position` vale `sequencer.currentTime * 1000`, limitado a `[0, duración − 1]` (`src/Player.ts:424-429`).
   - El secuenciador es `spessasynth_lib` (`src/Player.ts:8`, `:222`). Su `currentTime` es `(synth.currentTime − absoluteStartTime) × playbackRate`, y `synth.currentTime` es `AudioContext.currentTime`. Esto se lee en `spessasynth_lib/src/sequencer/sequencer.ts` y `.../basic_synthesizer.ts`, dentro de `build/musicxml-player.mjs.map`.
   - Es, por tanto, el reloj de **render** del contexto de audio, no el instante en que el sonido sale por el altavoz.
2. **Ese reloj vive en el hilo principal y se corrige poco** **«leído»**.
   - El reloj arranca en `play()` con la hora del hilo principal.
   - El worklet de audio manda un `sync` cada 1 s (`SEQUENCER_SYNC_INTERVAL = 1`, en `basic_synthesizer_core.ts`).
   - El hilo principal solo corrige si la diferencia supera 50 ms (`if (Math.abs(m.data - this.currentTime) > 0.05)`, en `spessasynth_lib/src/sequencer/sequencer.ts`).
3. **Dos tablas de tiempos distintas** **«leído»**:
   - **Tabla de compases del «conversor»** (`IMIDIConverter.timemap`). Es una lista de `{measure, timestamp, duration}` en ms, con las repeticiones ya desenrolladas (`src/interfaces/IMIDIConverter.ts:7-12`, comentario en `:19-22`). La generan:
     - `VerovioConverter`: usa `renderToTimemap({includeMeasures, includeRests})` y `renderToMIDI()` (`src/VerovioConverter.ts:50-55`).
     - `VerovioStaticConverter`: lee un JSON precalculado con la CLI de Verovio.
     - `FetchConverter`: lee un MIDI y un JSON de compases, o los calcula con la XSLT `timemap.sef.json` de musicxml-midi, que descarga de GitHub (`src/FetchConverter.ts:27-45`; URL por defecto en `src/Player.ts:116-117`).
     - `MmaConverter`: usa un servidor externo más esa XSLT.
     - `MuseScoreConverter`: lee el JSON de `mscore --score-media`.
   - **Tabla de notas del «renderer»**. `VerovioRenderer` pide a Verovio su propio timemap con `expandNever: true`, es decir, sin desenrollar repeticiones e incluyendo silencios (`src/VerovioRenderer.ts:121-130`). Cada entrada lleva `tstamp` (ms), `on`/`off` (ids de nota), `restsOn`/`restsOff` y `measureOn`.
   - El renderer **no** usa los tiempos del MIDI para las notas. Usa los de su propio timemap.
4. **Repeticiones** **«leído»**.
   - Al desenrollar, Verovio da a los compases repetidos ids con sufijo `-rendN`.
   - `_parseTimemap` los vuelve a llevar a su índice original con un mapa `id base → índice` (`src/VerovioConverterBase.ts:23-30`).
   - La duración del último compás sale del `tstamp` máximo (`:44`).
   - Así, la tabla de compases dice qué compás *visual* suena, aunque sea la segunda vuelta.
5. **Desplazamiento dentro del compás** **«leído»**.
   - El renderer calcula `tiempoNota = inicioCompás_renderer + (posición − inicioCompás_conversor)` (`src/VerovioRendererBase.ts:189`).
   - El desplazamiento se suma en **ms absolutos**. No se reescala a la duración real del compás.
   - En cambio, la línea del cursor sí avanza de forma proporcional, `offset / duration` (`:255-277`).
   - Si el compás real (por ejemplo, tocado por un humano) dura distinto que el de la partitura, notas y cursor se desacoplan dentro del compás (no medido).
6. **Anacrusa** **«leído» + «medido»**.
   - No hay tratamiento especial: el compás incompleto es el compás 0, que empieza en 0 ms.
   - Medido en `asa-branca`, que tiene `implicit="yes"`: la tabla de compases da al compás 0 una duración de 500 ms y los demás de 1000 ms. Los 258 cambios de nota medidos en esa pieza (3 ejecuciones) coinciden con su note-on del MIDI (columna B de §2, mediana 0,0 ms).
7. **Cambios de tempo** **«leído» + «medido»**.
   - No hay lógica propia: los `tstamp` ya vienen en ms con el tempo aplicado.
   - Medido en `blue-bag-folly`, con un cambio de 120 a 90 bpm a los 28 s: los 13 cambios posteriores al cambio de tempo coinciden con el MIDI (mediana 0,0 ms, extremos −0,33 y +0,34 ms).
   - **Fallo lateral, medido.** `_adjustMidiDuration` (`src/Player.ts:475-491`) añade un CC al final usando `midi.tempoChanges[0]`. En spessasynth esa lista va **invertida**: el elemento 0 es el *último* cambio de tempo (comentario «Tempo changes are reversed», en `basic_midi.ts`). En `blue-bag-folly` el CC cayó en **100000 ms**, cuando la tabla de compases suma 109333 ms. Aquí no tuvo efecto visible porque cayó antes del final.
8. **Ligaduras de prolongación** **«medido»**.
   - Prueba en `blue-bag-folly`, con 5 ligaduras según el MEI que Verovio tiene cargado.
   - En el timemap de Verovio, la nota ligada de destino aparece como un `on` propio en su instante escrito, y la de origen como `off` en ese mismo instante. Pasó en las 5.
   - En el MIDI no hay ningún note-on a ±30 ms de esos instantes (0 de 5).
   - En la reproducción, el resaltado **salta a la segunda nota de la ligadura** sin que haya ataque sonoro. Pasó en las 3 de 3 ligaduras alcanzadas en los 45 s grabados.
9. **Silencios**: se resaltan como las notas (`includeRests: true` y `restsOn`/`restsOff`, en `src/VerovioRendererBase.ts:105` y `:111`) **«leído»**.

### 1.2 Cómo busca la nota activa

1. Bucle con `requestAnimationFrame` mientras el estado es `Playing` (`src/Player.ts:304-348`). No hay temporizador propio ni anticipación **«leído»**.
2. En cada fotograma hay una **búsqueda binaria** sobre la tabla de compases por `timestamp` (`src/Player.ts:311-323`). Si no hay coincidencia exacta, se toma el último compás que empieza en o antes de `t` (`index ≥ 0 ? index : max(0, −index − 2)`, en `:326-329`). Luego se llama a `renderer.moveTo(compás, inicio, t − inicio, duración)` (`:331-336`) **«leído»**.
3. El renderer busca la nota de forma **lineal** desde el primer evento de ese compás, mientras `tstamp(siguiente) ≤ tiempoNota` (`src/VerovioRendererBase.ts:187-196`) **«leído»**.
4. **Notas sonando, no solo la última atacada** **«leído»**.
   - Al preparar los datos, cada evento hereda la lista de notas que siguen sonando del anterior, quita las de `off` y añade las de `on` (`src/VerovioRendererBase.ts:98-121`).
   - Así, una blanca sigue resaltada mientras otra voz cambia.
5. **Pintado por diferencias** **«leído»**.
   - Solo se toca el DOM si cambia el índice de evento (`:200`).
   - A las notas que se apagan se les devuelven el `fill`/`stroke` guardados.
   - A las que se encienden se les pone `fill` y `stroke` a `rgb(234, 107, 36)` (`:201-226`).
6. **Coste por fotograma** **«medido»**:
   - `moveTo` del renderer: mediana 0,0-0,1 ms, p95 ≤ 0,3 ms, máximo 5,2 ms (4 ejecuciones, n = 1802-8998 llamadas).
7. **Saltar al pulsar una nota** **«leído»**.
   - Cada nota y silencio lleva un `click` que llama a `Player.moveTo` (`src/VerovioRendererBase.ts:113-119`).
   - Con repeticiones, elige la aparición de ese compás más cercana a la posición actual (`src/Player.ts:283-291`).
   - Coloca el secuenciador 1 ms antes de la nota (`:293-294`).
8. **Otros renderers** **«leído»**, solo para comparar y sin medir:
   - OSMD convierte la fracción de compás a ms con el tempo del compás (`src/OpenSheetMusicDisplayRenderer.ts:179-182`) y recorre las entradas hacia atrás (`:97-117`).
   - MuseScore hace una búsqueda binaria sobre los segmentos de `--score-media` (`src/MuseScoreRenderer.ts:181-200`).

### 1.3 ¿Compensa la latencia?

1. **No** **«leído»**.
   - En `src/` no hay uso de `outputLatency`, `baseLatency` ni `getOutputTimestamp()`.
   - La posición sale de `AudioContext.currentTime` (punto 1.1.1), que va por delante de lo que se oye en lo que tarda la salida de audio.
   - En `demo/index.html:44` queda una regla CSS `#audio-offset` sin elemento que la use. Parece un resto, no una función.
2. El desfase entre el arranque del reloj en el hilo principal y el primer sonido real fue pequeño **«medido»**: mediana 3,3 ms, de −1,3 a 8,7 ms, en 17 ejecuciones (§2).

### 1.4 Formato que esperaría para una grabación humana

1. **No hay vía para audio externo** **«leído»**.
   - El audio siempre es MIDI tocado por spessasynth con una SoundFont (`src/Player.ts:174-184`, `:218-226`).
   - Para seguir una grabación habría que silenciar el sintetizador (`mute`) y conducir el reloj desde fuera. No hay API para eso: `position` solo lee el secuenciador.
2. **Lo más cercano es `FetchConverter(midi, timemap)`** **«leído»**.
   - Formato: JSON `[{ "measure": índice0, "timestamp": ms, "duration": ms }, …]`, **uno por compás tocado**, con las repeticiones desenrolladas.
   - Ejemplo real del repo: `demo/data/baiao-miranda.timemap.json`, cuya primera entrada es `{"measure":0,"timestamp":0,"duration":1224}`.
   - Siempre exige además un MIDI (`src/FetchConverter.ts:22-26`).
   - La granularidad es el **compás**. Dentro del compás manda el timemap de Verovio en ms absolutos (punto 1.1.5), así que el rubato interno no se reflejaría.
3. **Ids estables** **«leído»**.
   - El conversor de Verovio activa `xmlIdChecksum: true` (`src/VerovioConverter.ts`, constructor).
   - El modo estático documenta `verovio --xml-id-checksum` (`src/VerovioStaticRenderer.ts:12-16`).
   - Es lo que hace falta para que un mapa `id → ms` siga valiendo entre renders. No se ha medido si los ids se mantienen entre versiones de Verovio.

---

## 2. Medición en Chromium headless

### 2.1 Montaje **«medido»**

**Entorno:**
- Chromium 153.0.8010.12 headless, lanzado con Playwright 1.63.0 y `--autoplay-policy=no-user-gesture-required`.
- Ventana de 1280×800. La demo del repo (`demo/`, con su `build/` ya compilado) se sirvió por `http://localhost`.
- La librería `ireal-musicxml` de jsDelivr está bloqueada por el proxy del entorno. Se sustituyó por un módulo vacío porque solo se usa para listas iReal.
- No hay Web MIDI, así que se usó el sintetizador local.

**Configuración de cada ejemplo:** la de la demo (`data-renderer`/`data-converter` del desplegable). `blue-bag-folly` no está en el desplegable: se cargó con el botón de subida de la demo y se forzó Verovio como renderer y como conversor.

**Instrumentación** (`lab-cursor/run.js`):
- Un **AudioWorklet** conectado con `player.connect()` recoge la envolvente del audio real del sintetizador, con resolución de 16 muestras (0,36 ms a 44,1 kHz).
- Un **MutationObserver** registra cada nota que pasa a `fill = rgb(234, 107, 36)`. Para cada cambio guarda `performance.now()`, `AudioContext.currentTime`, la posición del Player y el siguiente `requestAnimationFrame`.
- Se envuelve `renderer.moveTo` para registrar lo que el Player le pasa en cada fotograma.

**Referencia de audio:**
- Se lee el MIDI que el Player cargó de verdad (`player.midi`).
- El audio se ancla a ese MIDI en el primer sonido tras el silencio inicial, el primer valor > 1e-4.
- Validación del ancla: se promedia la envolvente alineada a **todos** los note-on previstos y se busca la subida.
  - En los ejemplos con ataque percusivo (`asa-branca`, `salma-ya-salama`, `baiao-miranda`) la subida cae a −1,1…+1,1 ms del ancla.
  - En los de ataque lento (`maqam-rast`, `blackwood`, `blue-bag-folly`) esta validación no es concluyente: da entre −58 y +70 ms porque el instrumento tarda en subir. En esos ejemplos el ancla sigue siendo el primer sonido.

**Se probó y se descartó** detectar los ataques uno a uno sobre la mezcla: batería, acordes y bajo daban falsos positivos y alias rítmicos de 125-250 ms.

### 2.2 Qué se mide

Para cada cambio de nota resaltada:

| Clave | Definición |
|---|---|
| **A** | Posición del Player cuando cambia el resaltado − instante de esa nota según la partitura. Es el retraso del sondeo por fotograma. |
| **B** | Note-on del MIDI más cercano − instante de esa nota según la partitura. Comprueba que la nota resaltada es la que suena. |
| **C** | `currentTime` en el cambio del DOM − instante en que el sintetizador **renderizó** esa nota. Es el desfase respecto al audio, sin contar la salida. |
| **F** | Del cambio del DOM al siguiente `requestAnimationFrame`. Aproxima cuándo se pinta. |
| **D** | C + F − `outputLatency`. Aproxima «se ve» − «se oye». |

En D se usa el `outputLatency` que declara el navegador, que aquí fue 32 ms. Es una salida de audio sin tarjeta real.

Se excluyen los cambios sin note-on a ±60 ms: silencios y segundas notas de ligadura. Fueron 17 de 107 en `blue-bag-folly`, 1 en cada ejecución corta de `maqam-rast` y 1 en la larga.

### 2.3 Resultados conjuntos **«medido»**

**n = 1158 cambios de nota**, 17 ejecuciones, 6 partituras (`asa-branca`, `maqam-rast`, `salma-ya-salama`, `baiao-miranda`, `blackwood-ex-29`, `blue-bag-folly`). Incluye 2 ejecuciones en modo horizontal.

| Medida (ms) | n | Mediana | p25-p75 (RIQ) | p5-p95 | Mín / Máx |
|---|---|---|---|---|---|
| A: posición del Player − nota en partitura | 1158 | **10,0** | 7,6-14,6 (7,0) | 0,7-19,6 | 0,0 / 50,8 |
| B: note-on MIDI − nota en partitura | 1158 | 0,0 | 0,0-0,0 (0,0) | −0,7-0,0 | −4,2 / 0,4 |
| C: cambio en el DOM − audio renderizado | 1158 | **6,3** | 3,5-11,9 (8,3) | −3,1-17,0 | −5,0 / 47,9 |
| F: cambio en el DOM → siguiente fotograma | 1158 | 15,6 | 15,4-15,7 (0,3) | 14,6-15,9 | 3,3 / 16,1 |
| D: siguiente fotograma − audio oído (con outputLatency = 32 ms) | 1158 | **−10,4** | −13,2 a −4,8 (8,4) | −19,7 a 0,5 | −23,6 / 22,0 |
| Arranque: primer sonido − arranque del reloj del Player (por ejecución) | 17 | 3,3 | 2,9-5,1 | 2,1-6,7 | −1,3 / 8,7 |

- Intervalo entre fotogramas: mediana 16,7 ms (60 Hz).
- Signo: positivo significa que el resaltado llega **después**; negativo, que llega **antes**.

### 2.4 Por ejecución **«medido»** (medianas en ms)

| Ejecución | Conversor | n | A | C | D | Arranque |
|---|---|---|---|---|---|---|
| asa-branca | FetchConverter | 86 | 13,1 | 6,9 | −9,4 | 6,2 |
| asa-branca r2 | FetchConverter | 86 | 18,9 | 15,6 | −0,7 | 3,3 |
| asa-branca r3 | FetchConverter | 86 | 18,5 | 15,2 | −1,2 | 3,3 |
| maqam-rast | Verovio | 37 | 11,2 | 6,1 | −10,5 | 5,1 |
| maqam-rast r2 | Verovio | 37 | 10,2 | 5,1 | −11,6 | 5,1 |
| maqam-rast r3 | Verovio | 37 | 1,5 | −3,6 | −20,2 | 5,1 |
| maqam-rast (150 s) | Verovio | 132 | 9,8 | 4,7 | −12,0 | 5,1 |
| salma-ya-salama | FetchConverter | 88 | 10,7 | 8,0 | −8,6 | 2,9 |
| salma-ya-salama r2 | FetchConverter | 89 | 9,3 | 6,3 | −10,2 | 2,9 |
| salma-ya-salama r3 | FetchConverter | 89 | 9,2 | 6,3 | −10,0 | 2,9 |
| baiao-miranda | FetchConverter + timemap.json | 31 | 7,6 | 5,4 | −11,1 | 2,9 |
| baiao-miranda r2 | FetchConverter + timemap.json | 31 | 8,0 | 5,7 | −11,4 | 2,9 |
| baiao-miranda r3 | FetchConverter + timemap.json | 31 | 6,6 | 3,7 | −12,8 | 2,9 |
| blackwood-ex-29 | VerovioStatic | 10 | 1,2 | −1,7 | −18,6 | 2,9 |
| asa-branca horizontal | FetchConverter | 86 | 8,9 | 5,7 | −10,6 | 3,3 |
| salma-ya-salama horizontal | FetchConverter | 112 | 6,9 | −1,6 | −18,0 | 8,7 |
| blue-bag-folly | Verovio (subida) | 90 | 15,6 | 16,9 | 0,1 | −1,3 |

**Lectura de los datos** **«medido»**:
1. **La dispersión dentro de una ejecución es pequeña** (RIQ de A entre 1,2 y 2 ms en la mayoría), pero la mediana cambia mucho de una ejecución a otra (1,2 a 18,9 ms).
   - Las notas caen en una rejilla de pocos valores (múltiplos de 250 ms, por ejemplo) y los fotogramas van cada 16,7 ms. La fase entre ambas rejillas se fija en `play()` y se mantiene.
   - Por eso el retraso del sondeo es casi constante en cada reproducción y aleatorio entre reproducciones, entre 0 y 1 fotograma.
2. **B ≈ 0 en todas las ejecuciones.** La nota resaltada es la que suena, incluso:
   - en las repeticiones de `salma-ya-salama` (74 compases tocados para 36 escritos) y `asa-branca` (65 para 34);
   - en la anacrusa;
   - tras el cambio de tempo.
3. **El primer evento ya está resaltado antes de pulsar play** en las 7 partituras y modos probados: el primer cambio registrado fue siempre el evento 1. Encaja con que el `ResizeObserver` llama a `onResize` → `_move` al cargar (`src/Player.ts:234-239`) **«leído»**.

---

## 3. Paginación y desplazamiento

### 3.1 Cómo pagina **«leído»**

1. Verovio maqueta con páginas del tamaño del **padre del contenedor**:
   - `pageHeight = alto_padre × 100 / scale`
   - `pageWidth = ancho_padre × 100 / scale` (`src/VerovioRenderer.ts:106-116`)
   - Usa `adjustPageHeight: true`, y `breaks: 'smart'` en vertical o `'none'` en horizontal (`:40-51`).
2. Se renderizan **todas** las páginas de golpe (`:117-120`) y se apilan como `div.sheet-page` (`src/VerovioRendererBase.ts:59-66`).
3. En vertical, cada SVG se escala al 100 % del ancho con `viewBox` (`:68-76`).
4. No hay «pasar página»: la ventana entera se desplaza.
5. Al redimensionar, un `ResizeObserver` con 100 ms de espera vuelve a maquetar y renderizar todo (`src/Player.ts:234-239`; `VerovioRenderer.onResize`).
6. **Medido** con contenedor de 50vh y ventana de 1280×800: `asa-branca` salió en 3 páginas, `salma-ya-salama` en 4 y `maqam-rast` en 10, con alturas de 195 a 402 px.

### 3.2 Cómo desplaza mientras suena

**Vertical**
- **«leído»**: en cada cambio de evento llama a `system.scrollIntoView({behavior: 'smooth', block: 'center'})` (`src/VerovioRendererBase.ts:242-247`). Si el sistema ya está centrado, no se mueve.
- **«leído»**: cada evento `scroll` de la ventana dispara `onEvent` → `_refresh()`, que vuelve a medir con `getBoundingClientRect()` todas las notas (`src/Player.ts:241-247`, `src/VerovioRendererBase.ts:128-167`).
- **«medido»**: ese recálculo cuesta una mediana de 0,6-1,8 ms por evento `scroll`, con máximo de 5,0 ms en `maqam-rast` (376 eventos). Sobre 3 ejecuciones y n = 40-83 eventos `scroll` cada una.

**Horizontal**
- **«leído»**: en cada fotograma hace `scrollTo` del contenedor (`behavior: 'auto'`) para dejar el cursor a la misma x que la primera nota de la partitura. Interpola dentro del compás con `offset/duration` (`src/VerovioRendererBase.ts:255-265`).

**Medido en vertical** (31 cambios de sistema en 15 ejecuciones verticales):

| Medida | Mediana | p25-p75 | Mín / Máx |
|---|---|---|---|
| Del resaltado de la 1.ª nota del sistema nuevo al primer movimiento del scroll | **15,6 ms** (1 fotograma) | 15,1-15,7 | 12,1 / 31,9 |
| Duración de la animación | **200 ms** | 167-233 | 100 / 233 |
| Desplazamiento | 184 px | 130-209 | −229 / 229 |
| Posición del borde superior del sistema nuevo justo antes, en una ventana de 800 px | 513 px | 477-532 | 82 / 557 |
| Sistemas completos visibles por debajo del actual (por fotograma, n = 35407) | 1 | 1-2 | 0 / 2 |

- 3 de los 32 desplazamientos fueron **hacia arriba** (−229 px), por saltos de repetición en `salma-ya-salama`.
- 1 cambio de sistema no movió la página.

**Medido en horizontal** (2 ejecuciones):
- Cursor fijo a una mediana de **287 px** (`asa-branca`) y **210 px** (`salma-ya-salama`) del borde izquierdo de un visor de 1264 px.
- Velocidad de desplazamiento: 0,148 px por ms de música en ambas.
- Desplazamiento por fotograma: mediana 2-3 px. En `salma-ya-salama` hubo un salto de 2117 px al volver atrás por una repetición, que no se suaviza.

### 3.3 Cuánto se adelanta

1. **Vertical: nada en el tiempo** **«leído» + «medido»**.
   - Reacciona un fotograma *después* de que se ilumine la primera nota del sistema nuevo y tarda unos 200 ms en llegar.
   - No es grave porque, al centrar el sistema actual, el siguiente ya estaba a la vista (su borde superior a unos 513 de 800 px). Durante la reproducción queda una mediana de 1 sistema completo visible por delante.
2. **Horizontal: espacio, no tiempo** **«medido»**.
   - Por delante del cursor quedan una mediana de **977 px ≈ 6,6 s** (`asa-branca`) y **1054 px ≈ 7,1 s** (`salma-ya-salama`).
   - Por detrás, unos 287/0,148 ≈ 1,9 s y 210/0,148 ≈ 1,4 s.
   - Estas cifras dependen del zoom (`scale: 60` en la demo) y del tempo.

---

## 4. Ideas reutilizables para un visor Verovio + mapa `id de nota → ms` de una grabación humana

Solo ideas, por la GPL. La columna «Base» dice si la idea se apoya en lectura o en medición.

| # | Idea | Cómo lo hace musicxml-player | Cómo llevarla a un mapa `id → ms` humano | Base |
|---|---|---|---|---|
| 1 | Separar la línea de tiempo del audio de la geometría de la partitura | Tabla de compases desenrollada (conversor) frente a timemap de Verovio sin expandir (renderer) | El mapa humano *es* la línea de tiempo. De Verovio solo hace falta id → elemento SVG/sistema/página. No mezclar ms de Verovio con ms de la grabación | leído §1.1.3 |
| 2 | Repeticiones: de compás expandido a compás escrito | Sufijo `-rendN` → índice original | Clave `(id, vuelta)` o lista de instantes por id. Ordenar todo en una lista plana `[{ms, ids}]` desenrollada | leído §1.1.4; medido B ≈ 0 con repeticiones |
| 3 | Búsqueda de «último evento con t ≤ ahora» | Búsqueda binaria + punto de inserción − 1, por fotograma | Igual sobre la lista plana del mapa humano: O(log n) por fotograma, sin búsqueda lineal adicional | leído §1.2.2; medido: coste < 0,3 ms p95 |
| 4 | Conjunto de notas sonando, no solo la última | Arrastra notas activas con `on`/`off` | El mapa humano solo da ataques. Para el `off` hace falta el siguiente ataque de la misma voz o la duración escrita escalada al tempo local | leído §1.2.4 |
| 5 | Pintar por diferencias y restaurar atributos | Solo toca el DOM si cambia el evento; guarda y restaura `fill`/`stroke` | Igual; mejor con una clase CSS que con atributos | leído §1.2.5; medido: coste por fotograma bajo |
| 6 | Compensar la latencia de salida | **No lo hace** | Usar `AudioContext.getOutputTimestamp()` / `outputLatency`, o el `currentTime` del `<audio>` más un desfase calibrable. Aquí la latencia declarada (32 ms) ya cambia el signo del error | leído §1.3; medido D ≈ −10 ms |
| 7 | Anticipar medio fotograma | No: sondea con rAF y el error va de 0 a 1 fotograma, fijo en cada reproducción | Evaluar `t + ~8 ms`, o el `t` previsto al pintar (siguiente vsync) | medido A: mediana 10 ms, 0,7-19,6 ms p5-p95 |
| 8 | Reescalar dentro del compás | No: suma ms absolutos de Verovio (el cursor sí escala) | Con mapa por nota no hace falta. El cursor continuo se interpola entre ataques consecutivos del mapa, no con la duración del compás | leído §1.1.5 |
| 9 | Ligaduras | Verovio da la nota de destino como `on` propio y el resaltado salta sin sonido | En la grabación no hay ataque para la nota de destino: darle el instante interpolado por la partitura o fundirla con la de origen | medido §1.1.8 |
| 10 | Ids estables | `xmlIdChecksum` / `--xml-id-checksum` | Imprescindible para que el mapa siga valiendo tras volver a renderizar. Fijar también la versión de Verovio | leído §1.4.3 |
| 11 | Pre-render estático | SVG + timemap generados con la CLI (`VerovioStatic*`) | Generar SVG e ids una vez, junto con el mapa. El cliente no necesita WASM | leído |
| 12 | Saltar al pulsar una nota | Click → instante; con repeticiones elige la vuelta más cercana a la posición actual | Igual con `(id, vuelta)` | leído §1.2.7 |
| 13 | Seguimiento vertical | `scrollIntoView` del sistema, centrado y suave, al cambiar de sistema | Adelantarlo: desplazar cuando el cursor entra en el último compás del sistema, o antes con el tiempo restante del mapa. Fijar la duración de la animación | medido: 1 fotograma de retraso, 200 ms de animación |
| 14 | Seguimiento horizontal | Cursor fijo a x constante, `scrollTo` en cada fotograma | Buena base. Suavizar los saltos de repetición (aquí 2117 px de golpe) | medido §3.2 |
| 15 | Geometría en caché | `getBoundingClientRect` de todas las notas tras cada `scroll` | Guardar posiciones relativas al contenedor una vez y recalcular solo al redimensionar | medido: 0,6-1,8 ms por evento `scroll` |
| 16 | Reloj principal frente a reloj de audio | spessasynth corrige el reloj del hilo principal solo si se desvía más de 50 ms (cada 1 s) | Con `<audio>`, leer `currentTime` en cada fotograma y no acumular. Si se suaviza, poner un umbral explícito | leído §1.1.2; medido: arranque 3,3 ms |
| 17 | No copiar `_adjustMidiDuration` | Usa el último tempo para toda la pieza | No aplica con audio real; con MIDI, usar el mapa de tempo completo | medido: CC en 100000 ms frente a 109333 ms |

---

## Reproducir

Todo está en `lab-cursor/`:
- `run.js`: captura.
- `analyze3.py`: métricas A/B/C/D/F.
- `scroll.py`: desplazamiento.
- `aggregate.py`: tablas.
- `midi.py`: lector SMF.
- `resultados-*.txt`: salidas de las tablas.

Pasos:
1. Servir `demo/` en el puerto 8765 (`python3 -m http.server 8765` dentro de `demo/`).
2. Capturar:

```bash
NODE_PATH=$(npm root -g) node lab-cursor/run.js data/asa-branca.musicxml 30 asa.json
```

3. Analizar:

```bash
python3 lab-cursor/analyze3.py asa.json
```

`run.js` contiene la ruta absoluta del repo, `/home/user/musicxml-player`, para el modo `upload`.

---

## SIN MEDIR

- La latencia de salida con hardware real: tarjeta, altavoces, auriculares con cable o Bluetooth. Aquí `outputLatency` = 32 ms lo declara un Chromium headless sin dispositivo.
- El momento real en que se pinta en una pantalla física (vsync y compositor). F usa el siguiente `requestAnimationFrame` como aproximación.
- Navegadores distintos de Chromium (Firefox, Safari) y dispositivos móviles.
- La velocidad de reproducción distinta de 1 (`velocity` / `playbackRate`) y el bucle (`repeat`).
- El desfase tras saltar pulsando una nota, tras pausar y reanudar, o tras rebobinar. Solo se midió el arranque desde 0.
- El comportamiento con una tabla de compases humana (rubato) en `FetchConverter`: el desacople de notas y cursor dentro del compás (§1.1.5) es solo «leído».
- Una partitura que empiece con un silencio largo (opción `skipToFirstNoteOn` de spessasynth). Solo hubo un caso con 250 ms (`blue-bag-folly`), en el que el sonido empezó 248,7 ms después del reloj, sin salto.
- `_adjustMidiDuration` cuando el tempo **sube**: el CC podría caer después del final y alargar la pieza.
- Las 2 ligaduras de `blue-bag-folly` que quedaron después de los 45 s grabados.
- Los renderers OSMD y MuseScore, el conversor MMA (necesita servidor) y la opción `unroll`.
- Redimensionar durante la reproducción, partituras grandes y su coste en móviles.
- Si los ids de Verovio se mantienen estables entre versiones u opciones.
- El desplazamiento manual del usuario durante la reproducción. Según el código, la página vuelve al sistema en el siguiente cambio de nota («leído», no comprobado).
