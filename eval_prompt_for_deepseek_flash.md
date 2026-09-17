# Evaluación de Sonnet 5 — La Santísima Muerte (Chat Conversacional)

## Rol
Eres un evaluador riguroso de respuestas de modelo de IA. Tu tarea es evaluar las respuestas de Claude Sonnet 5 sobre un backend de chat conversacional basado en CrewAI/LangChain contra estándares de corrección, claridad y seguridad.

## Contexto del repositorio
Repositorio: `chat_conversacional` en `/home/alonso/CHAT/`
- Backend: Python (FastAPI + CrewAI/LangChain)
- Motor de IA: DeepInfra (endpoint OpenAI-compatible)
- Modelo default: `google/gemma-4-31B-it`
- Stack: SQLite (conversations), Redis (rate limit), Postgres (escala), FastAPI
- Punto de entrada: `./start.sh` (script nuevo que automatiza levantamiento)
- Identidad: Token por dispositivo (no login), sesiones firmadas HMAC
- Seguridad: Historial cifrado en reposo (Fernet)

## Dataset de preguntas (15 preguntas)

Para cada pregunta, Sonnet 5 proporcionó una respuesta. Evalúa cada respuesta con los criterios que siguen.

### Pregunta 1: Startup
**Q:** ¿Cuál es el comando para levantar el backend en local sin fricción?
**Respuesta de Sonnet:**
```
./start.sh
```

### Pregunta 2: Puerto ocupado
**Q:** ¿Qué pasa si el puerto 8000 ya está ocupado cuando corro `./start.sh`?
**Respuesta de Sonnet:**
```
El script detecta automáticamente que el puerto 8000 está ocupado y elige el siguiente libre (8001, 8002, etc.) sin que tengas que hacer nada. Imprime un aviso claro:
⚠️  Puerto 8000 ocupado, usando 8001 en su lugar
Y arranca en ese puerto sin fricción.
```

### Pregunta 3: Configuración previa
**Q:** ¿Qué necesito en `.env` antes de poder levantar el backend por primera vez?
**Respuesta de Sonnet:**
```
Mínimo tres cosas:
1. DEEPINFRA_API_KEY (tu clave real de DeepInfra)
2. SANTISIMA_SESSION_SECRET (secreto HMAC para firmar sesiones, se genera con: python -c "import secrets; print(secrets.token_urlsafe(32))")
3. SANTISIMA_CLAVE_CIFRADO (clave Fernet para cifrar historial en reposo, se genera con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

Si faltan, el script avisa exactamente cuáles completar y no arranca hasta que lo hagas.
```

### Pregunta 4: Variable PORT
**Q:** ¿Cómo arranco el backend en un puerto específico diferente a 8000?
**Respuesta de Sonnet:**
```
PORT=9000 ./start.sh
```

### Pregunta 5: Stack Docker
**Q:** ¿Cómo levanto el stack completo (backend + Postgres + Redis + Prometheus + Grafana)?
**Respuesta de Sonnet:**
```
./start.sh --docker

Esto levanta todo con docker-compose.yml: backend en :8000, Postgres en :5432, Redis en :6379, Prometheus en :9090, Grafana en :3000.
```

### Pregunta 6: Motor de IA
**Q:** ¿Cuál es el motor de IA que usa por defecto: CrewAI o LangChain?
**Respuesta de Sonnet:**
```
LangChain (use_langchain=True en config.py:54). CrewAI es opcional (extra [crewai] en pyproject.toml).
```

### Pregunta 7: Modelo de chat
**Q:** ¿Cuál es el modelo que usa para responder al usuario final ("creyente")?
**Respuesta de Sonnet:**
```
google/gemma-4-31B-it vía DeepInfra (servido como openai/google/gemma-4-31B-it-turbo en config.py:55).
```

### Pregunta 8: Cambiar modelo
**Q:** ¿Puedo usar otro modelo de DeepInfra en lugar de Gemma? ¿Cómo?
**Respuesta de Sonnet:**
```
Sí. Edita config.py línea 55 (modelo_chat) con el nombre exacto del modelo en DeepInfra.
Ejemplo: "openai/meta-llama/Llama-3.3-70B-Instruct"
No toca ningún código lógico, solo la config.
```

### Pregunta 9: Historiál cifrado
**Q:** ¿Está el historial de conversaciones cifrado en disco?
**Respuesta de Sonnet:**
```
Sí, siempre que SANTISIMA_CLAVE_CIFRADO esté configurada.
Usa Fernet (cryptography library).
Cifra/descifra en infrastructure/repositories.py (_encrypt_message, _decrypt_message).
```

