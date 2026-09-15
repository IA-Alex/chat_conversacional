# Pruebas de carga (Locust)

Pruebas de carga para el backend HTTP (`src/la_santisima_conversacional/presentation/http_api.py`),
usando [Locust](https://locust.io/). **No están wireadas en CI**: CI corre
únicamente `pytest` (ver `pyproject.toml` → `[project.optional-dependencies].test`).
Estas pruebas necesitan un servidor real corriendo, con acceso a un LLM
(real vía `DEEPINFRA_API_KEY`, o un stub local) — no tiene sentido, ni es
seguro, ejecutarlas automáticamente en cada push.

## Instalar

```bash
pip install -e ".[load]"
```

## Levantar el servidor a probar

Desde la raíz del repo, con `src` en el paquete instalado en modo editable:

```bash
SANTISIMA_DEBUG=true DEEPINFRA_API_KEY=<tu-api-key> \
    uvicorn la_santisima_conversacional.presentation.http_api:app
```

`SANTISIMA_DEBUG=true` relaja CORS y auth de administración para desarrollo
local — el flujo de device_token (registro → consentimiento → sesión →
mensajes) sigue aplicando igual, es el único camino que existe para
`/api/v1/mensajes`. Sin `DEEPINFRA_API_KEY` el motor de IA arranca en modo
degradado (fallback) — sirve para probar `degradation_flow.py`, pero no
representa carga realista sobre el LLM real.

## Archivos

- **`locustfile.py`** — flujo completo de un usuario real: registro +
  consentimiento + sesión una vez, luego mensajería sostenida con
  reinicios/sesiones nuevas ocasionales. Es el locustfile por defecto
  (`locust -f tests/load/locustfile.py` sin más flags lo usa).
- **`scenarios/auth_flow.py`** — solo registro → consentimiento → sesión,
  sin enviar mensajes. Para validar el camino de identidad bajo
  concurrencia aislado del costo de golpear al LLM.
- **`scenarios/messaging_flow.py`** — mensajería sostenida dentro del
  límite por dispositivo (espaciada para quedarse debajo de
  `rate_limit_por_minuto`, 20/min por defecto). Es el escenario para el
  objetivo principal de carga sostenida.
- **`scenarios/rate_limit_test.py`** — ráfaga deliberada desde
  dispositivos individuales para confirmar que el servidor devuelve 429 al
  exceder el límite por minuto. Falla la corrida (exit code != 0) si no se
  observó ningún 429.
- **`scenarios/degradation_flow.py`** — sondea `GET /health/ready` y
  `GET /metrics/health` repetidamente mientras hay mensajería concurrente,
  para confirmar que el servicio se mantiene respondiendo (aunque sea en
  modo degradado) en vez de caerse.
- **`scenarios/db_pool_test.py`** — 100 usuarios mandando mensajes sin
  pausa mientras se sondea `db_connection_pool_active_connections`. Requiere
  el backend con **Postgres** (`SANTISIMA_USAR_POSTGRES=true`): mide si el
  servidor aguanta las conexiones concurrentes que abre
  `PostgresConversationRepository` (una por operación, sin pool). Falla la
  corrida si el backend reporta `sqlite`, para que un escenario que no midió
  nada no pase como verde.

## Cómo correr cada escenario

Con interfaz web (por defecto en http://localhost:8089):

```bash
locust -f tests/load/locustfile.py --host http://127.0.0.1:8000
```

En modo headless, cada escenario con parámetros pensados para su propósito:

```bash
# Flujo completo (uso general / smoke de carga)
locust -f tests/load/locustfile.py --headless \
    -u 50 -r 10 -t 5m --host http://127.0.0.1:8000

# Solo auth/identidad bajo concurrencia
locust -f tests/load/scenarios/auth_flow.py --headless \
    -u 50 -r 50 -t 1m --host http://127.0.0.1:8000

# Mensajería sostenida (ver objetivo principal más abajo)
locust -f tests/load/scenarios/messaging_flow.py --headless \
    -u 100 -r 1 -t 30m --host http://127.0.0.1:8000

# Ráfaga de rate limit -- confirma que aparecen 429
locust -f tests/load/scenarios/rate_limit_test.py --headless \
    -u 25 -r 25 -t 30s --host http://127.0.0.1:8000

# Degradación: salud + mensajería concurrente
locust -f tests/load/scenarios/degradation_flow.py --headless \
    -u 20 -r 10 -t 5m --host http://127.0.0.1:8000

# Saturación de conexiones Postgres (requiere backend con SANTISIMA_USAR_POSTGRES=true)
locust -f tests/load/scenarios/db_pool_test.py --headless \
    -u 100 -r 20 -t 5m --host http://127.0.0.1:8000
```

`-u` = usuarios concurrentes simulados, `-r` = tasa de spawn (usuarios/seg),
`-t` = duración de la corrida.

## Objetivo principal: carga sostenida

Escenario de referencia (`scenarios/messaging_flow.py`) para validar el
backend bajo carga realista sostenida:

- **100 usuarios concurrentes** (dispositivos distintos)
- **Ramp-up de 5 minutos** (`-r` ≈ `100 usuarios / 300s` ≈ `0.33`, o
  `--spawn-rate` explícito equivalente)
- **30 minutos sostenidos** tras el ramp-up (`-t` total ≈ 35m, o usar
  `--run-time` contando el ramp-up aparte)
- **p95 de latencia < 3s** en `/api/v1/mensajes` (columna "95%" del
  resumen de Locust, o `--csv` + el archivo `_stats.csv` para análisis
  posterior)
- **Tasa de error < 1%** (excluyendo 429 esperados si el ritmo por usuario
  se mantiene realmente debajo del límite configurado — con
  `messaging_flow.py` bien parametrizado, 429 no debería aparecer en este
  escenario; si aparece, cuenta como error, ver el propio archivo)
- **Rate limit rechazando al límite configurado**: validado por separado
  con `rate_limit_test.py`, no dentro de este escenario sostenido.

Ejemplo de comando con ramp-up de 5 min y sostenido 30 min (35m totales):

```bash
locust -f tests/load/scenarios/messaging_flow.py --headless \
    -u 100 -r 0.34 -t 35m --host http://127.0.0.1:8000 \
    --csv tests/load/resultados/sostenida
```

(el directorio de `--csv` debe existir de antemano; no se versiona en el
repo).

`tests/load/resultados/` sí está versionado (con un `.gitkeep`) para que el
comando funcione tal cual, pero su **contenido** está en `.gitignore`: los
CSV/HTML son artefactos de una corrida concreta (máquina, fecha, red), no
fuente.

## Cómo leer los resultados

Cada corrida con `--csv <prefijo>` genera cuatro archivos:

| Archivo | Qué mirar |
|---|---|
| `<prefijo>_stats.csv` | Una fila por endpoint: `Request Count`, `Failure Count`, y las columnas `50%`/`95%`/`99%` de latencia |
| `<prefijo>_stats_history.csv` | Series temporales — es donde se ve si la latencia **degradó durante** la corrida (fuga de memoria, agotamiento de conexiones), no solo el promedio final |
| `<prefijo>_failures.csv` | Cada tipo de fallo con su mensaje; vacío o inexistente = sin fallos |
| `<prefijo>_exceptions.csv` | Excepciones no asociadas a un request |

Para el objetivo sostenido, el criterio se lee así:

```bash
# p95 de /api/v1/mensajes (columna "95%")
grep '/api/v1/mensajes' tests/load/resultados/sostenida_stats.csv

# ¿la latencia creció con el tiempo? Comparar el primer y último tramo
head -5 tests/load/resultados/sostenida_stats_history.csv
tail -5 tests/load/resultados/sostenida_stats_history.csv
```

Un p95 final aceptable con una tendencia creciente en `_stats_history.csv`
no es un aprobado: significa que la corrida terminó justo antes de cruzar
el umbral, y a los 60 minutos habría fallado.

## Notas

- Estas pruebas **no corren en CI**. CI ejecuta `pytest` sobre `tests/`
  (excluyendo `tests/load/`, que Locust descubre solo al invocarse
  explícitamente con `-f`, nunca vía `pytest`).
- Requieren un servidor corriendo aparte (no arrancan uno). Sin
  `DEEPINFRA_API_KEY`, el motor de IA queda en modo degradado — útil solo
  para `degradation_flow.py`.
- El límite de registro por IP (`rate_limit_registro_por_minuto`, 10/min
  por defecto) puede frenar el `on_start` de muchos usuarios simulados
  arrancando desde la misma IP local a la vez — es esperado, no un bug de
  estas pruebas (ver el manejo de 429 en `on_start` de cada escenario).
