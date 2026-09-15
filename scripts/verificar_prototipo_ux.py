#!/usr/bin/env python3
"""Verificación de la máquina de estados del prototipo de chat.

El prototipo (`propuesta_index/Santa Muerte Chat.dc.html`) implementa la
máquina de estados que definen los criterios `CV-I1` y §3.3 de
`docs/ux-criterios-evaluacion.md`. Su lógica (componente `DCLogic`) es código
puro sin DOM, así que se extrae y ejecuta en Node con un `DCLogic` simulado.
Esto valida el comportamiento **sin navegador** y sirve como prueba de
regresión de los hallazgos §5.

Uso:
    python3 scripts/verificar_prototipo_ux.py

NOTA IMPORTANTE: `propuesta_index/` está en `.gitignore` — no forma parte del
repositorio versionado. Por eso esto es un script y **no** una prueba de
`pytest`: un test que dependiera de ese directorio fallaría en un clon limpio.
Cuando el prototipo no exista, el script sale con código 0 e informa que se
omitió, en lugar de fallar.

Requiere `node` en el PATH. Sin Node, también se omite sin fallar.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROTOTIPO = RAIZ / "propuesta_index" / "Santa Muerte Chat.dc.html"
PATRON_SCRIPT = re.compile(r'<script type="text/x-dc" data-dc-script>(.*?)</script>', re.DOTALL)

# --- Arnéz de ejecución en Node -------------------------------------------
# `setState` acepta un objeto o una función, igual que la implementación real.
ARNEZ_CABECERA = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

class DCLogic {
  constructor() { this.state = {}; }
  setState(u) {
    const p = (typeof u === 'function') ? u(this.state) : u;
    this.state = Object.assign({}, this.state, p);
  }
}
global.DCLogic = DCLogic;
const Comp = eval(src + '\n; Component');

let pass = 0, fail = 0;
const ok = (name, cond, got) => {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + '  got=' + JSON.stringify(got)); }
};
const fresh = () => {
  const c = new Comp();
  c.state = JSON.parse(JSON.stringify(c.state));
  return c;
};
"""

# --- Casos: ciclo de vida del mensaje (A–B) --------------------------------
ARNEZ_CASOS_AB = r"""
console.log('--- A) ciclo completo ---');
let c = fresh();
c.state.inputValue = 'pregunta';
c.onInputKeyDown({ key: 'Enter' });
ok('A1 eco optimista + esperando + input limpio',
  c.state.phase === 'esperando' && c.state.inputValue === '' &&
  c.state.messages[c.state.messages.length - 1].isUser === true, c.state.phase);
ok('A2 pulso NO se dispara al enviar (§5-#3)', c.state.intensify === false, c.state.intensify);
c.onFirstToken();
ok('A3 pulso SI en primer token (§5-#3)',
  c.state.intensify === true && c.state.phase === 'streameando', c.state.intensify);
c.onChunk('hola ');
c.onChunk('mundo');
const st = c.state.messages.filter(m => m.isDeity && m.streaming);
ok('A4 streaming in-place: 1 solo mensaje',
  st.length === 1 && st[0].text === 'hola mundo', st.map(m => m.text));
c.onDone('esperanza');
const dm = c.state.messages.filter(m => m.isDeity).pop();
ok('A5 done cierra stream y guarda emocion',
  c.state.phase === 'completo' && c.state.emocion === 'esperanza' && !dm.streaming, c.state.phase);

console.log('--- B) corte de stream (§5-#9) ---');
c = fresh();
c.state.inputValue = 'p2';
c.sendMessage();
c.onFirstToken();
c.onChunk('A medias ');
c.onChunk('[La conexión se interrumpió. Por favor, intenta de nuevo.]');
const bm = c.state.messages.filter(m => m.isDeity).pop();
ok('B1 fase interrumpido', c.state.phase === 'interrumpido', c.state.phase);
ok('B2 marcador NO queda en el texto', !bm.text.includes('[La conexión'), bm.text);
ok('B3 texto limpio conservado (sin espacios colgantes)', bm.text === 'A medias', bm.text);
ok('B4 msg.interrupted=true (el template lo pinta)', bm.interrupted === true, bm.interrupted);
ok('B5 msg.interruptedNotice presente',
  typeof bm.interruptedNotice === 'string' && bm.interruptedNotice.length > 0, bm.interruptedNotice);
ok('B6 streaming cerrado (cursor apagado)', bm.streaming === false, bm.streaming);
"""

