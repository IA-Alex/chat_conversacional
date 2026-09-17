#!/usr/bin/env python3
"""
Prueba DIRECTA del servicio La Santísima Muerte
Usa el API programático sin servidor HTTP
"""

import time
import statistics
from typing import List, Dict
from datetime import datetime

def test_directo_con_mock():
    """Prueba usando mocks para simular respuestas"""
    print("🧪 PRUEBA DIRECTA CON MOCK")
    print("="*60)
    
    try:
        from la_santisima_conversacional import crear_servicio
        
        print("1. Creando servicio (modo mock)...")
        
        servicio = crear_servicio(
            use_langchain=True,
            ventana_mensajes=3,
            usar_sqlite=False
        )
        
        print("✅ Servicio creado exitosamente")
        
        print("\n2. Probando respuesta a mensaje simple...")
        
        try:
            inicio = time.time()
            respuesta = servicio.responder("Hola", session_id="test-session-123")
            tiempo = time.time() - inicio
            
            print(f"📤 Mensaje: 'Hola'")
            print(f"📥 Respuesta obtenida en {tiempo:.2f}s")
            print(f"💬 Respuesta: {respuesta[:100]}..." if respuesta else "Sin respuesta")
            
            return {
                "exito": True,
                "tiempo": tiempo,
                "respuesta": respuesta[:200] if respuesta else None
            }
            
        except Exception as e:
            print(f"❌ Error al obtener respuesta: {e}")
            print("💡 Esto podría ser porque:")
            print("   - No hay DEEPINFRA_API_KEY configurada")
            print("   - El endpoint de DeepInfra no está disponible")
            
            # Probar funcionalidad básica sin LLM
            print("\n🔧 Probando funcionalidad básica sin LLM...")
            
            metodos = [m for m in dir(servicio) if not m.startswith('_')]
            print(f"Métodos disponibles: {', '.join(metodos[:10])}...")
            
            return {
                "exito": False,
                "error": str(e),
                "servicio_creado": True
            }
            
    except ImportError as e:
        print(f"❌ Error de importación: {e}")
        return {"exito": False, "error": f"Import error: {e}"}
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return {"exito": False, "error": str(e)}

def test_flujo_completo_con_stub():
    """Prueba con stub para simular LLM"""
    print("\n" + "="*60)
    print("🤖 PRUEBA CON STUB (simula LLM)")
    print("="*60)
    
    try:
        from unittest.mock import Mock
        
        # Crear un mock del servicio
        mock_servicio = Mock()
        mock_servicio.responder.return_value = "Te escucho, hijo mío. Estoy aquí para acompañarte en este momento."
        
        print("1. Mock de servicio creado")
        
        # Simular tiempos de respuesta
        tiempos = []
        preguntas = [
            "Hola",
            "¿Cómo estás?",
            "Necesito ayuda",
            "Gracias"
        ]
        
        resultados = []
        
        for i, pregunta in enumerate(preguntas, 1):
            inicio = time.time()
            
            # Simular tiempo de procesamiento (0.5-2s)
            time.sleep(0.5 + (i * 0.1))
            respuesta = mock_servicio.responder(pregunta, session_id=f"test-{i}")
            tiempo = time.time() - inicio
            
            tiempos.append(tiempo)
            resultados.append({
                "pregunta": pregunta,
                "respuesta": respuesta,
                "tiempo": tiempo
            })
            
            print(f"\n[{i}] Pregunta: '{pregunta}'")
            print(f"    Tiempo simulado: {tiempo:.2f}s")
            print(f"    Respuesta: '{respuesta[:60]}...'")
        
        # Análisis
        print("\n" + "="*60)
        print("📊 RESULTADOS SIMULADOS")
        print("="*60)
        
        promedio = statistics.mean(tiempos)
        print(f"Tiempo promedio simulado: {promedio:.2f}s")
        print(f"Mejor tiempo: {min(tiempos):.2f}s")
        print(f"Peor tiempo: {max(tiempos):.2f}s")
        
        if promedio < 1:
            print("🎯 SIMULACIÓN: RENDIMIENTO IDEAL")
        elif promedio < 3:
            print("⚠️  SIMULACIÓN: RENDIMIENTO REALISTA")
        else:
            print("🐌 SIMULACIÓN: RENDIMIENTO LENTO")
        
        return {
            "simulacion": True,
            "promedio_tiempo": promedio,
            "resultados": resultados,
            "exito": True
        }
        
    except Exception as e:
        print(f"❌ Error en simulación: {e}")
        return {"exito": False, "error": str(e)}

