# ADR-0003: Migración de proveedor de IA — OpenAI → DeepInfra

**Estado:** Aceptado.
**Fecha:** 2026-09-14.

## Contexto

El código llamaba directo a la API de OpenAI (`OPENAI_API_KEY`, modelos
`openai/gpt-4o` / `openai/gpt-4o-mini`). El proveedor oficial del proyecto
es DeepInfra (https://deepinfra.com), que sirve modelos de terceros
(Google Gemma, DeepSeek, etc.) a través de un endpoint compatible con la
API de OpenAI.

Se evaluaron modelos priorizando calidad de razonamiento/multilingüe para
la voz principal, y economía para tareas de bajo riesgo (clasificación) —
ver [docs/compliance/gobernanza-ia.md](../compliance/gobernanza-ia.md) §1
para el detalle de la evaluación de cada modelo.

## Decisión

- `modelo_chat`: `google/gemma-4-31B-it-turbo` — variante optimizada para
  latencia del modelo flagship de Gemma 4 (MMLU Pro 85.2%, 140+ idiomas).
- `modelo_resumen`: `google/gemma-4-26B-A4B-it` — MoE, corre a velocidad
  cercana a un modelo denso de 4B con más conocimiento accesible.
- `modelo_clasificador`: `deepseek-ai/DeepSeek-V4-Flash-0731` — el más
  económico evaluado, para una tarea de bajo riesgo si falla ocasionalmente.

**Mecanismo de la migración:** en vez de reescribir `CrewAIAdapter` y
`LangChainAdapter` (que usan el SDK de OpenAI/LiteLLM internamente),
`crear_servicio` traduce `deepinfra_api_key`/`deepinfra_api_base` a
`OPENAI_API_KEY`/`OPENAI_API_BASE`/`OPENAI_BASE_URL` en el proceso, en un
único punto de composición, antes de construir cualquier adaptador. Los
nombres de modelo mantienen el prefijo `"openai/"` (convención LiteLLM)
seguido del id real en DeepInfra (p. ej.
`"openai/google/gemma-4-31B-it-turbo"`).

## Consecuencias

- **Positivo:** cero cambios dentro de `CrewAIAdapter`/`LangChainAdapter`
  — ninguno de los dos necesita saber que el proveedor real cambió.
- **Positivo:** cambiar de proveedor de nuevo en el futuro (otro endpoint
  compatible con OpenAI) requiere tocar solo `crear_servicio`/`Settings`.
- **Negativo (costo aceptado):** el nombre de variable de entorno que el
  operador configura (`DEEPINFRA_API_KEY`) no coincide con el que el SDK
  termina viendo (`OPENAI_API_KEY`) — puede confundir a quien no conozca
  este ADR. Mitigado documentando el puente explícitamente en
  `config.py`, `__init__.py` y `README.md`.
- Verificado con test dedicado
  (`test_crear_servicio.py::test_deepinfra_api_key_puebla_openai_api_key_en_el_entorno`)
  — ver RNF-008 en [rtm.md](../rtm.md).
- Documentos de cumplimiento (`RoPA.md`, `DPIA.md`, `soa-iso27001.md`)
  actualizados para nombrar a DeepInfra como subprocesador, no OpenAI.
