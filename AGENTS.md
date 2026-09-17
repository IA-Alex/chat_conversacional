# AGENTS.md — Convenciones para agentes de código en este repo

## Qué es este proyecto

Backend Python (FastAPI) de un chat conversacional con dos motores de IA
intercambiables (CrewAI y LangChain, mismo puerto `ServicioLaSantisima`),
servido con DeepInfra. Ver `README.md` para la vista completa y
`docs/architecture.md` para el diseño de capas.

## Estructura (Clean Architecture)

```
src/la_santisima_conversacional/
  domain/          # Entidades y reglas de negocio, sin dependencias de framework
  application/     # Casos de uso (coordina domain + infrastructure)
  infrastructure/  # Adapters concretos: CrewAI, LangChain, SQLite/Postgres, Redis
  presentation/    # FastAPI (http_api.py) y el caso de uso invocado por API
```

Regla de dependencia: `domain` no importa nada de `infrastructure` ni
`presentation`. Lógica compartida entre los dos motores (sliding window,
resumen, política de fallback) vive en `domain/`, nunca duplicada dentro
de un adapter.

## Comandos

```bash
pip install -e ".[test,lint]"
pytest                              # tests + cobertura (pytest.ini)
mypy --config-file=.mypy.ini src    # tipos
black src tests                     # formateo
pylint --rcfile=.pylintrc src       # lint
pre-commit run --all-files          # hooks locales (large files, trailing whitespace, etc.)
```

Estas mismas verificaciones corren en CI (`.github/workflows/ci.yml`) en
cada push/PR — un cambio que no pasa localmente tampoco pasará ahí.

## Convenciones que este repo exige

- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`,
  `test:`, `chore:`, `style:`, `perf:`, `build:`, `ci:`, `revert:`),
  validado en CI (`commit-lint` job). El mensaje explica el *por qué*, no
  solo el qué — ver el historial de `git log` para el estilo esperado.
- **Decisiones de arquitectura o de producto con consecuencias**: un ADR
  nuevo bajo `docs/adr/`, siguiendo el formato de los existentes
  (Contexto / Decisión / Consecuencias, incluyendo riesgos aceptados
  explícitamente si los hay — ver `docs/adr/0005-*.md` como referencia).
- **Archivos que no son fuente** (resultados de una corrida puntual,
  entornos virtuales, worktrees de otras herramientas) van a
  `.gitignore`, nunca se versionan "porque ya estaba así". `git status`
  antes de cada commit para detectar esto.
- **Ningún endpoint nuevo** que toque datos del creyente sin revisar
  `docs/compliance/` (DPIA, RoPA, gobernanza de IA) — el consentimiento y
  la retención son parte del contrato del backend, no un añadido opcional.

## Modo especializado: auditoría UX/UI del frontend

Para tareas específicas de revisión visual/accesibilidad sobre
`frontend/index_santa_flat.html` (el único archivo de frontend, sin
build step — ver `README.md` §Frontend), usar este protocolo:

**Rol**: Diseñador UX/UI Lead con perfil Fullstack Frontend, auditando
inconsistencias visuales, desbalances de diseño y fallos de integración
con el backend.

**Estándares obligatorios**:
- Espaciado en múltiplos de 4px/8px, alineación y jerarquía tipográfica.
- WCAG 2.1/2.2: contraste mínimo 4.5:1 (texto normal), 3:1 (UI/texto
  grande); tokens semánticos consistentes (superficies, estados de
  éxito/advertencia/error); regla 60-30-10.
- Ciclo de vida completo de peticiones (`idle`/`loading`/`success`/
  `error`/`empty`), validación defensiva ante datos nulos o payloads
  mutados, traducción de errores HTTP a mensajes accionables.

**Formato de cada hallazgo**: Diagnóstico (categoría, elemento afectado,
causa técnica) → Criterio infringido (regla exacta rota) → Código
reparado (diff o snippet completo listo para aplicar). Tono técnico y
directo, sin comentarios introductorios ni cierres genéricos.

Precedente: este protocolo ya se usó para la ronda de accesibilidad
registrada en `docs/accessibility.md` y el commit `b8b4396`.
