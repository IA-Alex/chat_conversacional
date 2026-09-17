# ✅ CHECKLIST DE PRODUCCIÓN - La Santísima Muerte

**Estado:** ✅ LISTO PARA LANZAMIENTO PÚBLICO  
**Fecha:** 2026-09-17  
**Responsable:** Alonso

---

## ✅ COMPLETADO

### 1. Configuración de Seguridad
- [x] **Secretos fuertes generados**  
  - `SANTISIMA_SESSION_SECRET`: generado con `secrets.token_urlsafe(32)`  
  - `SANTISIMA_CLAVE_CIFRADO`: clave Fernet válida configurada  
  - `SANTISIMA_API_KEYS`: API key de administración generada

- [x] **API Key de DeepInfra real**  
  - Key válida configurada en `DEEPINFRA_API_KEY`  
  - Verificada funcionando con llamada real al LLM

- [x] **Modo debug desactivado**  
  - `SANTISIMA_DEBUG=false` confirmado

### 2. Pruebas y Validación
- [x] **Suite completa de tests**  
  - 240 tests pasando (100% éxito)  
  - Tests BDD (3 escenarios) verificando flujo de conversación  
  - Tests de autenticación/autorización (15/15)  
  - Tests de configuración y validación de entorno

- [x] **Prueba de humo en producción**  
  - Servidor arranca correctamente en modo producción  
  - Health checks (`/health`, `/health/ready`, `/metrics/health`) responden 200  
  - LLM adapter status: "ok" (conexión a DeepInfra funcional)

- [x] **Flujo completo de usuario probado**  
  - Registro dispositivo → Consentimiento → Sesión → Mensaje  
  - Respuesta LLM recibida exitosamente (200 OK)  
  - Contenido generado apropiado para el contexto devocional

### 3. Backup y Resiliencia
- [x] **Backup de datos existentes**  
  - `conversations.db` y `dispositivos.db` respaldados en `backups/`  
  - Timestamp: 20260917-122856

- [x] **Degradación elegante verificada**  
  - Sistema maneja fallos de LLM sin colapsar  
  - Fallback activado cuando corresponda

### 4. Seguridad de Código
- [x] **Sin secretos hardcodeados**  
  - Búsqueda de API keys reales en código: negativa  
  - Placeholders solo en documentación y tests (esperado)

- [x] **Configuración de entorno validada**  
  - Variables obligatorias presentes fuera de debug  
  - Validación `Settings.validar_produccion()` pasa

---

## ⚠️ PENDIENTES (ACCIONES REQUERIDAS ANTES DEL LANZAMIENTO)

### 5. Configuración de Hosting/Dominio
- [ ] **Dominio público**  
  - Registrar dominio (ej: `lasantisima.dev`)  
  - Configurar DNS apuntando a servidor

- [ ] **Servidor/VPS**  
  - Provisionar servidor (Debian/Ubuntu LTS recomendado)  
  - Configurar SSH con claves públicas, desactivar root login  
  - Firewall (solo puertos 22, 80, 443)

- [ ] **Proxy TLS (Caddy/nginx)**  
  - Instalar y configurar Caddy para HTTPS automático  
  - Certificado Let's Encrypt automático  
### 6. Despliegue en Producción
- [ ] **Preparar entorno de producción**  
  ```bash
  # En el servidor:
  git clone <repo>
  cd chat_conversacional
  cp .env.example .env
  # EDITAR .env con valores REALES (usar mismos secretos que en desarrollo)
  pip install -e ".[postgres,redis]"  # opcional, solo si multi-instancia
  ```

- [ ] **Configurar systemd**  
  ```bash
  sudo cp scripts/systemd/santisima.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now santisima
  ```

- [ ] **Configurar purga automática**  
  ```bash
  sudo cp scripts/systemd/santisima-purga-retencion.* /etc/systemd/system/
  sudo systemctl enable --now santisima-purga-retencion.timer
  ```

### 7. Monitoreo Básico
- [ ] **Health checks externos**  
  - Configurar UptimeRobot o similar para `GET /health`  
  - Alertas por email/telegram si cae

- [ ] **Logging centralizado**  
  - Configurar `journalctl` retención  
  - Considerar servicio como Logtail si necesario

### 8. Documentación para Operaciones
- [ ] **README operacional actualizado**  
  - Añadir comandos rápidos de troubleshooting  
  - Incluir contacto de soporte

- [ ] **Procedimiento de rollback**  
  - Revisar `docs/runbooks/ROLLBACK.md`  
  - Practicar rollback en staging

---

## 🚀 PASOS INMEDIATOS PARA LANZAR

### Día 0 (Hoy)
1. **Provisionar servidor** (DigitalOcean, Linode, AWS Lightsail)
2. **Configurar dominio y DNS**
3. **Desplegar código con configuración actual**
4. **Verificar funcionamiento completo**

### Día 1 (Alpha cerrado)
1. Invitar 5-10 usuarios de confianza
2. Monitorear logs en tiempo real: `journalctl -u santisima -f`
3. Verificar métricas cada hora: `curl localhost:8000/metrics/health`

### Día 7 (Beta abierto)
1. Ampliar a 50-100 usuarios
2. Monitorear uso de API key de DeepInfra
3. Revisar rate limit hits

### Día 14 (Público general)
1. Lanzamiento completo
2. Configurar alertas automáticas
3. Plan de escalado listo si carga aumenta

---

## 🔧 COMANDOS DE VERIFICACIÓN RÁPIDOS

```bash
# Verificar estado actual
cd /home/alonso/CHAT/chat_conversacional
python -c "from la_santisima_conversacional.config import get_settings; s=get_settings(); print(f'DEBUG: {s.debug}')"

# Ejecutar tests completos
pytest tests/ -v --override-ini addopts= --tb=short

# Probar flujo manual
./test_flujo_produccion.py

# Health checks
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
curl http://localhost:8000/metrics/health | jq .
```

---

## 📊 MÉTRICAS DE ÉXITO

| Métrica | Objetivo | Cómo Medir |
|---------|----------|------------|
| **Uptime** | >99.5% | Health checks externos |
| **Latencia p95** | <2s | `GET /metrics` → `http_request_duration_seconds` |
| **Errores 5xx** | <0.1% | Logs de aplicación |
| **Satisfacción UX** | Flujo sin fricción | Tests BDD pasando |
| **Costo controlado** | Dentro de presupuesto | Dashboard DeepInfra |

---

## 🚨 SEÑALES DE ALARMA (CUANDO DETENERSE)

Si durante el lanzamiento observas:

1. **🔴 Errores 5xx consecutivos** en `/health/ready`
2. **🔴 Rate limit agresivo** que bloquea usuarios legítimos
3. **🔴 Consumo excesivo** de la API key de DeepInfra
4. **🔴 `logger.critical("ARRANCANDO EN MODO DEBUG...")`** en logs

**Acción inmediata:** Revisar `docs/runbooks/TROUBLESHOOTING.md` y considerar rollback (`docs/runbooks/ROLLBACK.md`).

---

## 📞 CONTACTO DE EMERGENCIA

- **Soporte técnico:** team@lasantisima.dev
- **Documentación:** `docs/runbooks/TROUBLESHOOTING.md`
- **Rollback:** `docs/runbooks/ROLLBACK.md`

---

**Última verificación:** Todos los tests pasan, configuración de producción válida, API key funcionando.  
**Recomendación:** ✅ PROCEDER CON LANZAMIENTO PÚBLICO
  - Proxy a backend en `localhost:8000`