#!/bin/bash
# Script para ejecutar todas las pruebas desde el entorno virtual

echo "🔧 Activando entorno virtual..."
source .venv/bin/activate

echo "📦 Verificando instalación..."
python -c "import la_santisima_conversacional; print('✅ Paquete importado correctamente')"

echo ""
echo "🧪 EJECUTANDO PRUEBAS..."
echo "================================"

# Opciones disponibles
echo ""
echo "Selecciona una opción:"
echo "1. 🚀 Prueba SUPER RÁPIDA (test_minimo.py)"
echo "2. ⚡ Prueba RÁPIDA (test_rapido.py)"
echo "3. 📊 Prueba DIRECTA (test_directo.py)"
echo "4. 📈 Prueba COMPLETA (test_bateria_preguntas.py)"
echo "5. 🔍 Verificar servidor (check_servidor.sh)"
echo "6. 🏃 Ejecutar TODAS las pruebas en orden"
echo "7. 🚪 Salir"
echo ""

read -p "Opción (1-7): " opcion

case $opcion in
    1)
        echo "🚀 Ejecutando prueba SUPER RÁPIDA..."
        python test_minimo.py
        ;;
    2)
        echo "⚡ Ejecutando prueba RÁPIDA..."
        python test_rapido.py
        ;;
    3)
        echo "📊 Ejecutando prueba DIRECTA..."
        python test_directo.py
        ;;
    4)
        echo "📈 Ejecutando prueba COMPLETA..."
        python test_bateria_preguntas.py
        ;;
    5)
        echo "🔍 Verificando servidor..."
        ./check_servidor.sh
        ;;
    6)
        echo "🏃 Ejecutando TODAS las pruebas..."
        echo ""
        echo "=== PASO 1: Verificar estructura ==="
        python test_directo.py
        
        echo ""
        echo "=== PASO 2: Probar con servidor (si está activo) ==="
        if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
            echo "✅ Servidor activo, ejecutando prueba mínima..."
            python test_minimo.py
        else
            echo "⚠️  Servidor no activo. Para activarlo:"
            echo "   export DEEPINFRA_API_KEY='tu_key' && ./iniciar_servidor.sh"
        fi
        
        echo ""
        echo "=== PASO 3: Pruebas unitarias ==="
        python -m pytest tests/test_crear_servicio.py -v
        
        echo ""
        echo "🎉 Todas las pruebas completadas"
        ;;
    7)
        echo "👋 Saliendo..."
        exit 0
        ;;
    *)
        echo "❌ Opción inválida"
        exit 1
        ;;
esac

echo ""
echo "📌 Para más opciones ejecuta nuevamente: ./ejecutar_pruebas.sh"
echo "🕐 Pruebas completadas a las: $(date '+%H:%M:%S')"