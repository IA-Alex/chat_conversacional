#!/bin/bash
# Script rápido para verificar estado del servidor

echo "🔍 Verificando servidor en 127.0.0.1:8000..."

# Verificar si responde el health check
if curl -s http://127.0.0.1:8000/health > /dev/null; then
    echo "✅ Servidor RESPONDE"
    
    # Obtener detalles del health
    echo "\n📊 Estado del servicio:"
    curl -s http://127.0.0.1:8000/health | python3 -m json.tool | grep -E "(status|degradado|modelo|uptime)" | head -10
    
    echo "\n⚡ Probando respuesta rápida..."
    
    # Registrar dispositivo
    DEVICE_TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/dispositivos | python3 -c "import sys, json; print(json.load(sys.stdin)['device_token'])")
    
    # Crear sesión
    SESSION_ID=$(curl -s -X POST http://127.0.0.1:8000/api/v1/sesiones \
        -H "Authorization: Bearer $DEVICE_TOKEN" | python3 -c "import sys, json; print(json.load(sys.stdin)['session_id'])")
    
    echo "📱 Dispositivo: ${DEVICE_TOKEN:0:8}..."
    echo "💬 Sesión: ${SESSION_ID:0:8}..."
    
    # Enviar mensaje de prueba
    echo "\n📤 Enviando mensaje de prueba..."
    START_TIME=$(date +%s.%N)
    
    RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/api/v1/mensajes \
        -H "Authorization: Bearer $DEVICE_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"session_id\": \"$SESSION_ID\", \"mensaje\": \"Hola, ¿puedes responderme?\"}")
    
    END_TIME=$(date +%s.%N)
    ELAPSED=$(echo "$END_TIME - $START_TIME" | bc)
    
    if [ $? -eq 0 ]; then
        RESPUESTA=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['respuesta'][:100])")
        echo "✅ Respuesta obtenida en ${ELAPSED}s"
        echo "📥 Respuesta: \"$RESPUESTA...\""
        
        # Evaluación rápida
        if (( $(echo "$ELAPSED < 3" | bc -l) )); then
            echo "🎯 TIEMPO: EXCELENTE"
        elif (( $(echo "$ELAPSED < 6" | bc -l) )); then
            echo "⚠️  TIEMPO: ACEPTABLE"
        else
            echo "🐌 TIEMPO: LENTO"
        fi
    else
        echo "❌ Error en la respuesta"
    fi
    
else
    echo "❌ Servidor NO RESPONDE"
    echo "\n📝 Posibles causas:"
    echo "  1. Servidor no está corriendo"
    echo "  2. Está en otro puerto (no 8000)"
    echo "  3. Firewall bloqueando"
    echo "\n💡 Solución:"
    echo "  Ejecutar: uvicorn la_santisima_conversacional.presentation.http_api:app --reload"
fi

echo "\n📌 Para más pruebas ejecutar:"
echo "  python test_minimo.py  (prueba rápida)"
echo "  python test_rapido.py   (prueba completa)"