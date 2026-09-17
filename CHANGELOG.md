# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este archivo formaliza la gestión de configuración exigida por
ISO/IEC/IEEE 12207 §6.3.5 (trazabilidad de cambios) — no se rellenan
entradas retroactivas que no se puedan verificar contra el historial de
`git log`; a partir de aquí, cada cambio relevante se registra en su
momento.

## [Unreleased]

## [0.1.0] - 2026-09-16

### Added (cont.)
- **Consentimiento explícito diferenciado** (ISO/IEC 29134, DPIA §4):
  nuevo endpoint `POST /api/v1/dispositivos/consentimiento` registra, por
  dispositivo, la versión aceptada del aviso de privacidad
  (`SANTISIMA_AVISO_PRIVACIDAD_VERSION`). `POST /api/v1/mensajes` y
  `.../mensajes/stream` ahora exigen consentimiento vigente (403
  `consentimiento_requerido` si falta o quedó desactualizado por un
  cambio de versión del aviso). `RegistroDispositivos` (memoria y SQLite,
  con migración de esquema para bases existentes) gana
  `registrar_consentimiento`/`obtener_version_consentimiento`.

### Changed
- **Migración de proveedor de IA: OpenAI → DeepInfra.** El backend
  llamaba directo a la API de OpenAI (`OPENAI_API_KEY`, `openai/gpt-4o`).
  Ahora usa DeepInfra vía su endpoint compatible con OpenAI
  (`DEEPINFRA_API_KEY`, `SANTISIMA_DEEPINFRA_API_BASE`), traducido a
  `OPENAI_API_KEY`/`OPENAI_API_BASE` en un único punto (`crear_servicio`)
  para que ni `CrewAIAdapter` ni `LangChainAdapter` necesiten cambios.
  Modelos por defecto: `google/gemma-4-31B-it-turbo` (chat),
  `google/gemma-4-26B-A4B-it` (resumen), `deepseek-ai/DeepSeek-V4-Flash-0731`
  (clasificación) — ver `docs/compliance/gobernanza-ia.md` §1 para la
  justificación de cada elección.

### Added
- Documentación de cumplimiento normativo bajo `docs/compliance/`:
  DPIA, RoPA, política de retención, gobernanza de IA (ISO/IEC 42001)
  y Declaración de Aplicabilidad ISO/IEC 27001 (SoA).
- Este `CHANGELOG.md`.

- `start.sh` como punto de entrada único para levantar el backend en
  local (`uv sync` + `uvicorn --reload`), con detección de puerto
  ocupado y selección automática de uno libre. Reemplaza a los scripts
  sueltos `iniciar_servidor.sh`/`check_servidor.sh`/`ejecutar_pruebas.sh`,
  ya retirados del repo.
- Mejoras de accesibilidad WCAG en `frontend/index_santa_flat.html` y
  suite de pruebas asociada (ver `docs/accessibility.md`).

### Fixed
- `use_langchain=True` fijado por defecto: el motor CrewAI quedaba
  degradado sin detección de crisis mientras esa rama de enrutado
  existió (ver nota histórica en `docs/architecture.md`).

### Known risks (ver `docs/compliance/gobernanza-ia.md`)
- El sistema no enruta mensajes de crisis emocional grave a un
  tratamiento distinto del devocional estándar. Riesgo identificado y
  aceptado temporalmente por decisión de producto — revisión obligatoria
  antes de lanzamiento público. Sigue abierto en este release; no forma
  parte de este release documental (ver ADR-0005).
