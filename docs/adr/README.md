# Registros de Decisiones de Arquitectura (ADR)

**Referencia normativa:** ISO/IEC/IEEE 15288:2015 (gestión de decisiones
técnicas), formato Michael Nygard (estándar de facto de la industria, sin
número ISO propio).

Cada ADR documenta una decisión ya tomada y presente en el código — no
son propuestas. Se numeran secuencialmente y no se editan retroactivamente
para "corregir" una decisión pasada: si una decisión cambia, se escribe un
ADR nuevo que la reemplaza y enlaza al anterior.

| ADR | Título | Estado |
|---|---|---|
| [0001](0001-dos-motores-intercambiables.md) | Dos motores de IA intercambiables (CrewAI y LangChain) | Aceptado |
| [0002](0002-identidad-por-dispositivo.md) | Identidad por dispositivo, sin cuentas ni login | Aceptado |
| [0003](0003-migracion-deepinfra.md) | Migración de proveedor de IA: OpenAI → DeepInfra | Aceptado |
| [0004](0004-consentimiento-explicito-por-version.md) | Consentimiento explícito versionado antes del primer mensaje | Aceptado |
| [0005](0005-personificacion-sin-aviso-de-ia-en-el-flujo.md) | Personificación en primera persona sin aviso de IA dentro del flujo conversacional | Aceptado, con riesgo diferido registrado |
