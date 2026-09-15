# Gestión de secretos en producción

Cómo poblar el `.env` que lee `pydantic-settings` (`Settings`,
`env_prefix="SANTISIMA_"`, `env_file=".env"` — ver
`src/la_santisima_conversacional/config.py`) en un entorno de producción,
sin escribir secretos a mano en el servidor.

El mecanismo es `scripts/init_secrets.sh`: un script operacional (no toca
`config.py` ni el resto del código) que lee un secreto desde AWS Secrets
Manager o HashiCorp Vault y escribe `.env` con permisos `600`. Nunca
imprime valores de secretos a stdout/stderr/logs — solo nombres de claves
y conteos.

Ver también `docs/runbooks/DEPLOYMENT.md` (estrategia de despliegue y
checklist pre-deploy) y `docs/despliegue.md` (guía de servidor propio:
SSH, Caddy, systemd, backups).

## Modos

```
scripts/init_secrets.sh --mode local   # default: dev local, no toca secretos reales
scripts/init_secrets.sh --mode aws     # producción vía AWS Secrets Manager
scripts/init_secrets.sh --mode vault   # producción vía HashiCorp Vault
```

- `--mode local` solo garantiza que exista un `.env` (copiándolo de
  `.env.example` si falta) y nunca sobrescribe uno existente. Es el
  comportamiento de desarrollo, no de producción.
- `--mode aws` y `--mode vault` leen **un** secreto/ruta con forma de
  objeto JSON plano (clave: valor de string) y escriben cada clave
  presente como una línea `CLAVE=valor` en `.env`. Antes de escribir nada,
  validan que estén todas las claves requeridas (`REQUIRED_KEYS` en el
  script) y con valor no vacío; si falta alguna, el script falla sin
  escribir `.env` (nunca arranca con un secreto de producción a medias).

## Forma exacta del JSON esperado

El script (`write_env_from_json` en `scripts/init_secrets.sh`) espera un
objeto JSON plano — sin anidar, sin arrays — donde cada clave es
exactamente el nombre de variable de entorno que `Settings` lee (con
prefijo `SANTISIMA_` donde corresponda; `DEEPINFRA_API_KEY` es la
excepción, sin prefijo, porque identifica al proveedor del LLM y no a
esta app):

```json
{
  "DEEPINFRA_API_KEY": "di-...",
  "SANTISIMA_CLAVE_CIFRADO": "<clave Fernet generada con cryptography.fernet.Fernet.generate_key()>",
  "SANTISIMA_SESSION_SECRET": "<secreto generado con secrets.token_urlsafe(32)>",
  "SANTISIMA_POSTGRES_DSN": "postgresql://usuario:password@host:5432/la_santisima",
  "SANTISIMA_REDIS_URL": "redis://host:6379/0",

  "SANTISIMA_API_KEYS": "clave-admin-1,clave-admin-2",
  "SANTISIMA_USAR_POSTGRES": "true",
  "SANTISIMA_USAR_REDIS_RATE_LIMIT": "true"
}
```

Las primeras cinco claves (`DEEPINFRA_API_KEY`, `SANTISIMA_CLAVE_CIFRADO`,
`SANTISIMA_SESSION_SECRET`, `SANTISIMA_POSTGRES_DSN`,
`SANTISIMA_REDIS_URL`) son **obligatorias** — así estén vacías las
últimas dos por no usarse todavía (`usar_postgres=false`), la clave debe
existir en el JSON con un valor no vacío, o el script rechaza escribir
`.env`. Si de verdad no se usa Postgres/Redis, poner un DSN/URL con
formato válido pero apuntando a un host que no se resuelve — no dejarlo
vacío — o retirar la validación del script para ese caso (no hacer esto
sin revisar `REQUIRED_KEYS`).

Cualquier otra clave con prefijo `SANTISIMA_` (`SANTISIMA_API_KEYS`,
`SANTISIMA_USAR_POSTGRES`, `SANTISIMA_RATE_LIMIT_POR_MINUTO`, etc. — ver
`.env.example` para la lista completa) es opcional: si está presente en
el JSON se escribe a `.env` igual; si no está, simplemente no aparece en
`.env` y `Settings` usa su default de `config.py`.

