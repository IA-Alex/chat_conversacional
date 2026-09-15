# ADR-0001: Dos motores de IA intercambiables (CrewAI y LangChain)

**Estado:** Aceptado.
**Fecha:** previa a esta iteración de trabajo (decisión ya presente en el código base).

## Contexto

El sistema necesita generar respuestas conversacionales, clasificar
intención/emoción y mantener memoria persistente. CrewAI ofrece un DSL
declarativo (`flow.json`) editable sin tocar Python; LangChain (LCEL) es
más explícito y no depende de un framework adicional.

## Decisión

Implementar ambos motores detrás de un mismo puerto (`ServicioLaSantisima`,
Dependency Inversion Principle), con paridad funcional exacta: sliding
window, memoria persistente, clasificación con enrutado, degradación con
fallback. `crear_servicio(use_langchain: bool)` elige cuál construir.

La lógica de negocio compartida (sliding window, extracción de resumen,
política de degradación, prompt de fallback) vive en `domain/` e
`infrastructure/prompts.py`, reutilizada por ambos adaptadores — no
duplicada.

## Consecuencias

- **Positivo:** el paquete base (`pip install -e .`) no obliga a instalar
  CrewAI (dependencia pesada, extra opcional) para poder correr con
  LangChain.
- **Positivo:** un fallo o cambio de comportamiento en un motor no arrastra
  al otro.
- **Negativo (costo aceptado):** toda lógica de prompt/enrutado debe
  mantenerse en paralelo en dos formatos distintos (`flow.json` declarativo
  vs. cadenas LCEL en Python) — ver la brecha RNF-006 en
  [rtm.md](../rtm.md): no hay un test parametrizado único que corra ambos
  motores con las mismas aserciones, así que pueden divergir sin que
  ningún test lo note hasta que alguien lo prueba manualmente.
- Cualquier control de seguridad/privacidad nuevo en el prompt (ver
  [ADR-0005](0005-personificacion-sin-aviso-de-ia-en-el-flujo.md)) debe
  implementarse en los tres lugares: `flow.json`, `langchain_adapter.py` y
  `infrastructure/prompts.py` (fallback compartido).
