# Plan de Pruebas

**Referencia normativa:** ISO/IEC/IEEE 29119 (partes 2 y 3: proceso y
documentación de pruebas).
**Estado:** Vivo — describe la suite real (`tests/`), no un plan aspiracional.
**Última verificación:** 2026-09-14 — `python -m pytest -q` →
188 passed, 8 skipped. `python -m mypy src/` → sin issues.

## 1. Alcance y estrategia

| Nivel | Qué cubre | Ubicación |
|---|---|---|
| Unitario — dominio | Reglas de negocio puras: validación de mensajes, sliding window, degradación, clasificación | `tests/domain/` |
| Unitario — infraestructura | Repositorios, rate limit, seguridad (HMAC), registro de dispositivos, cada adaptador de IA por separado | `tests/infrastructure/` |
| Integración — aplicación | `CasoDeUsoResponderMensaje` orquestando servicio + repositorio | `tests/application/` |
| Integración — HTTP | Autenticación, rate limit, propiedad de sesión, consentimiento, salud — vía `TestClient` de FastAPI, con el motor de IA reemplazado por un doble de prueba (no se llama a un LLM real) | `tests/presentation/` |
| Estructural | El propio `flow.json` (grafo válido, sin ciclos, sin variables CEL no documentadas) | `tests/infrastructure/test_flow_structure.py` |
| Fábrica | `crear_servicio` construye la combinación correcta de dependencias según flags | `tests/test_crear_servicio.py` |
| Configuración | `Settings` falla rápido ante configuración inválida/incompleta | `tests/test_config.py` |

**Fuera de esta suite (requieren infraestructura externa, se saltan si no
está disponible):** `tests/infrastructure/test_repository_postgres.py`
(Postgres real) y `tests/infrastructure/test_rate_limit_redis.py` (Redis
real) — explican en su docstring cómo levantar el servicio local para
correrlos. Esto explica los "8 skipped" del run estándar.

**Explícitamente fuera de alcance de esta suite:** calidad subjetiva de la
respuesta generada (tono, coherencia devocional) — no hay test que llame
al LLM real y evalúe su salida; los tests que ejercitan los adaptadores
usan dobles de prueba (stubs) para el LLM. Evaluar la calidad de la voz
requeriría un proceso de revisión humana o un LLM-as-judge, no cubierto
aquí.

## 2. Herramientas

| Herramienta | Propósito | Comando |
|---|---|---|
| pytest + pytest-cov | Ejecución y cobertura | `python -m pytest -q` |
| mypy | Tipado estático | `python -m mypy src/` (config: `.mypy.ini`) |
| pylint | Calidad estática | `uv run --extra lint python -m pylint src/la_santisima_conversacional` (config: `.pylintrc`) |
| black | Formato | `uv run --extra lint python -m black src/ tests/` (config: `pyproject.toml`) |
| pre-commit | Orquesta las 4 anteriores + hooks de higiene (trailing whitespace, YAML) | `.pre-commit-config.yaml` |

## 3. Convención de nombres

Todos los tests siguen `test_<qué_se_prueba>_<resultado_esperado>` en
español, describiendo comportamiento observable, no implementación
(`test_mensaje_con_session_id_ajeno_devuelve_404`, no
`test_validar_propiedad_sesion`). Clases `_Casos*` (sin `Test` al inicio,
para que pytest no las recolecte directamente) definen casos compartidos
entre implementaciones intercambiables (ej. `RegistroDispositivosMemory`
vs. `RegistroDispositivosSQLite`) — ver `_CasosRegistroDispositivos` en
`test_dispositivos.py`: garantiza que ambas cumplen exactamente el mismo
contrato observable.

## 4. Doble de prueba para el motor de IA

Los tests HTTP (`test_http_api.py`) y de aplicación reemplazan
`servicio_respuestas.responder_mensaje`/`responder_mensaje_stream` por
funciones stub que devuelven texto fijo — nunca se llama a DeepInfra
durante la suite. Esto es deliberado: mantiene la suite rápida (3.5s para
188 tests), determinista, y sin costo ni dependencia de red — pero
significa que **ningún test de este repositorio detecta si DeepInfra deja
de responder correctamente, cambia su formato de respuesta, o si un
modelo específico deja de estar disponible**. Eso solo se detecta en
verificación manual (ver README) o en producción vía `/health/ready`.

## 5. Brechas conocidas (priorizadas)

| Brecha | Riesgo si no se cierra | Costo estimado de cerrarla |
|---|---|---|
| RNF-003: timeout/reintentos del LLM nunca se ejercitan contra un servidor lento real o simulado | Bajo-medio: si el timeout tiene un bug, se descubre en producción como una request colgada | Medio — requiere un servidor HTTP de prueba que responda lento a propósito |
| RNF-006: sin test parametrizado único que corra el mismo escenario contra ambos motores (CrewAI/LangChain) con las mismas aserciones | Medio: los dos motores pueden divergir en comportamiento sin que ningún test lo note, pese a que la arquitectura promete paridad (ver [ADR-0001](adr/0001-dos-motores-intercambiables.md)) | Medio-alto — requiere abstraer las aserciones actuales en un set parametrizable por adaptador |

Ver el detalle fila por fila en [rtm.md](rtm.md).

## 6. Ejecución en CI

Configurado en [.github/workflows/ci.yml](../.github/workflows/ci.yml):
job `test` corre `pytest` (con cobertura) en Python 3.10/3.11/3.12; job
`quality` corre `mypy`, `black --check` y `pylint` en cada push a `main` y
en cada pull request. Esto es lo que hace que "sin errores" sea una
propiedad verificada por máquina en cada cambio futuro, no solo en esta
revisión puntual — pero solo corre en GitHub Actions: no hay evidencia en
este repositorio de que se haya ejecutado todavía (sin historial de commits
al momento de escribir esto), así que su primera corrida real validará si
el pipeline en sí está bien configurado.