def test_estructura():
    """Prueba la estructura del proyecto"""
    print("\n" + "="*60)
    print("🏗️  PRUEBA DE ESTRUCTURA")
    print("="*60)
    
    checks = []
    
    # 1. Verificar imports básicos
    try:
        import la_santisima_conversacional
        checks.append(("Import módulo principal", True, ""))
    except ImportError as e:
        checks.append(("Import módulo principal", False, str(e)))
    
    # 2. Verificar configuración
    try:
        from la_santisima_conversacional.config import Settings
        config = Settings()
        checks.append(("Configuración Settings", True, ""))
    except Exception as e:
        checks.append(("Configuración Settings", False, str(e)))
    
    # 3. Verificar creación de servicio
    try:
        from la_santisima_conversacional import crear_servicio
        checks.append(("Función crear_servicio", True, ""))
    except Exception as e:
        checks.append(("Función crear_servicio", False, str(e)))
    
    # 4. Verificar tests existentes
    try:
        import pytest
        checks.append(("Framework pytest", True, ""))
    except:
        checks.append(("Framework pytest", False, "No instalado"))
    
    # Mostrar resultados
    exitos = sum(1 for check, success, _ in checks if success)
    total = len(checks)
    
    print(f"Checks realizados: {exitos}/{total}")
    
    for nombre, exito, error in checks:
        status = "✅" if exito else "❌"
        print(f"{status} {nombre}")
        if error:
            print(f"   Error: {error}")
    
    return {
        "checks": checks,
        "exitos": exitos,
        "total": total,
        "porcentaje": (exitos / total * 100) if total > 0 else 0
    }

def main():
    """Función principal"""
    print("🚀 INICIANDO PRUEBAS DIRECTAS")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    resultados_totales = {}
    
    # 1. Prueba de estructura
    resultados_totales["estructura"] = test_estructura()
    
    # 2. Prueba directa (intenta usar servicio real)
    resultados_totales["directo"] = test_directo_con_mock()
    
    # 3. Prueba con stub (si la directa falló)
    if not resultados_totales["directo"].get("exito", False):
        print("\n" + "="*60)
        print("🔄 Intentando prueba con simulación...")
        resultados_totales["simulacion"] = test_flujo_completo_con_stub()
    
    # Resumen final
    print("\n" + "="*60)
    print("🎯 RESUMEN FINAL DE PRUEBAS")
    print("="*60)
    
    # Analizar estructura
    estructura = resultados_totales.get("estructura", {})
    if estructura:
        porcentaje = estructura.get("porcentaje", 0)
        print(f"🏗️  Estructura del proyecto: {porcentaje:.0f}%")
        if porcentaje >= 80:
            print("   ✅ ESTRUCTURA: SOLIDA")
        elif porcentaje >= 50:
            print("   ⚠️  ESTRUCTURA: PARCIAL")
        else:
            print("   ❌ ESTRUCTURA: PROBLEMAS")
    
    # Analizar prueba directa
    directo = resultados_totales.get("directo", {})
    if directo.get("exito"):
        tiempo = directo.get("tiempo", 0)
        print(f"🔗 Conexión con LLM: {tiempo:.2f}s")
        if tiempo > 0:
            if tiempo < 3:
                print("   ✅ CONEXIÓN: EXITOSA Y RÁPIDA")
            elif tiempo < 10:
                print("   ⚠️  CONEXIÓN: EXITOSA PERO LENTA")
            else:
                print("   🐌 CONEXIÓN: MUY LENTA")
    else:
        print("🔗 Conexión con LLM: NO DISPONIBLE")
        print("   💡 Se requiere DEEPINFRA_API_KEY configurada")
    
    # Analizar simulación
    simulacion = resultados_totales.get("simulacion", {})
    if simulacion.get("exito"):
        tiempo_prom = simulacion.get("promedio_tiempo", 0)
        print(f"🤖 Simulación de flujo: {tiempo_prom:.2f}s promedio")
        print("   📊 Flujo conversacional: SIMULADO CORRECTAMENTE")
    
    print("\n📌 RECOMENDACIONES:")
    
    if directo.get("exito"):
        print("1. ✅ El sistema funciona con el LLM real")
        print("2. ⚡ Ejecuta las pruebas HTTP completas")
    elif estructura.get("porcentaje", 0) >= 80:
        print("1. 🔧 Configura DEEPINFRA_API_KEY en .env")
        print("2. 🚀 Ejecuta ./iniciar_servidor.sh")
        print("3. 🧪 Luego ejecuta test_minimo.py")
    else:
        print("1. 🔨 Revisa problemas de estructura")
        print("2. 📦 Verifica instalación de dependencias")
        print("3. 🔧 Corrige imports faltantes")
    
    print(f"\n📄 Para más detalles, revisa los logs arriba")
    print(f"🕐 Fin: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()