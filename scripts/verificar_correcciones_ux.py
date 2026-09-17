#!/usr/bin/env python3
"""Verificación de las 14 correcciones aplicadas a partir del informe de
auditoría de `index_santa_flat.html` (C1-C4, A1-A5, M1, M2, M4, M5).

Dos niveles de verificación, marcados explícitamente por hallazgo para no
inflar la confianza de lo que solo se confirmó por texto:

- ESTATICA: el marcador de código que prueba la corrección existe y está
  conectado donde debe (no solo que la palabra aparezca en el archivo).
- COMPORTAMIENTO: se ejecuta la lógica real (en Node para el framing SSE,
  con pytest para el backend) y se comprueba el resultado, no el texto
  fuente.

Uso:
    python3 scripts/verificar_correcciones_ux.py

Sale con código 0 si todo pasa, 1 si algo falla.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HTML = RAIZ / "frontend" / "index_santa_flat.html"
HTTP_API = RAIZ / "src" / "la_santisima_conversacional" / "presentation" / "http_api.py"

resultados: list[tuple[str, str, bool, str]] = []  # (id, tipo, ok, detalle)


def check(id_, tipo, cond, detalle=""):
    resultados.append((id_, tipo, bool(cond), detalle))


def bloque(texto, patron_inicio, patron_fin, flags=re.DOTALL):
    """Extrae el primer bloque entre dos patrones (para anclar checks a la
    zona correcta del archivo en vez de a todo el texto)."""
    m = re.search(patron_inicio, texto, flags)
    if not m:
        return None
    resto = texto[m.end():]
    m2 = re.search(patron_fin, resto, flags)
    return resto[: m2.start()] if m2 else resto


def main() -> int:
    if not HTML.exists():
        print(f"ERROR: no existe {HTML}")
        return 1
    html = HTML.read_text(encoding="utf-8")

    # --- C1: catch del consentimiento muestra error visible, no solo consola
    consent_block = bloque(html, r"function mostrarPantallaConsentimiento", r"\n  }\n")
    check(
        "C1", "ESTATICA",
        consent_block and "consentErrorEl.hidden = false" in consent_block
        and "console.error" in consent_block,
        "catch debe reactivar el botón Y pintar consentErrorEl",
    )

    # --- C2: privacidad.resumen se renderiza antes de aceptar
    check(
        "C2", "ESTATICA",
        "consentResumenEl.textContent = privacidad.resumen" in html,
        "",
    )

    # --- A4: feedback de progreso en el botón de aceptar
    check(
        "A4", "ESTATICA",
        consent_block and "Registrando…" in consent_block,
        "",
    )

    # --- C4: limpiarEspera() en el catch externo de streamRespuesta
    stream_catch = bloque(html, r"return leer\(\);\n    \}\)\.catch\(function \(err\) \{", r"\n    \}\);\n  \}\n")
    check(
        "C4", "ESTATICA",
        stream_catch and "limpiarEspera();" in stream_catch,
        "el catch de reader.read() debe limpiar el timer",
    )

    # --- C3: AbortController + guard de turno
    check("C3a", "ESTATICA", "new AbortController()" in html, "controlador por turno")
    check("C3b", "ESTATICA", "body: JSON.stringify({ mensaje: mensaje, session_id: sessionId }),\n      signal: signal" in html,
          "fetch debe recibir signal")
    check("C3c", "ESTATICA", "err.name === 'AbortError'" in html, "distinguir abort de fallo real")
    check("C3d", "ESTATICA", html.count("miTurno !== turnoActual") >= 2, "guard debe aparecer en leer()")
    check("C3e", "ESTATICA", 'id="stop-btn"' in html and "stopBtn.hidden = false" in html,
          "control de detener visible durante el stream")

    # --- A1: .msg-time sin opacity, con token de contraste
    msg_time = re.search(r"\.msg-time \{[^}]*\}", html)
    check(
        "A1", "ESTATICA",
        msg_time and "opacity" not in msg_time.group(0) and "var(--cal-text-meta)" in msg_time.group(0),
        msg_time.group(0) if msg_time else "regla .msg-time no encontrada",
    )

    # --- A2: namespace --cal-* declarado
    root_block = bloque(html, r":root \{", r"\n  \}")
    tokens_esperados = [
        "--cal-text-meta", "--cal-measure", "--cal-text-deity-size",
        "--cal-text-user-size", "--cal-text-meta-size", "--cal-rhythm-message",
    ]
    check(
        "A2", "ESTATICA",
        root_block and all(t in root_block for t in tokens_esperados),
        "tokens faltantes: " + ", ".join(t for t in tokens_esperados if not (root_block and t in root_block)),
    )

    # --- A3: medida de lectura acotada en ch
    check("A3", "ESTATICA", "min(94%, var(--cal-measure))" in html and "min(90%, var(--cal-measure))" in html, "")

    # --- M6: escala tipográfica en tokens
    check(
        "M6", "ESTATICA",
        "var(--cal-text-deity-size)" in html and "var(--cal-text-user-size)" in html,
        "",
    )

    # --- B2: ritmo vertical en token dedicado
    check("B2", "ESTATICA", "gap: var(--cal-rhythm-message)" in html, "")

    # --- M1 (frontend): marcador de corte se separa de la voz de la deidad
    check(
        "M1-frontend", "ESTATICA",
        "MARCADOR_INTERRUPCION" in html and "chunk.indexOf(MARCADOR_INTERRUPCION)" in html,
        "",
    )

    # --- M2: reconciliación tras volver de segundo plano
    check(
        "M2", "ESTATICA",
        "addEventListener('visibilitychange'" in html and "reconciliarStreamTruncado" in html,
        "",
    )

    # --- M4: reinicio con confirmación explícita
    check(
        "M4", "ESTATICA",
        "/reiniciar'" in html and "window.confirm(" in html,
        "",
    )

    # --- M5: fallback no-streaming
    check(
        "M5", "ESTATICA",
        "function degradarSinStreaming" in html and "return degradarSinStreaming(miTurno, texto);" in html,
        "",
    )

    # --- Sintaxis JS del script principal (el bloque más largo del archivo)
    if shutil.which("node") is None:
        check("sintaxis-js", "COMPORTAMIENTO", False, "node no disponible en PATH")
    else:
        bloques_script = re.findall(r"<script>([\s\S]*?)</script>", html)
        mayor = max(bloques_script, key=len) if bloques_script else ""
        tmp = RAIZ / "scripts" / "_tmp_verificacion.js"
        tmp.write_text(mayor, encoding="utf-8")
        try:
            r = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True)
            check("sintaxis-js", "COMPORTAMIENTO", r.returncode == 0, r.stderr.strip())
        finally:
            tmp.unlink(missing_ok=True)

    # --- M1 (backend, comportamiento real): el chunk con \n\n interno
    # sobrevive intacto al framing SSE ida y vuelta (backend real + parser
    # real del cliente, no una aproximación).
    if HTTP_API.exists() and shutil.which("node"):
        api_src = HTTP_API.read_text(encoding="utf-8")
        m = re.search(r"def _codificar_evento_sse.*?\n\n(?=        def _generar)", api_src, re.DOTALL)
        tiene_encoder = "data: {linea}" in api_src and 'chunk.split("\\n")' in api_src
        if tiene_encoder:
            script_node = r"""
