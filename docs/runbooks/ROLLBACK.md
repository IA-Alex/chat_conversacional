# Rollback — La Santísima Muerte

Cómo revertir un deploy con lo que existe realmente en el repo: no hay
imagen Docker versionada ni artifact registry (ver
`DEPLOYMENT.md#lo-que-no-existe-todavía`), así que "rollback" es `git
checkout <rev-anterior>` + reinstalar deps + reiniciar, no "apuntar al
tag de imagen anterior". Tampoco hay mecanismo de migraciones de esquema
— eso hace que ciertos rollbacks sean seguros y otros no, según qué tocó
el deploy que se está revirtiendo.

## Decisión rápida: ¿este rollback es seguro?

| El deploy que se revierte tocó... | ¿Rollback simple es seguro? |
|---|---|
| Solo lógica de aplicación (prompts, endpoints, validación) sin tocar esquema de datos ni secretos | Sí — `git checkout` + reinstalar + reiniciar |
| `SANTISIMA_SESSION_SECRET` (rotación) | **No sin plan** — ver abajo |
| `SANTISIMA_CLAVE_CIFRADO` (rotación) | **No sin plan** — ver abajo |
| Esquema de `messages`/dispositivos (columnas nuevas, tipos) | **No sin plan** — no hay migraciones, ver abajo |
| `SANTISIMA_AVISO_PRIVACIDAD_VERSION` (subida de versión) | Revertir la versión sin más re-pide consentimiento a nadie que ya lo dio en la versión nueva — inofensivo pero revisar `docs/privacidad.md` esté coherente con la versión a la que se vuelve |
| Dependencias (`pyproject.toml`) | Sí, siempre que el checkout anterior también reinstale su propio `pyproject.toml` — no mezclar código viejo con deps nuevas |

## Rollback simple (caso común)

Aplica cuando el deploy no tocó secretos ni esquema de datos.

```bash
# 1. Confirmar la revisión buena conocida (el commit anterior al deploy problemático)
git log --oneline -10

# 2. Detener el servicio antes de tocar el checkout, para no servir un
#    estado a medio cambiar
sudo systemctl stop santisima

# 3. Checkout de la revisión anterior
git checkout <rev-anterior>

# 4. Reinstalar deps de ESA revisión (pyproject.toml puede diferir del
#    deploy que se revierte)
pip install -e .   # o con extras si esa revisión los usaba: .[postgres,redis]

# 5. Reiniciar
sudo systemctl start santisima

# 6. Verificar
curl -s localhost:8000/health/ready
curl -s localhost:8000/metrics/health | python3 -m json.tool
journalctl -u santisima -n 50 --no-pager
```

**Downtime esperado**: igual al de un deploy normal (segundos, un solo
proceso) — ver `DEPLOYMENT.md`. En multi-instancia, revertir instancia
por instancia como cualquier rolling deploy, no todas a la vez.

## Rollback tras rotar `SANTISIMA_SESSION_SECRET`

**El problema**: `session_id`/`device_token` son HMAC firmados con este
secreto (ver `infrastructure/security.py`). Si el deploy que se revierte
incluyó una rotación de `session_secret`, revertir el código sin también
revertir la variable de entorno dejaría el secreto nuevo activo con
código viejo — o, si también se revierte la variable, invalida de golpe
cualquier token emitido durante la ventana en que corrió el secreto
nuevo.

**No hay forma de "recuperar" sesiones emitidas con un secreto que ya no
está activo** — es el mismo invariante que documenta
`TROUBLESHOOTING.md#sesión-inválida-tras-un-deploy`. Rotar
`session_secret` (en cualquier dirección, hacia adelante o hacia atrás)
siempre invalida algún conjunto de tokens.

**Procedimiento**:

1. Decidir explícitamente cuál secreto queda activo tras el rollback —
   normalmente el que estaba activo *antes* del deploy que se revierte,
   para que los usuarios que no alcanzaron a re-autenticarse con el
   secreto nuevo recuperen su sesión.
2. Confirmar el fingerprint esperado antes de tocar nada:
   ```bash
   journalctl -u santisima | grep "session_secret_fingerprint"
   ```
3. Restaurar `SANTISIMA_SESSION_SECRET` al valor correspondiente en
   `.env` (el `EnvironmentFile=` que usa el `.service` de systemd, ver
   `docs/despliegue.md §4`) **junto con** el código, en el mismo paso de
   rollback — nunca uno sin el otro.
4. Reiniciar y confirmar el fingerprint en logs coincide con el esperado.
5. Comunicar (si hay canal para eso) que usuarios que registraron
   dispositivo durante la ventana del secreto ahora inválido deberán
   re-registrar — no hay forma de evitarlo retroactivamente.

## Rollback tras rotar `SANTISIMA_CLAVE_CIFRADO`

**El problema**: `SQLiteConversationRepository`/
`PostgresConversationRepository` cifran `content` con Fernet usando esta
clave (ver `infrastructure/repositories.py`). Mensajes guardados con la
clave nueva **no se pueden descifrar con la clave vieja** —
`_descifrar` lanza `InvalidToken` si la clave no coincide con la que
cifró ese registro específico.

