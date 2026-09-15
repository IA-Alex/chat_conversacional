# Deployment — La Santísima Muerte

Cómo desplegar hoy, con lo que existe realmente en el repo. No describe
nada aspiracional (sin Kubernetes, sin registro de contenedores, sin
pipeline de despliegue en CI — ver "Lo que NO existe todavía" al final).

Referencia base: `docs/despliegue.md` (guía completa de servidor propio —
SSH, firewall, Caddy, systemd, backups). Este documento se enfoca en la
estrategia de despliegue en sí (cómo pasar de una versión a otra sin
downtime evitable) y en el checklist pre-deploy.

## Cómo corre el proceso hoy

Un solo ASGI app (`la_santisima_conversacional.presentation.http_api:app`)
detrás de un proxy TLS (Caddy en `docs/despliegue.md`, cualquier proxy TLS
equivalente sirve igual — nginx, Caddy, un load balancer gestionado).

```bash
# Desarrollo
uvicorn la_santisima_conversacional.presentation.http_api:app --reload

# Producción — un solo worker, systemd lo reinicia si muere (ver
# docs/despliegue.md §4 para la unit completa)
uvicorn la_santisima_conversacional.presentation.http_api:app \
    --host 127.0.0.1 --port 8000 \
    --proxy-headers --forwarded-allow-ips="127.0.0.1"
```

`--proxy-headers --forwarded-allow-ips` es obligatorio detrás de proxy:
sin esto, `request.client.host` ve la IP del proxy, no la del usuario, y
`SANTISIMA_RATE_LIMIT_REGISTRO_POR_MINUTO` (rate limit por IP en
`POST /api/v1/dispositivos`, ver `presentation/http_api.py:_exigir_tasa_registro`)
termina limitando a *todos* los usuarios como si fueran uno solo.

gunicorn con worker uvicorn (`gunicorn -k uvicorn.workers.UvicornWorker`)
es una alternativa válida para varios workers en la misma máquina, pero
ver "multi-proceso en una sola máquina" más abajo antes de sumar
`--workers > 1`: el registro de rate limit y dispositivos por defecto no
está pensado para eso.

## Estrategia de despliegue recomendada: rolling, no blue-green

**Recomendación: rolling deployment** (reemplazar la instancia en sitio —
`systemctl restart santisima` tras actualizar el código — o, en el modelo
multi-instancia, sacar una instancia de rotación, actualizarla, devolverla,
repetir con la siguiente).

**Por qué no blue-green**, explícitamente:

- Blue-green exige correr la versión vieja y la nueva en paralelo,
  sirviendo tráfico real desde ambas, y luego cortar tráfico de una a
  otra de golpe. Eso requiere que ambos entornos compartan el mismo
  estado — la misma base de datos, el mismo registro de dispositivos —
  o los dos "verdes" divergen mientras coexisten.
- Con el despliegue por defecto de este proyecto (`usar_postgres=False`),
  la persistencia es **SQLite en un archivo local del servidor**
  (`sqlite_db_path`, `dispositivos_db_path`). Dos entornos (blue y green)
  en dos máquinas/procesos distintos con sus propios archivos SQLite no
  comparten estado: un mensaje guardado en "green" mientras "blue" sigue
  sirviendo tráfico no existe para "blue", y un dispositivo revocado en
  uno no está revocado en el otro. Blue-green sobre SQLite-por-defecto
  literalmente no es blue-green — son dos servicios con datos
  divergentes.
- El rate limiter en memoria (`LimitadorTasa`, ver
  `infrastructure/rate_limit.py`) tiene el mismo problema: cada entorno
  cuenta su propio cupo, así que el límite efectivo durante el corte se
  duplica sin coordinación.
- Rolling, en cambio, nunca tiene dos versiones sirviendo tráfico real
  contra el mismo archivo SQLite **a la vez de forma sostenida** — hay
  una sola instancia activa en todo momento (single-instance) o, en el
  caso multi-instancia, todas las instancias comparten Postgres/Redis
  (ver más abajo) así que da igual cuál de ellas sirve cada request
  durante el rollout.

**Cuándo blue-green pasa a ser viable**: solo después de migrar a
`usar_postgres=True` + `usar_redis_rate_limit=True` (ver `SCALING.md`) —
con estado compartido de verdad detrás de ambos entornos, el argumento de
arriba desaparece. Hasta entonces, rolling es la única estrategia que no
arriesga divergencia de datos silenciosa.

## Camino single-instance (default)

Esto es lo que corre out-of-the-box: `usar_sqlite=True`,
`usar_postgres=False`, `usar_redis_rate_limit=False`. Un despliegue es:

1. `git pull` / desplegar el nuevo checkout.
2. `pip install -e .` (o `.[postgres,redis]` si ya usas esos extras) con
   el mismo venv que systemd referencia.
3. `systemctl restart santisima` (systemd reinicia con `Restart=on-failure`
   si el arranque falla — ver `docs/despliegue.md §4`).
4. Verificar `GET /health` y `GET /health/ready` (ver `HEALTH_CHECKS.md`).

