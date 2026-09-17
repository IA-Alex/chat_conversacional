#!/bin/bash
# Script para iniciar el servidor de La Santísima Muerte

echo "🚀 Iniciando servidor La Santísima Muerte..."

# Verificar si ya está corriendo
if lsof -i :8000 > /dev/null 2>&1; then
    echo "⚠️  Servidor ya está corriendo en puerto 8000"
    echo "   Para detenerlo: pkill -f \"uvicorn.*la_santisima\""
    exit 1
fi

# Cargar variables de entorno desde .env si existe
if [ -f .env ]; then
    echo "📄 Cargando variables desde .env"
    # Usar set -a para exportar todas las variables automáticamente
    set -a
    source .env
    set +a
    echo "✅ Variables cargadas desde .env"
elif [ -f .env.example ]; then
    echo "⚠️  Archivo .env no encontrado, usando .env.example"
    cp .env.example .env 2>/dev/null || echo "No se pudo copiar .env.example"
    set -a
    source .env
    set +a
fi

# Verificar variables de entorno necesarias
if [ -z "$DEEPINFRA_API_KEY" ] || [ "$DEEPINFRA_API_KEY" = "di-..." ]; then
    echo "❌ DEEPINFRA_API_KEY no está configurada o usa valor por defecto"
    echo "💡 Edita el archivo .env con tu key real de DeepInfra"
    echo "   O ejecuta: export DEEPINFRA_API_KEY=\"tu_key_aqui\""
    exit 1
fi

# Iniciar servidor en background
echo "🌐 Iniciando servidor FastAPI en http://127.0.0.1:8000"

# Opciones de ejecución:
# 1. Con uvicorn directamente
echo "📡 Ejecutando: uvicorn la_santisima_conversacional.presentation.http_api:app --host 0.0.0.0 --port 8000 --reload"

# Crear archivo de log
LOGFILE="servidor.log"
echo "📝 Logs en: $LOGFILE"

# Ejecutar en background
nohup uvicorn la_santisima_conversacional.presentation.http_api:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload > "$LOGFILE" 2>&1 &

SERVER_PID=$!
echo "✅ Servidor iniciado con PID: $SERVER_PID"

# Esperar un momento para que inicie
echo "⏳ Esperando inicio del servidor..."
sleep 3

# Verificar que está corriendo
if curl -s http://127.0.0.1:8000/health > /dev/null; then
    echo "🎉 Servidor LISTO en http://127.0.0.1:8000"
    echo ""
    echo "📌 Comandos útiles:"
    echo "   Ver logs: tail -f $LOGFILE"
    echo "   Ver salud: curl http://127.0.0.1:8000/health"
    echo "   Detener: kill $SERVER_PID"
    echo ""
    echo "🔍 Para pruebas ejecutar:"
    echo "   ./check_servidor.sh"
    echo "   python test_minimo.py"
else
    echo "❌ El servidor no responde después de 3 segundos"
    echo "   Revisa el log: tail -n 20 $LOGFILE"
    kill $SERVER_PID 2>/dev/null
fi