Todos los valores deben ser strings JSON (`"true"`, no `true` booleano;
`pydantic-settings` parsea el string de entorno igual que si viniera de
un `.env` escrito a mano).

### AWS Secrets Manager

Crear/actualizar el secreto como un JSON secret (no "plaintext"), con el
nombre que apunte `AWS_SECRET_NAME` (default `la-santisima/prod`):

```bash
aws secretsmanager create-secret \
  --name la-santisima/prod \
  --secret-string file://secret.json
# o, para actualizar uno existente:
aws secretsmanager put-secret-value \
  --secret-id la-santisima/prod \
  --secret-string file://secret.json
```

`secret.json` tiene exactamente la forma de arriba. Borrar
`secret.json` del disco después (`shred -u secret.json` o equivalente) —
nunca dejarlo commiteado ni en el mismo host de forma persistente.

### HashiCorp Vault

Escribir en una ruta KV (v1 o v2 — el script detecta el formato
automáticamente probando `.data.data` primero y cayendo a `.data`) que
apunte `VAULT_KV_PATH` (default `secret/la-santisima/prod`):

```bash
vault kv put secret/la-santisima/prod \
  DEEPINFRA_API_KEY="di-..." \
  SANTISIMA_CLAVE_CIFRADO="..." \
  SANTISIMA_SESSION_SECRET="..." \
  SANTISIMA_POSTGRES_DSN="postgresql://..." \
  SANTISIMA_REDIS_URL="redis://..."
```

Cada par `clave=valor` pasado a `vault kv put` se convierte en una clave
del objeto `.data.data` (KV v2) que el script lee — no hace falta
construir el JSON a mano en este caso.

## IAM / política de acceso (alto nivel)

El principal que ejecuta `init_secrets.sh` en el host de producción
(el rol/usuario que corre el paso de deploy, no un desarrollador) necesita
acceso de **solo lectura** al secreto específico, nada más amplio:

- **AWS**: una policy IAM que otorgue `secretsmanager:GetSecretValue`
  (y `secretsmanager:DescribeSecret` si se usa rotación automática de
  AWS) acotada por `Resource` al ARN exacto del secreto
  (`la-santisima/prod`), no a `secretsmanager:*` ni a `Resource: "*"`.
  Sin `PutSecretValue`/`CreateSecret`/`DeleteSecret` — el host de
  producción solo lee, quien rota escribe desde su propia máquina o
  pipeline separado.
- **Vault**: una policy que otorgue `read` (no `create`/`update`) sobre
  la ruta exacta `secret/data/la-santisima/prod` (KV v2) o
  `secret/la-santisima/prod` (KV v1), autenticada vía el método que
  corresponda al entorno (AppRole para un host, IAM auth / Kubernetes
  auth si el deploy corre en esa infraestructura — evitar tokens
  root/estáticos de larga vida).
- En ambos casos: acceso auditado (CloudTrail para AWS, audit device de
  Vault) — cualquier lectura del secreto de producción debe quedar
  registrada, porque incluye `SANTISIMA_SESSION_SECRET` y
  `SANTISIMA_CLAVE_CIFRADO`.

## Uso en el paso de deploy

`init_secrets.sh` corre **antes** de arrancar `uvicorn`, como parte del
mismo paso de deploy (ver `docs/runbooks/DEPLOYMENT.md` para el resto del
checklist):

```bash
# En el host de producción, con las credenciales AWS/Vault del rol de deploy
# ya configuradas en el entorno (perfil de instancia / VAULT_ADDR+VAULT_TOKEN):

AWS_SECRET_NAME=la-santisima/prod \
AWS_REGION=us-east-1 \
scripts/init_secrets.sh --mode aws

# .env queda escrito (permisos 600) en la raíz del repo. Recién ahora:
systemctl restart santisima   # o el comando uvicorn/gunicorn equivalente
```