Hay un downtime real y esperado durante el restart (un solo proceso, sin
instancia de respaldo sirviendo mientras tanto) — de segundos, no minutos,
si el arranque no falla. Es aceptable para el volumen de tráfico actual;
no es un SLA de cero downtime.

## Camino multi-instancia

Requiere primero `usar_postgres=True` y `usar_redis_rate_limit=True` (ver
README "Escalar a múltiples instancias" y `SCALING.md` — sin esto, cada
instancia tiene su propio SQLite y su propio contador de rate limit, y
"multi-instancia" produce datos divergentes e inconsistentes, no
disponibilidad extra).

Con Postgres + Redis activos:

1. Actualizar instancias una por una (o en lotes) detrás del load
   balancer: sacar de rotación, actualizar código, `systemctl restart`,
   esperar `GET /health/ready` en 200, devolver a rotación, seguir con la
   siguiente.
2. No se requiere afinidad de sesión (session affinity) en el load
   balancer: `session_id`/`device_token` son HMAC firmados y stateless
   (ver `infrastructure/security.py`) — cualquier instancia puede validar
   el token de cualquier otra siempre que compartan `session_secret` (ver
   checklist abajo). Ver `SCALING.md` para el detalle completo.

## Checklist pre-deploy

- [ ] **Secretos poblados desde el gestor, no a mano**:
      `scripts/init_secrets.sh --mode aws` (o `--mode vault`) antes de
      arrancar `uvicorn` — ver `docs/secrets-management.md`. Corre *antes*
      que el backend porque escribe el `.env` que `pydantic-settings` lee
      al importar `config.py`; si el script falla (secreto inalcanzable,
      JSON inválido, clave requerida ausente) **no** escribe nada y el
      backend arrancaría con el `.env` anterior — no relanzar el servicio
      ignorando ese fallo.
- [ ] `SANTISIMA_SESSION_SECRET` configurado e **idéntico** al de la
      versión anterior (si cambia, todo `device_token`/`session_id`
      emitido antes deja de validar — ver `TROUBLESHOOTING.md#sesión-inválida-tras-un-deploy`
      y `ROLLBACK.md`).
- [ ] `SANTISIMA_CLAVE_CIFRADO` configurado e idéntico al de la versión
      anterior (si cambia, el contenido ya cifrado con la clave vieja
      deja de descifrar).
- [ ] Ambos son **obligatorios fuera de modo debug** —
      `Settings.validar_produccion()` hace fallar el arranque si faltan.
      Verificar que `SANTISIMA_DEBUG` no esté en `true` en este entorno.
- [ ] `DEEPINFRA_API_KEY` válida (probar con `curl` contra
      `deepinfra_api_base` o esperar a `GET /health/ready` tras el
      arranque — ver `TROUBLESHOOTING.md#llm-degraded`).
- [ ] Si el deploy toca el esquema de datos: revisar `ROLLBACK.md` — no
      hay mecanismo de migraciones, así que cualquier cambio de esquema
      debe ser compatible hacia atrás (ver esa nota completa allí).
- [ ] `docs/privacidad.md` y `SANTISIMA_AVISO_PRIVACIDAD_VERSION`
      coherentes si este deploy cambia el aviso de privacidad (subir la
      versión fuerza re-consentimiento de todos los usuarios — ver
      `presentation/http_api.py:_exigir_consentimiento`).
- [ ] Backup reciente de `conversations.db` / `dispositivos.db` (o del
      Postgres, si aplica) antes de un deploy que toque persistencia.
- [ ] `systemctl daemon-reload` si se modificó la unit de systemd.
- [ ] Tras el restart: `curl -s localhost:8000/health/ready` → `200
      {"status": "ready"}`, y `curl -s localhost:8000/metrics/health` para
      confirmar `llm_adapter_status: "ok"`, `db_backend` esperado,
      `redis_connection_status` coherente con `redis_rate_limit_enabled`
      (`"disabled"` si el flag es `false`) y `ultima_purga` no vacío.
      Comparar el `session_secret_fingerprint` de esta línea de log contra
      el del deploy anterior en `journalctl` — si cambió sin haber rotado
      el secreto a propósito, todo token emitido antes dejará de validar
      (ver `_fingerprint_secreto` en `http_api.py`).
- [ ] `journalctl -u santisima -n 50` sin `logger.critical("ARRANCANDO EN
      MODO DEBUG...")` ni tracebacks de arranque.

## Lo que NO existe todavía (gap honesto)

- **`.github/workflows/ci.yml` no tiene paso de deploy.** CI corre
  `pytest` (matriz 3.10/3.11/3.12) y el job `quality` (mypy, black,
  pylint) en cada push/PR a `main` — nada más. No hay build de imagen,
  no hay artifact registry, no hay step que toque un servidor. El deploy
  descrito en `docs/despliegue.md` y aquí es manual (SSH + `git pull` +
  `systemctl restart`) hasta que alguien construya ese paso.
- No hay contenedor/imagen Docker versionada en el repo — el despliegue
  es del checkout de git directamente sobre un venv, no de un artefacto
  inmutable. Esto es relevante para `ROLLBACK.md`: "rollback" hoy es
  `git checkout <rev-anterior>` + reinstalar deps + reiniciar, no
  "apuntar a la imagen anterior".