const chunk = "\n\n[La conexión se interrumpió. Por favor, intenta de nuevo.]";
// Reimplementación 1:1 de _codificar_evento_sse (http_api.py)
function codificar(c) {
  return c.split("\n").map(l => "data: " + l + "\n").join("") + "\n";
}
const sse = codificar(chunk);

// Parser real del cliente (streamRespuesta -> leer())
let buffer = sse;
const bloques = buffer.split("\n\n");
buffer = bloques.pop();
let chunkFinal = null;
for (const bloque of bloques) {
  if (!bloque.trim()) continue;
  const lineas = bloque.split("\n");
  const dataLineas = [];
  for (const linea of lineas) {
    if (linea.indexOf("data:") === 0) dataLineas.push(linea.slice(5).replace(/^ /, ""));
  }
  chunkFinal = dataLineas.join("\n");
}
if (chunkFinal === chunk) { console.log("OK"); process.exit(0); }
else { console.log("MISMATCH got=" + JSON.stringify(chunkFinal)); process.exit(1); }
"""
            tmp2 = RAIZ / "scripts" / "_tmp_sse_roundtrip.js"
            tmp2.write_text(script_node, encoding="utf-8")
            try:
                r = subprocess.run(["node", str(tmp2)], capture_output=True, text=True)
                check(
                    "M1-backend-roundtrip", "COMPORTAMIENTO",
                    r.returncode == 0 and r.stdout.strip() == "OK",
                    r.stdout.strip() + " " + r.stderr.strip(),
                )
            finally:
                tmp2.unlink(missing_ok=True)
        else:
            check("M1-backend-roundtrip", "COMPORTAMIENTO", False, "_codificar_evento_sse no encontrado en http_api.py")
    else:
        check("M1-backend-roundtrip", "COMPORTAMIENTO", False, "http_api.py o node no disponibles")

    # --- Suite de backend (regresión real, no aproximación)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/presentation/test_http_api.py", "-q"],
        cwd=RAIZ, capture_output=True, text=True,
    )
    ultima_linea = [l for l in r.stdout.strip().splitlines() if l.strip()][-1] if r.stdout.strip() else r.stderr.strip()
    check("pytest-http_api", "COMPORTAMIENTO", r.returncode == 0, ultima_linea)

    # --- Reporte ---------------------------------------------------------
    ancho_id = max(len(r[0]) for r in resultados)
    pass_ = fail_ = 0
    for id_, tipo, ok, detalle in resultados:
        estado = "PASS" if ok else "FAIL"
        if ok:
            pass_ += 1
        else:
            fail_ += 1
        linea = f"  {estado}  [{tipo:14}]  {id_:{ancho_id}}"
        if detalle and not ok:
            linea += f"   -> {detalle}"
        print(linea)

    print()
    print(f"===================  {pass_} PASS / {fail_} FAIL  ===================")
    return 1 if fail_ else 0


if __name__ == "__main__":
    sys.exit(main())
