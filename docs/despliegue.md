# Despliegue en un servidor propio (single-server)

Guía para desplegar el backend + frontend en un servidor rentado (VPS),
con frontend y API en el mismo dominio/origen (ver `docs/architecture.md`
para el diseño de la app en sí). Objetivo: máxima seguridad razonable sin
introducir fricción para el usuario final — nada de lo aquí descrito es
visible desde `/index.html`.

## 1. Servidor base

- Distribución recomendada: Debian/Ubuntu LTS (actualizaciones de
  seguridad largas, mínima superficie).
- Usuario no-root para correr todo: nunca ejecutar la app ni Caddy como
  `root`.
  ```bash
  adduser --disabled-password --gecos "" santisima
  ```
- Actualizaciones de seguridad automáticas (`unattended-upgrades` en
  Debian/Ubuntu) — un servidor sin parchear es el vector de entrada más
  común, muy por delante de cualquier bug de la propia app.
  ```bash
  apt install unattended-upgrades
  dpkg-reconfigure -plow unattended-upgrades
  ```

## 2. SSH

- Solo autenticación por clave pública, nunca contraseña:
  `PasswordAuthentication no` en `/etc/ssh/sshd_config`.
- `PermitRootLogin no`.
- Opcional pero recomendado: mover el puerto de 22 a otro (reduce ruido de
  bots, no es una defensa real por sí sola) y/o `fail2ban` para bloquear
  intentos repetidos.

## 3. Firewall