Si `init_secrets.sh` falla (secreto inalcanzable, JSON inválido, clave
requerida faltante), el paso de deploy debe abortar ahí — no continuar a
`systemctl restart` con un `.env` viejo o inexistente, porque
`Settings.validar_produccion()` igual hará fallar el arranque si faltan
`session_secret`/`clave_cifrado`, pero es mejor detectarlo en el paso de
deploy con un mensaje claro que en el arranque del proceso.

## Rotación de un secreto

Procedimiento general (aplica a `DEEPINFRA_API_KEY`,
`SANTISIMA_POSTGRES_DSN`, `SANTISIMA_REDIS_URL`, `SANTISIMA_API_KEYS`):

1. Actualizar el valor en AWS Secrets Manager (`put-secret-value`) o
   Vault (`vault kv put`, que crea una nueva versión).
2. Re-ejecutar `scripts/init_secrets.sh --mode aws` (o `--mode vault`) en
   cada instancia — reescribe `.env` con el valor nuevo.
3. Reiniciar el proceso (`systemctl restart santisima`) para que
   `pydantic-settings` relea `.env` — `Settings` está cacheado por
   proceso (`get_settings`, `@lru_cache`), así que un `.env` nuevo en
   disco no tiene efecto hasta el restart.
4. En despliegue multi-instancia: rotar instancia por instancia (rolling,
   igual que un deploy normal — ver `docs/runbooks/DEPLOYMENT.md`), no
   todas a la vez, salvo que el secreto rotado no tenga ventana de
   incompatibilidad entre valor viejo/nuevo (ver el caso especial de
   `SANTISIMA_SESSION_SECRET` abajo, que sí la tiene).

### Caso especial: `SANTISIMA_SESSION_SECRET`

**No es una rotación casual.** Por diseño (ver el docstring de
`session_secret` en `config.py`), este valor firma con HMAC todo
`session_id`/`device_token` que el servidor haya emitido. Cambiarlo
invalida de golpe **todos** los `session_id`/`device_token` emitidos con
el valor anterior — cualquier dispositivo/cliente que los tenga
guardados deja de poder autenticarse hasta que vuelva a registrarse
(`POST /api/v1/dispositivos`).

Esto significa:

- Rotar `SANTISIMA_SESSION_SECRET` es un evento de impacto a usuarios, no
  una operación de mantenimiento transparente. Coordinar con antelación
  (aviso a clientes/frontends que dependan de sesiones persistentes),
  igual que un evento de "todos los usuarios deben volver a iniciar
  sesión".
- En despliegue **single-instance**: el corte es inmediato en el
  restart — no hay forma de tener periodo de gracia con una sola
  instancia y un solo valor de secreto activo a la vez.
- En despliegue **multi-instancia**: rotar `SANTISIMA_SESSION_SECRET`
  instancia por instancia (rolling normal) todavía dejaría, durante el
  rollout, instancias viejas y nuevas con secretos distintos sirviendo
  tráfico simultáneamente — un token emitido por una instancia nueva no
  valida en una instancia vieja todavía sin actualizar, y viceversa. Para
  evitar ese corte intermitente, coordinar la rotación de
  `SANTISIMA_SESSION_SECRET` específicamente (no aplica al resto de
  secretos, que no tienen este acoplamiento): actualizar el secreto en
  AWS/Vault y reiniciar **todas** las instancias en la ventana más
  corta posible, aceptando que durante esa ventana habrá sesiones
  inválidas, en vez de un rolling gradual.
- Nunca rotar `SANTISIMA_SESSION_SECRET` como parte de un deploy rutinario
  que además cambia código — aislarlo en su propio cambio, para poder
  diagnosticar "sesiones inválidas" (ver
  `docs/runbooks/TROUBLESHOOTING.md#sesión-inválida-tras-un-deploy`) sin
  confundirlo con un bug del código desplegado a la vez.

`SANTISIMA_CLAVE_CIFRADO` tiene una restricción parecida pero distinta:
cambiarla no invalida sesiones, pero el contenido ya cifrado con la
clave vieja deja de descifrar con la nueva — no rotar sin un plan de
re-cifrado del historial existente (o aceptar perder acceso a mensajes
antiguos, lo cual normalmente no es aceptable).
