# La Santísima Muerte — Flow conversacional

Este proyecto define un Flow declarativo de CrewAI en
`src/la_santisima_conversacional/infrastructure/flow.json`.

## Configuración

Ambos motores (CrewAI y LangChain) usan modelos servidos por DeepInfra
(https://deepinfra.com) a través de su endpoint compatible con la API de
OpenAI. `crear_servicio` (o `Settings`/`DEEPINFRA_API_KEY` si arrancas vía
`http_api.py`) traduce la key de DeepInfra a `OPENAI_API_KEY`/
`OPENAI_API_BASE` internamente — el SDK de OpenAI que usan LangChain y
LiteLLM (CrewAI) no necesita saber que el proveedor real es otro. Expórtala
antes de ejecutar:

```bash
export DEEPINFRA_API_KEY="di-..."
```

## Instalación

El paquete base (`pip install -e .`) trae solo LangChain, para poder usar
`crear_servicio(use_langchain=True)` sin depender de CrewAI. El motor
CrewAI (`crewai install` / `crewai run`, y `crear_servicio(use_langchain=False)`,
que es el valor por defecto) requiere instalar además el extra opcional:

```bash
pip install -e ".[crewai]"
# o, con la CLI de crewai:
crewai install
```

## Ejecutar

```bash
crewai run
```

Edita el flow declarativo en `src/la_santisima_conversacional/infrastructure/flow.json`
para cambiar el comportamiento. Agrega crews reutilizables bajo
`src/la_santisima_conversacional/crews/`, tools de Python personalizadas bajo
`src/la_santisima_conversacional/tools/`, y archivos de conocimiento compartido
bajo `src/la_santisima_conversacional/knowledge/`.

## Uso programático

```python
from la_santisima_conversacional import crear_servicio

# Por defecto: CrewAI + repositorio en memoria (desarrollo).
api = crear_servicio()

# Motor LangChain (LCEL puro, sin CrewAI): misma paridad funcional
# (clasificación de intención/emoción, sliding window, memoria persistente,
# degradación validada), sin la dependencia opcional de crewai.
api = crear_servicio(use_langchain=True)

# Backend de persistencia real (SQLite) en vez de memoria:
api = crear_servicio(usar_sqlite=True, sqlite_db_path="conversations.db")

# O inyectar cualquier ConversationRepository propio:
api = crear_servicio(repositorio=mi_repositorio_custom)

respuesta = api.responder("Hola, La Santísima Muerte", session_id="creyente-123")
```

### CrewAI vs. LangChain: cuándo usar cada motor

Ambos adaptadores (`CrewAILaSantisimaAdapter` y `LangChainAdapter`) implementan
el mismo puerto `ServicioLaSantisima` y tienen **paridad funcional**:
clasificación de intención/emoción con enrutado (vacío/incompleto/válido),
sliding window de historial, resumen de memoria persistente en background,
streaming y degradación validada con fallback. La lógica de sliding window,
extracción de resumen y la política de validación/fallback vive en
`domain/conversacion.py` y `domain/degradacion.py`, compartida por ambos
motores para garantizar el mismo comportamiento sin importar cuál se elija.

- **CrewAI** (`use_langchain=False`, default): el flujo vive declarado en
  `infrastructure/flow.json`, editable sin tocar código Python. Requiere el
  extra `crewai`.
- **LangChain** (`use_langchain=True`): el flujo es código Python explícito
  (cadenas LCEL) en `infrastructure/langchain_adapter.py`. No requiere el
  extra `crewai`, por lo que trae menos dependencias transitivas
  (`litellm`, herramientas de crewai, etc.) para desplegar.

No se usa LangGraph para el enrutado: con solo 3 ramas y sin ciclos entre
turnos, if/else sobre LCEL da el mismo beneficio (tipado, testeable) sin
sumar una dependencia nueva. Si el flujo conversacional crece en
complejidad (bucles, intervención humana, ramas paralelas), reevaluar.

## Backend HTTP (la API real)

`presentation/http_api.py` expone el servicio vía FastAPI: sin esto, el
paquete solo era invocable desde otro proceso Python. Incluye lo que un
backend en producción necesita y antes faltaba: identidad de usuario final
sin login, límite de tasa, sesiones no adivinables, validación de entrada,
salud/degradación y aviso de privacidad. Ver `config.py` para todas las
variables de entorno (`SANTISIMA_*`) y `.env.example` para una plantilla
lista para copiar.

```bash
cp .env.example .env   # completar DEEPINFRA_API_KEY, SANTISIMA_SESSION_SECRET
uvicorn la_santisima_conversacional.presentation.http_api:app --reload
```

### Identidad: dispositivo (app), no login

Pensado para que Android/iOS/web se conecten sin pedirle nombre, email ni
contraseña a nadie — y sin que el cliente público lleve ningún secreto
embebido (una API key dentro de un APK/IPA se puede extraer). La app se
registra una sola vez y usa el `device_token` que recibe para todo lo
demás; el servidor puede revocar un dispositivo abusivo sin tocar a los
demás (ver `infrastructure/security.py` y `infrastructure/dispositivos.py`).

Flujo típico de un cliente:

```bash
# 1. Registrar el dispositivo (una sola vez, al primer uso de la app).
#    Sin autenticación: es el punto de entrada. Guardar device_token en
#    almacenamiento seguro del dispositivo (Keychain en iOS, Keystore en
#    Android) — es lo único que hace falta para todo lo demás.
DEVICE_TOKEN=$(curl -s -X POST localhost:8000/api/v1/dispositivos | jq -r .device_token)

# 2. Con ese device_token, obtener un session_id firmado por el servidor.
#    Un session_id inventado por el cliente, o el de otro dispositivo,
#    nunca es válido — antes cualquier string servía como session_id sin
#    ninguna verificación de propiedad.
SESSION_ID=$(curl -s -X POST localhost:8000/api/v1/sesiones \
  -H "Authorization: Bearer $DEVICE_TOKEN" | jq -r .session_id)

# 3. Enviar un mensaje con ese session_id.
curl -s -X POST localhost:8000/api/v1/mensajes \
  -H "Authorization: Bearer $DEVICE_TOKEN" -H "Content-Type: application/json" \
  -d "{\"mensaje\": \"Hola, La Santísima Muerte\", \"session_id\": \"$SESSION_ID\"}"

# 4. Streaming (SSE):
curl -N -X POST localhost:8000/api/v1/mensajes/stream \
  -H "Authorization: Bearer $DEVICE_TOKEN" -H "Content-Type: application/json" \
  -d "{\"mensaje\": \"Hola\", \"session_id\": \"$SESSION_ID\"}"
```

### Administración: API key aparte, nunca en el cliente

`SANTISIMA_API_KEYS` es solo para operar el backend (hoy: revocar un
dispositivo abusivo) — jamás se distribuye dentro de la app:

```bash
curl -s -X POST localhost:8000/admin/dispositivos/<device_id>/revocar \
  -H "Authorization: Bearer $SANTISIMA_API_KEYS"
```

Otros endpoints: `GET /health` (liveness), `GET /health/ready` (503 si el
motor de IA quedó en modo degradado — ver `esta_degradado` en los
adapters), `GET /privacidad` (resumen del aviso, contenido completo en
`docs/privacidad.md`), `POST /api/v1/sesiones/{id}/reiniciar` (borra el
historial de esa sesión).

**Retención de datos**: `scripts/purgar_retencion.py` borra mensajes más
antiguos que `SANTISIMA_RETENCION_DIAS` (90 días por defecto). Debe
programarse periódicamente (cron/systemd timer); no corre solo.

### Frontend

`GET /` sirve `frontend/index_santa_flat.html`: un HTML autocontenido
(sin build step, sin bundler) que consume la API en el mismo origen
(`127.0.0.1:8000`) para no chocar con CORS. Vive en un único archivo
explícito en vez de montarse todo el repo como estático, que expondría
`.env` y las bases SQLite (ver el comentario junto a `_RUTA_FRONTEND` en
`presentation/http_api.py`). No es un artefacto de build: es la fuente.

## Escalar a múltiples instancias

Por defecto el backend corre en **una sola instancia**: repositorio
SQLite (un archivo) y rate limiter en memoria (un diccionario Python).
Eso es correcto y suficiente mientras sea una sola instancia — no hay
nada que ganar activando Postgres/Redis antes de necesitarlos.

El día que corras **más de una instancia** del backend a la vez (detrás
de un load balancer, en Kubernetes con `replicas > 1`, etc.), esos dos
componentes dejan de ser correctos: cada instancia tendría su propio
archivo SQLite y su propio conteo de rate limit, sin coordinación entre
ellas. Activa ambos juntos en ese momento:

```bash
pip install -e ".[postgres,redis]"
```

```bash
# .env
SANTISIMA_USAR_POSTGRES=true
SANTISIMA_POSTGRES_DSN=postgresql://usuario:password@host:5432/la_santisima
SANTISIMA_USAR_REDIS_RATE_LIMIT=true
SANTISIMA_REDIS_URL=redis://host:6379/0
```

- `PostgresConversationRepository` ([infrastructure/repositories.py](src/la_santisima_conversacional/infrastructure/repositories.py)):
  mismo contrato y mismo esquema que `SQLiteConversationRepository`
  (cifrado, retención), pero en un servidor al que todas las instancias se
  conectan por red.
- `LimitadorTasaRedis` ([infrastructure/rate_limit.py](src/la_santisima_conversacional/infrastructure/rate_limit.py)):
  mismo límite, pero contado en Redis con un script Lua atómico, para que
  el límite sea correcto sin importar a cuál instancia caiga cada
  request.

Ninguna otra pieza del sistema cambia: `session_id` ya es un token firmado
(no depende de memoria de una instancia) y el resto del dominio/adapters
no sabe ni le importa qué repositorio o qué limitador está detrás.

## Desarrollo

```bash
pip install -e ".[test,lint]"
pytest                              # tests + cobertura (ver pytest.ini)
mypy --config-file=.mypy.ini src    # chequeo de tipos estático
black src tests                     # formateo (config en pyproject.toml [tool.black])
pylint --rcfile=.pylintrc src       # lint
```

Estas mismas verificaciones corren en CI en cada push/PR
(`.github/workflows/ci.yml`).

## Deployment

Guía completa de servidor propio (SSH, firewall, Caddy, systemd, backups):
`docs/despliegue.md`. Estrategia de despliegue y checklist pre-deploy:
`docs/runbooks/DEPLOYMENT.md` (incluye qué NO existe todavía — el deploy
de producción sigue siendo manual vía `git pull` + `systemctl restart`;
`Dockerfile`/`docker-compose.yml` son para desarrollo local/staging, no
para producción).

### Stack completo en local (Docker)

```bash
cp .env.example .env   # completar DEEPINFRA_API_KEY, SANTISIMA_SESSION_SECRET, SANTISIMA_CLAVE_CIFRADO
touch dispositivos.db purga_estado.json  # bind mounts: deben existir antes del primer `up`
touch deidad_1.jpeg    # idem -- o copia la imagen real (ver docs/despliegue.md) antes de este paso
docker compose up -d
curl http://localhost:8000/health
```

Quick start (servidor con systemd, ver `docs/despliegue.md` para el detalle
de cada paso):

```bash
git clone <repo> && cd chat_conversacional
scripts/init_secrets.sh --mode aws   # o --mode vault; ver --help
pip install -e ".[postgres,redis]"
systemctl restart santisima
```

Purga de retención automática (systemd timer, cron, o `docker-compose.purga.yml`
si el host no tiene ninguno de los dos): `docs/despliegue.md` §7.

Monitoreo: `monitoring/README.md`. Troubleshooting: `docs/runbooks/TROUBLESHOOTING.md`.