Solo tres puertos abiertos al exterior: SSH, HTTP (para el reto ACME de
Let's Encrypt) y HTTPS. El backend (`:8000` por defecto de uvicorn) **no
se expone nunca directamente** — solo escucha en `localhost`, Caddy es el
único que le habla.

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

## 4. La app como servicio systemd

Corre bajo el usuario `santisima`, reinicia sola si el proceso muere, y
arranca al boot del servidor.

`/etc/systemd/system/santisima.service`:
```ini
[Unit]
Description=La Santísima Muerte — backend conversacional
After=network.target

[Service]
Type=simple
User=santisima
Group=santisima
WorkingDirectory=/home/santisima/chat_conversacional
EnvironmentFile=/home/santisima/chat_conversacional/.env
ExecStart=/home/santisima/chat_conversacional/.venv/bin/uvicorn \
    la_santisima_conversacional.presentation.http_api:app \
    --host 127.0.0.1 --port 8000 \
    --proxy-headers --forwarded-allow-ips="127.0.0.1"
Restart=on-failure
RestartSec=5

# Hardening: el proceso no necesita nada de esto, así que se le niega
# explícitamente (defensa en profundidad si algún día hay una RCE en una
# dependencia).
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/santisima/chat_conversacional
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

`--proxy-headers --forwarded-allow-ips="127.0.0.1"` es lo que hace que
`request.client.host` refleje la IP real del usuario (no la de Caddy) —
necesario para que el rate limit de registro de dispositivo
(`_exigir_tasa_registro`, ver `presentation/http_api.py`) limite por
usuario real y no por la IP del proxy compartida entre todos.

`.env` con permisos restrictivos (contiene `DEEPINFRA_API_KEY`,
`SANTISIMA_SESSION_SECRET`, `SANTISIMA_CLAVE_CIFRADO`):
```bash
chmod 600 .env
chown santisima:santisima .env
```

```bash
systemctl daemon-reload
systemctl enable --now santisima
```

## 5. Reverse proxy: Caddy (TLS automático)

`/etc/caddy/Caddyfile`:
```
tudominio.com {
    encode gzip

    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /health* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /privacidad {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        root * /home/santisima/chat_conversacional/frontend
        file_server
    }
}
```

Caddy obtiene y renueva el certificado TLS solo (Let's Encrypt), añade
HSTS automáticamente al servir HTTPS, y reenvía `X-Forwarded-For` por
defecto. Frontend y API quedan en el mismo origen (`tudominio.com`), así
que **no hace falta configurar CORS en absoluto** —
`SANTISIMA_CORS_ORIGINS` puede quedar vacío.

## 6. Variables de entorno de producción — checklist

Ver `.env.example` para la lista completa; lo específico de producción:

- `SANTISIMA_DEBUG=false` (u omitido — el default ya es `false`). Nunca
  `true` en este servidor.
- `SANTISIMA_SESSION_SECRET` generado con
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- `SANTISIMA_CLAVE_CIFRADO` generada con
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  — sin esto, el contenido conversacional se guarda en texto plano.
- `SANTISIMA_CORS_ORIGINS=` (vacío: mismo origen, no hace falta).
- `SANTISIMA_API_KEYS=` con al menos una key generada igual que el
  session secret, si vas a usar `/admin/dispositivos/{id}/revocar`.
- `SANTISIMA_RATE_LIMIT_REGISTRO_POR_MINUTO` — el default (10) ya es
  razonable; solo bajarlo si ves abuso real en logs.

## 7. Datos: backups y retención

- `dispositivos.db` y `conversations.db` viven en
  `WorkingDirectory` (fuera del repo git — ver hallazgo H-02 del audit:
  confirmar que `*.db` está en `.gitignore` antes de cualquier `git push`
  desde este servidor).
- Retención automática: timer systemd diario que dispara
  `scripts/purgar_retencion.py` — mismo mecanismo de servicio/hardening
  que `santisima.service` (§4), en vez de un cron aparte sin logging
  centralizado ni reintento tras un reinicio del servidor.

  Unidades de ejemplo: `scripts/systemd/santisima-purga-retencion.service`
  y `scripts/systemd/santisima-purga-retencion.timer`.

  ```bash
  cp scripts/systemd/santisima-purga-retencion.service /etc/systemd/system/
  cp scripts/systemd/santisima-purga-retencion.timer /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now santisima-purga-retencion.timer
  ```

  Verificar que quedó programado y ver el resultado de la última corrida:
  ```bash
  systemctl list-timers santisima-purga-retencion.timer
  journalctl -u santisima-purga-retencion.service
  ```

  El timer corre a las 03:00 hora del servidor, con `Persistent=true`
  (si el servidor estuvo apagado a esa hora, purga en cuanto arranca en
  vez de saltarse el día) — ver comentarios en el propio archivo `.timer`
  para el detalle. Esto cierra el pendiente #2 de
  `docs/compliance/politica-retencion.md` §4: antes el script existía
  pero nada garantizaba que corriera de forma programada.

  **Alternativas al timer** (mismo script, mismo resultado en
  `purga_estado.json` — lo que se monitorea es el archivo, no el
  scheduler, así que la alerta `SantisimaPurgaRetencionAtrasada` funciona
  igual con cualquiera de las tres):

  - **Host sin systemd** (Alpine, contenedor, macOS): cron diario sobre el
    wrapper `scripts/retencion_cron.sh`, que resuelve el intérprete del
    venv y deja una marca de tiempo propia en el log (permite distinguir
    "el cron no disparó" de "disparó y la purga falló").

    ```bash
    0 3 * * * /ruta/al/repo/scripts/retencion_cron.sh >> /var/log/santisima-purga.log 2>&1
    ```

  - **Despliegue en contenedor**: `docker-compose.purga.yml`, que monta el
    repo en una imagen `python:3.12-slim` (no hay Dockerfile propio en este
    proyecto) y corre el script con `--rm`. Sirve tanto para una corrida
    puntual como invocado desde el cron del host.

    ```bash
    docker compose -f docker-compose.purga.yml run --rm purga-retencion
    ```

  - Cualquiera de las tres opciones puede confirmarse consultando
    `GET /metrics/health` → `ultima_purga` (ver
    `docs/runbooks/HEALTH_CHECKS.md`).
- Backup: si vas a respaldar los `.db`, hazlo cifrado en destino (el
  contenido de `messages` ya viaja cifrado con Fernet si configuraste
  `SANTISIMA_CLAVE_CIFRADO`, pero el backup en sí — snapshot del VPS,
  `rsync` a otro host — debe tratarse con la misma sensibilidad que la
  base original).

## 8. Monitoreo mínimo

- `GET /health` (liveness) y `GET /health/ready` (readiness — refleja si
  el motor de IA cayó a modo degradado) ya existen en la API. Un check
  externo simple (cron + curl, o UptimeRobot/similar) contra ambos basta
  para enterarte de una caída sin depender de que un usuario se queje.
- Vigilar logs por el mensaje `logger.critical("ARRANCANDO EN MODO
  DEBUG...")` — si alguna vez aparece en este servidor, es una
  configuración incorrecta que debe corregirse de inmediato (ver hallazgo
  H-01 del audit de seguridad).

## Resumen: qué hace esto invisible para el usuario

Nada de lo anterior agrega pasos, redirecciones ni pantallas — el usuario
sigue entrando a `https://tudominio.com` y chateando de inmediato. Todo el
hardening ocurre por debajo: quién puede tocar el servidor (SSH+firewall),
cómo se sirve TLS (Caddy, automático), y cómo se guardan/protegen sus
datos (systemd hardening, `.env` con permisos, retención automática).