ARNEZ_CASOS_B2 = r"""
console.log('--- B2) marcador con el formato REAL del motor (salto doble delante) ---');
c = fresh();
c.state.inputValue = 'p2b';
c.sendMessage();
c.onFirstToken();
c.onChunk('Texto real a medias');
c.onChunk('\n\n[La conexión se interrumpió. Por favor, intenta de nuevo.]');
const b2 = c.state.messages.filter(m => m.isDeity).pop();
ok('B7 marcador real no se filtra al texto',
  b2.text === 'Texto real a medias', JSON.stringify(b2.text));
ok('B8 sin residuo de corchetes', !b2.text.includes('['), b2.text);
ok('B9 fase interrumpido con marcador real', c.state.phase === 'interrumpido', c.state.phase);

console.log('--- C) detener conserva texto (§5-#6) ---');
c = fresh();
c.state.inputValue = 'p3';
c.sendMessage();
c.onFirstToken();
c.onChunk('parcial');
c.onStopClick();
const sm = c.state.messages.filter(m => m.isDeity).pop();
ok('C1 phase idle tras detener', c.state.phase === 'idle', c.state.phase);
ok('C2 texto parcial conservado', sm.text === 'parcial' && sm.stopped === true, sm.text);

console.log('--- D) guard de turno ---');
c = fresh();
c.state.inputValue = 'p4';
c.sendMessage();
c.onFirstToken();
c.onChunk('viejo');
c.onStopClick();
const n0 = c.state.messages.length;
c.onChunk('TARDIO');
ok('D1 chunk tardio descartado', c.state.messages.length === n0, c.state.messages.length - n0);
ok('D2 texto tardio no contaminado',
  c.state.messages.filter(m => m.isDeity).pop().text === 'viejo',
  c.state.messages.filter(m => m.isDeity).pop().text);

console.log('--- E) errores ---');
c = fresh();
c.onError('recuperable', 'Demasiadas solicitudes.');
let m = c.state.messages[c.state.messages.length - 1];
ok('E1 recuperable con reintento',
  c.state.phase === 'error_recuperable' && m.canRetry === true && m.isNotice === true, c.state.phase);
c.onError('terminal', 'Sesión no encontrada.');
m = c.state.messages[c.state.messages.length - 1];
ok('E2 terminal sin reintento',
  c.state.phase === 'error_terminal' && m.canRetry === false, c.state.phase);
"""

