# Matriz de Trazabilidad de Requisitos (RTM)

**Referencia normativa:** ISO/IEC/IEEE 29148:2018 (trazabilidad
bidireccional: stakeholder → requisito → diseño → prueba).
**Fuente de requisitos:** [srs.md](srs.md).
**Estado:** Verificado contra la suite real el 2026-09-14
(`python -m pytest -q` → 188 passed, 8 skipped). Una fila cuya columna
"Test" queda vacía es un requisito **no verificado**, aunque el código lo
implemente — es una brecha real, no un descuido de este documento.

| Requisito | Módulo/diseño | Test(s) que lo verifican | Estado |
|---|---|---|---|
| RF-001 | `http_api.py: registrar_dispositivo` | `TestRegistroDeDispositivo::test_registrar_dispositivo_no_requiere_auth`, `test_cada_registro_da_un_dispositivo_distinto` | ✅ |
| RF-002 | `verificar_dispositivo` | `test_device_token_fabricado_es_rechazado`, `test_device_token_de_otra_instalacion_del_servidor_es_rechazado` | ✅ |
| RF-003 | `RegistroDispositivos.revocar` | `TestAdministracion::test_revocar_dispositivo_con_api_key_admin_lo_bloquea`, `test_dispositivos.py::test_revocar_bloquea_el_dispositivo` | ✅ |
| RF-004 | `aceptar_consentimiento` | `TestConsentimiento::test_mensaje_tras_aceptar_consentimiento_funciona`, `test_dispositivos.py::test_registrar_consentimiento_queda_disponible` | ✅ |
| RF-005 | `_exigir_consentimiento` | `test_mensaje_sin_consentimiento_devuelve_403`, `test_aceptar_version_distinta_a_la_vigente_no_habilita_el_envio` | ✅ |
| RF-010 | `crear_sesion` / `emitir_session_id` | `test_security.py::test_session_id_puede_atarse_a_un_device_id` | ✅ |
| RF-011 | `_validar_propiedad_sesion` | `TestPropiedadDeSesion::test_mensaje_con_session_id_ajeno_devuelve_404`, `test_session_id_de_un_dispositivo_no_sirve_para_otro` | ✅ |
| RF-012 | `generar_respuesta` (flow.json) / `_chain_principal` | `test_langchain_adapter.py::test_mensaje_valido_usa_cadena_principal`; equivalente CrewAI en `test_flow_integration.py` | ✅ |
| RF-013 | `enviar_mensaje_stream` / `responder_mensaje_stream` | `test_langchain_adapter.py::test_streaming_mensaje_valido_actualiza_memoria_al_terminar` | ✅ |
| RF-014 | `detectar_intencion` / `enrutar_por_intencion` | `test_langchain_adapter.py::test_mensaje_vacio_usa_respuesta_corta_y_no_actualiza_memoria`, `test_mensaje_incompleto_usa_respuesta_corta`; `test_flow_structure.py::test_clasificacion_de_intencion_consistente` | ✅ |
| RF-015 | `extraer_resumen_persistente` / `actualizar_memoria` | `test_langchain_adapter.py::test_resumen_persistente_se_extrae_e_inyecta`, `test_memoria_se_persiste_via_callback`; `test_caso_de_uso.py::test_ejecutar_persiste_resumen_via_callback` | ✅ |
| RF-016 | `aplicar_sliding_window` | `test_langchain_adapter.py::test_historial_se_recorta_a_la_ventana` | ✅ |
| RF-017 | `reiniciar_sesion` | `TestPropiedadDeSesion::test_reiniciar_sesion_ajena_devuelve_404`, `test_reiniciar_sesion_propia_vacia_el_historial` | ✅ |
| RF-018 | `validar_o_usar_fallback` / `_fallback_responder` | `test_degradacion.py::test_fallo_flow_crewai_dispara_fallback`, `test_streaming_fallback_cuando_flow_falla`; `test_langchain_adapter.py::test_error_al_generar_dispara_fallback` | ✅ |
| RF-020 | `GET /privacidad` | `TestPrivacidad::test_aviso_privacidad_no_requiere_auth` | ✅ |
| RF-021 | `GET /health`, `GET /health/ready` | `TestSalud::test_health_no_requiere_auth`, `test_readiness_503_cuando_motor_degradado` | ✅ |
| RF-022 | `purgar_expirados` | `test_repository.py::test_purgar_expirados_borra_solo_mensajes_viejos` (SQLite), `test_repository_postgres.py::test_purgar_expirados_borra_solo_mensajes_viejos` (Postgres, requiere servidor real — se salta si no hay uno disponible) | ✅ |
| RNF-001 | Cifrado Fernet en `_cifrar`/`_descifrar` | `test_repository.py::test_cifrado_en_reposo` (SQLite), `test_repository_postgres.py::test_cifrado_en_reposo` (Postgres) | ✅ |
| RNF-002 | `LimitadorTasa` por `device_id` | `TestRateLimit::test_dispositivos_distintos_no_comparten_cupo`; `test_rate_limit.py::test_claves_distintas_no_comparten_cupo` | ✅ |
| RNF-003 | `llm_timeout_segundos`/`llm_max_reintentos` pasados a `ChatOpenAI` | Sin test dedicado — se configura pero no se verifica que el timeout real se respete (probarlo requeriría un servidor lento simulado) | ⚠️ No verificado |
| RNF-004 | `Settings` fail-fast, `validar_produccion` | `test_config.py::test_falla_sin_deepinfra_api_key`, `test_validar_produccion_exige_session_secret_fuera_de_debug` | ✅ |
| RNF-005 | `usar_postgres`/`usar_redis_rate_limit` | `test_config.py::test_usar_postgres_sin_dsn_falla_al_construir`; comportamiento bajo carga real no cubierto por tests (requiere infraestructura) | ⚠️ Parcial |
| RNF-006 | `ServicioLaSantisima` (puerto) | Paridad verificada indirectamente: mismos escenarios (`test_langchain_adapter.py` vs `test_flow_integration.py`) cubren ambos motores por separado — no hay un test parametrizado único que corra ambos con las mismas aserciones | ⚠️ Parcial |
| RNF-007 | Extras opcionales en `pyproject.toml`, mock en `conftest.py` | Toda la suite corre sin el extra `crewai` instalado (evidencia empírica: esta suite corrió así) | ✅ |
| RNF-008 | Puente de credenciales en `crear_servicio` | `test_crear_servicio.py::test_deepinfra_api_key_puebla_openai_api_key_en_el_entorno`, `test_sin_deepinfra_api_key_no_toca_el_entorno` | ✅ |

## Brechas abiertas (para priorizar, no para ignorar)

Al cierre de esta iteración (2026-09-14) quedan dos brechas reales, ambas
de mayor costo que las cuatro originales — las otras dos (RF-017,
RNF-008) se cerraron con tests nuevos en la misma sesión de trabajo:

1. **RNF-003** — el timeout/reintentos configurados nunca se ejercitan
   contra un LLM lento simulado.
2. **RNF-006** — no hay un test parametrizado que corra el mismo escenario
   contra `CrewAIAdapter` y `LangChainAdapter` con exactamente las mismas
   aserciones (hoy son suites separadas que prueban lo mismo por
   duplicado, con riesgo de que diverjan sin que ningún test lo note).

Estas dos brechas quedan también reflejadas en [test-plan.md](test-plan.md) §5.
