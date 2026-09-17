# Guía Rápida para Pruebas de La Santísima Muerte

## Estado Actual
- **Servidor detectado**: NO está corriendo en puerto 8000
- **Herramientas creadas**: ✅ Scripts de prueba listos

## 🚀 Para Empezar

### 1. Iniciar el servidor
```bash
# Asegúrate de tener la API key configurada
export DEEPINFRA_API_KEY="tu_key_deepinfra"

# Iniciar servidor
./iniciar_servidor.sh
```

### 2. Verificar que funciona
```bash
# Verificación rápida
./check_servidor.sh

# O directamente
curl http://127.0.0.1:8000/health
```

## 📊 Opciones de Pruebas

### 🔍 **Prueba SUPER RÁPIDA** (1 minuto)
```bash
python test_minimo.py
```
**Mide**: 
- ¿El servidor responde?
- Tiempo de 3 mensajes básicos
- Coherencia mínima

### ⚡ **Prueba RÁPIDA** (2-3 minutos)
```bash
python test_rapido.py
```
**Mide**:
- Salud completa del sistema
- 4-5 preguntas variadas
- Tiempos estadísticos
- Guarda resultados en JSON

### 📈 **Prueba COMPLETA** (5-10 minutos)
```bash
python test_bateria_preguntas.py
```
**Mide**:
1. **Coherencia** - 10 preguntas variadas
2. **Robustez** - Entradas problemáticas (vacías, largas, etc.)
3. **Múltiples sesiones** - 3 sesiones concurrentes
4. **Tiempo sostenido** - 20 mensajes seguidos

## 📋 Qué se Mide en Cada Prueba

### Métricas Principales:
1. **Tiempo de respuesta** - Desde que envías hasta que recibes
2. **Coherencia** - ¿Las respuestas tienen sentido?
3. **Robustez** - ¿Aguanta entradas raras?
4. **Concurrencia** - ¿Soporta múltiples usuarios?

### Escalas de Evaluación:

#### Tiempos de Respuesta:
- **< 2s**: Excelente 🎯
- **2-5s**: Aceptable ⚠️  
- **> 5s**: Lento 🐌

#### Porcentaje de Éxito:
- **> 90%**: Excelente 🎯
- **70-90%**: Aceptable ⚠️
- **< 70%**: Mejorable 🔧

## 🎯 Ejemplo de Uso Rápido

```bash
# Paso 1: Iniciar servidor
export DEEPINFRA_API_KEY="tu_key"
./iniciar_servidor.sh

# Paso 2: Esperar que inicie (ver log)
tail -f servidor.log

# Paso 3: Prueba rápida
python test_minimo.py

# Paso 4: Si pasa, prueba completa
python test_rapido.py
```

## 📁 Archivos Creados

1. **test_minimo.py** - Prueba de 30 segundos
2. **test_rapido.py** - Prueba de 2-3 minutos  
3. **test_bateria_preguntas.py** - Prueba completa
4. **check_servidor.sh** - Verificación rápida
5. **iniciar_servidor.sh** - Inicio del servidor
6. **GUIA_PRUEBAS.md** - Esta guía

## 🔧 Solución de Problemas

### ❌ "Servidor NO disponible"
```bash
# Verificar proceso
ps aux | grep uvicorn

# Matar proceso anterior
pkill -f "uvicorn.*la_santisima"

# Reintentar
./iniciar_servidor.sh
```

### ❌ "DEEPINFRA_API_KEY no configurada"
```bash
# Configurar variable
export DEEPINFRA_API_KEY="di-tu_key_aqui"

# O editar .env
cp .env.example .env
# Editar .env con tu key
```

### ❌ "Error en la respuesta"
```bash
# Ver logs detallados
tail -n 50 servidor.log

# Probar endpoint manualmente
curl -v http://127.0.0.1:8000/health
```

## 📊 Interpretando Resultados

Los resultados se guardan en:
- `test_rapido_resultados.json` - Para test_rapido.py
- `resultados_pruebas.json` - Para test_bateria_preguntas.py

### Ejemplo de resultado exitoso:
```json
{
  "promedio_tiempo": 1.23,
  "resultados": [
    {"pregunta": "Hola", "tiempo": 1.1, "respuesta_len": 85},
    {"pregunta": "¿Cómo estás?", "tiempo": 1.4, "respuesta_len": 92}
  ]
}
```

**Interpretación**: 
- `promedio_tiempo: 1.23` → Excelente (< 2s)
- `respuesta_len: 85` → Respuestas de buen tamaño
- Todos los tiempos similares → Comportamiento estable

## 🎯 Recomendación Inicial

```bash
# Para una validación rápida hoy:
1. ./iniciar_servidor.sh
2. python test_minimo.py

# Si pasa, entonces:
3. python test_rapido.py
```

Esto te dará en **menos de 5 minutos** una evaluación completa de:
- ✅ ¿Funciona el sistema?
- ⚡ ¿Qué tan rápido responde?
- 🧠 ¿Las respuestas son coherentes?
- 🛡️ ¿Es robusto ante errores?