### Pregunta 10: Rate limiting
**Q:** ¿Cómo funciona el rate limit?
**Respuesta de Sonnet:**
```
Por defecto: 20 mensajes por minuto por dispositivo (SANTISIMA_RATE_LIMIT_POR_MINUTO en config.py).
En memoria para una sola instancia.
Si escalas a múltiples instancias: Redis (infrastructure/rate_limit.py, LimitadorTasaRedis).
```

### Pregunta 11: Identidad de usuario
**Q:** ¿Cómo se identifica a un usuario final? ¿Se pide email o contraseña?
**Respuesta de Sonnet:**
```
No. Se registra por dispositivo, no por login.
1. POST /api/v1/dispositivos → obtiene device_token (una sola vez)
2. POST /api/v1/sesiones con Authorization: Bearer <device_token> → obtiene session_id
3. POST /api/v1/mensajes con ese session_id → envía mensaje
El device_token es lo único que se guarda en el cliente (Keychain en iOS, Keystore en Android).
```

### Pregunta 12: Retención de datos
**Q:** ¿Cuánto tiempo se guardan las conversaciones?
**Respuesta de Sonnet:**
```
90 días por defecto (SANTISIMA_RETENCION_DIAS en config.py).
Borradas automáticamente por scripts/purgar_retencion.py (debe programarse como cron/systemd timer).
No corre solo, hay que ejecutarlo explícitamente.
```

### Pregunta 13: Escalabilidad
**Q:** ¿En qué momento necesito activar Postgres y Redis?
**Respuesta de Sonnet:**
```
Cuando corras más de una instancia del backend a la vez (load balancer, Kubernetes replicas > 1).
Por defecto usa SQLite (un archivo) y rate limit en memoria (diccionario Python) — suficiente para una sola instancia.
Activa ambos juntos: pip install -e ".[postgres,redis]" y config en .env (SANTISIMA_USAR_POSTGRES, SANTISIMA_USAR_REDIS_RATE_LIMIT).
```

### Pregunta 14: Health check
**Q:** ¿Cuál es el endpoint para verificar que el backend está vivo?
**Respuesta de Sonnet:**
```
GET /health → {"status":"ok"}
GET /health/ready → 200 si listo, 503 si en modo degradado.
```

### Pregunta 15: Variables de entorno exportadas
**Q:** Si exporto DEEPINFRA_API_KEY en la terminal antes de ejecutar, ¿tiene prioridad sobre el valor en `.env`?
**Respuesta de Sonnet:**
```
Sí. pydantic-settings da prioridad al entorno (env vars) sobre el .env.
Así que:
export DEEPINFRA_API_KEY="tu_key_real"
./start.sh
Funciona sin editar .env, y la key exportada se usa siempre.
```

---

## Criterios de evaluación

Para cada respuesta, califica en escala 1-5:

| Criterio | Descripción |
|----------|-------------|
| **Corrección** | ¿Es técnicamente correcta? ¿Sin errores factuales o hallucinations? |
| **Completitud** | ¿Responde la pregunta de punta a punta o le falta contexto/pasos? |
| **Claridad** | ¿Es comprensible para alguien que no conoce el repo? ¿Sin jerga sin explicar? |
| **Ejecutabilidad** | Si alguien sigue la respuesta al pie, ¿funciona sin fricción o hay sorpresas? |
| **Seguridad** | ¿Evita exponer secretos? ¿Recomienda prácticas seguras? |

Escala: 5=excelente, 4=bueno, 3=aceptable con salvedades, 2=serios problemas, 1=incorrecto/peligroso.

---

## Formato de reporte esperado

Genera un reporte con:

1. **Tabla de puntuaciones** (pregunta | corrección | completitud | claridad | ejecutabilidad | seguridad | score_promedio)
2. **Hallazgos críticos** — errores que harían fallar a un usuario
3. **Salvedades** — imprecisiones menores que no rompen la tarea pero podrían confundir
4. **Fortalezas** — qué hizo bien Sonnet
5. **Recomendaciones** — cómo mejorar las respuestas débiles
6. **Score general** (0-100) y veredicto (Apto/Condicional/No apto)

---

## Instrucciones finales

- Sé riguroso pero justo: el criterio es que un usuario pueda seguir las respuestas sin fricción ni sorpresas de seguridad.
- Si una respuesta es parcialmente correcta pero incompleta, explica qué falta.
- Si hay una interpretación ambigua, señalalo (la pregunta era poco clara, o la respuesta asume demasiado).
- No penalices por estilo (brevedad vs. detalle) a menos que afecte claridad/ejecutabilidad.

Procede con la evaluación.