# --- Casos: tokens, medida y estados derivados (F) -------------------------
ARNEZ_CASOS_F = r"""
console.log('--- F) tokens y medida (§5-#1, #4, #7) ---');
c = fresh();
c.state.viewportWidth = 390;
const vals = c.renderVals();
ok('F1 medida de lectura acotada en ch (§UX-D1)',
  /var\(--cal-measure\)/.test(vals.deityMessageStyle), vals.deityMessageStyle);
ok('F2 metadatos con token de contraste (§5-#4)',
  !/opacity:0\.15/.test(vals.metaStyle('flex-start')) &&
  /--cal-text-meta/.test(vals.metaStyle('flex-start')), vals.metaStyle('flex-start'));
ok('F3 sin hex crudo en estilos',
  !/#[0-9a-f]{6}/i.test(vals.deityTextStyle + vals.userTextStyle + vals.inputFieldStyle), 'hex');
ok('F4 espera + caret + stop expuestos',
  !!vals.waitingDotsStyle && !!vals.dotStyle(0) && !!vals.caretStyle && !!vals.stopButtonStyle, 'ok');
ok('F5 caret apagado en idle', vals.caretStyle === 'display:none;', vals.caretStyle);
c = fresh();
c.state.inputValue = 'x';
c.sendMessage();
c.onFirstToken();
ok('F6 caret visible mientras se streamea',
  /calCaret/.test(c.renderVals().caretStyle), c.renderVals().caretStyle);
c = fresh();
c.state.viewportWidth = 390;
ok('F7 indicador de espera ausente en idle',
  c.renderVals().isWaiting === false, c.renderVals().isWaiting);
c.state.inputValue = 'x';
c.sendMessage();
ok('F8 isWaiting=true tras enviar', c.renderVals().isWaiting === true, c.renderVals().isWaiting);
ok('F9 send bloqueado durante streaming', c.renderVals().canSend === false, c.renderVals().canSend);
c.onFirstToken();
ok('F10 send sigue bloqueado al streamear', c.renderVals().canSend === false, c.renderVals().canSend);
c.onDone('calma');
ok('F11 send reabierto tras completar', c.renderVals().canSend === true, c.renderVals().canSend);

console.log('');
console.log('===================  ' + pass + ' PASS / ' + fail + ' FAIL  ===================');
process.exit(fail ? 1 : 0);
"""

ARNEZ = ARNEZ_CABECERA + ARNEZ_CASOS_AB + ARNEZ_CASOS_B2 + ARNEZ_CASOS_F


def _extraer_logica(html: str) -> str:
    """Devuelve el bloque `<script data-dc-script>` del prototipo."""
    coincidencia = PATRON_SCRIPT.search(html)
    if not coincidencia:
        raise SystemExit(
            'ERROR: no se encontró el bloque <script type="text/x-dc" '
            "data-dc-script> en el prototipo."
        )
    return coincidencia.group(1)


def main() -> int:
    if not PROTOTIPO.exists():
        print(
            "OMITIDO: el prototipo no existe en este árbol de trabajo.\n"
            f"  Esperado en: {PROTOTIPO}\n"
            "  `propuesta_index/` está en .gitignore, así que es normal que no\n"
            "  esté en un clon del repositorio. Nada que verificar."
        )
        return 0

    if shutil.which("node") is None:
        print(
            "OMITIDO: `node` no está disponible en el PATH.\n"
            "  El prototipo se verifica ejecutando su lógica en Node; sin Node\n"
            "  no hay nada que hacer."
        )
        return 0

    logica = _extraer_logica(PROTOTIPO.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ruta_logica = tmp_path / "prototipo.js"
        ruta_arnes = tmp_path / "arnes.js"
        ruta_logica.write_text(logica, encoding="utf-8")
        ruta_arnes.write_text(ARNEZ, encoding="utf-8")

        sintaxis = subprocess.run(
            ["node", "--check", str(ruta_logica)],
            capture_output=True,
            text=True,
            check=False,
        )
        if sintaxis.returncode != 0:
            print("FALLO: el bloque de script del prototipo no es JavaScript válido.")
            print(sintaxis.stderr.strip())
            return 1
        print(f"Sintaxis OK ({len(logica)} caracteres de lógica extraídos).")

        resultado = subprocess.run(
            ["node", str(ruta_arnes), str(ruta_logica)],
            capture_output=True,
            text=True,
            check=False,
        )

    print(resultado.stdout.rstrip())
    if resultado.returncode not in (0, 1):
        print(resultado.stderr.strip())
        return 1

    if resultado.returncode == 0:
        print("\nVerificación de la máquina de estados: OK")
    else:
        print("\nVerificación de la máquina de estados: HAY FALLOS")
    return resultado.returncode


if __name__ == "__main__":
    sys.exit(main())