**Esto es más delicado que `session_secret`**: no es "algunos tokens
dejan de validar", es "algunas filas de la base quedan permanentemente
ilegibles" si se revierte la clave sin más. No hay ceremonia de
re-cifrado versionada en este repo.

**Procedimiento**:

1. **Antes de rotar `clave_cifrado` en cualquier deploy futuro**, tener
   un plan de re-cifrado (leer todo con la clave vieja, re-escribir con
   la nueva) — esto debería ser parte del propio deploy que rota la
   clave, no algo que se improvisa en un rollback.
2. Si ya se rotó sin re-cifrar y hace falta revertir:
   - Los mensajes guardados **antes** de la rotación siguen siendo
     legibles con la clave vieja — revertir `clave_cifrado` a la vieja
     los recupera.
   - Los mensajes guardados **durante la ventana con la clave nueva**
     quedan ilegibles al revertir — no hay forma de recuperarlos sin la
     clave nueva. Guardar la clave nueva en un lugar seguro (no
     descartarla) antes de revertir, por si se necesita recuperarlos
     después con un script de re-cifrado ad hoc.
3. Restaurar `SANTISIMA_CLAVE_CIFRADO` junto con el código, mismo
   principio que `session_secret`: nunca revertir uno sin el otro.
4. Verificar leyendo historial de una sesión de prueba tras el restart —
   un `InvalidToken` no manejado se manifestaría como 500 en el endpoint
   que lee historial; confirmar en logs que no aparece.

## Rollback cuando el deploy tocó el esquema de datos

**No hay mecanismo de migraciones** en este repo (ni Alembic ni
equivalente versionado) — `_inicializar_base_datos` en
`SQLiteConversationRepository` corre `CREATE TABLE IF NOT EXISTS` en cada
arranque, lo que significa que añadir una columna nueva normalmente se
hace a mano (o con un script ad hoc) fuera del ciclo normal de deploy.

**Implicación para rollback**: si un deploy agregó una columna y el
código nuevo la usa, revertir el código sin revertir el esquema es
**seguro solo si la columna nueva tiene un default y el código viejo
simplemente la ignora** (no falla por su presencia). Si el código viejo
hace `SELECT` con columnas explícitas que no incluyen la nueva, no hay
problema. Si el esquema cambió de forma incompatible (columna
renombrada, tipo cambiado, NOT NULL sin default), revertir el código
**no es seguro** sin también revertir el esquema — y revertir el esquema
puede perder datos escritos con la forma nueva.

**Procedimiento**:

1. Antes de cualquier deploy que toque esquema: confirmar que es
   compatible hacia atrás (el checklist pre-deploy de `DEPLOYMENT.md` ya
   lo exige) — esto es lo que evita necesitar este procedimiento.
2. Si ya se desplegó y hace falta revertir de todos modos:
   - Backup de la base **antes de tocar nada** (`conversations.db`/
     `dispositivos.db`, o `pg_dump` si es Postgres).
   - Si el cambio es aditivo (columna nueva con default, tabla nueva sin
     dependencias del código viejo): revertir solo el código es seguro.
   - Si el cambio es destructivo/incompatible: escribir una migración
     manual inversa antes de revertir el código, probarla contra una
     copia del backup, y solo entonces aplicarla a producción.
3. Nunca revertir código contra un esquema que ese código no reconoce sin
   antes confirmar (en una copia, no en producción) que no revienta al
   primer `SELECT`/`INSERT`.

## Checklist de rollback (cualquier caso)

- [ ] Backup de `conversations.db` / `dispositivos.db` (o `pg_dump` si
      aplica) antes de tocar nada.
- [ ] Identificada la revisión buena conocida (`git log`).
- [ ] Confirmado si el deploy a revertir tocó `session_secret`,
      `clave_cifrado`, o esquema — si sí, seguir la sección específica
      arriba, no el camino simple.
- [ ] `systemctl stop santisima` antes de cambiar el checkout.
- [ ] `git checkout <rev>` + `pip install -e .` con los extras que esa
      revisión requiera.
- [ ] Variables de entorno (`.env`) coherentes con la revisión a la que
      se vuelve — no solo el código.
- [ ] `systemctl start santisima`.
- [ ] `curl -s localhost:8000/health/ready` → 200.
- [ ] `curl -s localhost:8000/metrics/health` → `llm_adapter_status:
      "ok"`, `db_backend` y `redis_rate_limit_enabled` como se esperan
      para esta revisión.
- [ ] `journalctl -u santisima -n 50` sin tracebacks de arranque.
- [ ] Prueba funcional mínima: registrar un dispositivo de prueba,
      enviar un mensaje, confirmar respuesta no-fallback.
- [ ] Si se revirtió multi-instancia: repetir por instancia, una a la
      vez, confirmando `/health/ready` antes de seguir con la siguiente
      (mismo patrón rolling que `DEPLOYMENT.md`).
- [ ] Documentar qué se revirtió y por qué (para el postmortem, ver
      `INCIDENT_RESPONSE.md#cierre-de-incidente`).
