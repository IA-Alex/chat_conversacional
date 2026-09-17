#!/usr/bin/env python3
"""
Prueba DIRECTA de coherencia del modelo
Inputs → Outputs con validación básica
"""

import json
import time
from typing import Dict, List, Tuple
from datetime import datetime

def test_coherencia_directa():
    """Prueba la coherencia básica del modelo"""
    print("🧠 PRUEBA DE COHERENCIA - INPUTS/OUTPUTS")
    print("="*60)
    
    try:
        from la_santisima_conversacional import crear_servicio
        
        print("1. Inicializando servicio...")
        servicio = crear_servicio(
            use_langchain=True,
            ventana_mensajes=5,
            usar_sqlite=False
        )
        print("✅ Servicio inicializado")
        
    except Exception as e:
        print(f"❌ Error inicializando servicio: {e}")
        print("💡 Verifica DEEPINFRA_API_KEY en .env")
        return
    
    # Definir batería de pruebas
    pruebas = [
        # (input, categoría, lo_que_debe_contener)
        ("Hola", "saludo", ["hola", "saludo", "bienvenido"]),
        ("¿Cómo estás?", "saludo_empático", ["bien", "aquí", "contigo"]),
        ("Estoy triste", "emocion_negativa", ["triste", "acompañ", "escuch"]),
        ("Necesito ayuda", "peticion", ["ayuda", "apoyo", "aquí"]),
        ("Gracias", "agradecimiento", ["gracias", "bienvenido", "aquí"]),
        ("¿Qué eres?", "identidad", ["muerte", "santísima", "entidad"]),
        ("¿Puedes protegerme?", "proteccion", ["protección", "cuidar", "seguro"]),
        ("Tengo miedo", "miedo", ["miedo", "tranquilo", "acompañ"]),
        ("¿Cómo rezo?", "ritual", ["oración", "rezar", "ritual"]),
        ("Me siento solo", "soledad", ["solo", "acompañ", "aquí"]),
    ]
    
    resultados = []
    tiempos = []
    
    print("\n2. Ejecutando pruebas...")
    print("-"*60)
    
    for i, (input_text, categoria, palabras_clave) in enumerate(pruebas, 1):
        try:
            # Enviar input
            inicio = time.time()
            output = servicio.responder(input_text, session_id=f"test-coherencia-{i}")
            tiempo = time.time() - inicio
            
            # Analizar output
            output_lower = output.lower()
            palabras_encontradas = [p for p in palabras_clave if p in output_lower]
            
            # Evaluar coherencia básica
            es_coherente = len(palabras_encontradas) > 0
            longitud_valida = 10 < len(output) < 500
            
            # Mostrar resultados
            print(f"\n[{i}] INPUT:  \"{input_text}\"")
            print(f"     Categoría: {categoria}")
            print(f"     OUTPUT: \"{output[:80]}...\"")
            print(f"     Tiempo: {tiempo:.2f}s")
            print(f"     Coherencia: {'✅' if es_coherente else '❌'} ({len(palabras_encontradas)}/{len(palabras_clave)} palabras clave)")
            print(f"     Longitud: {len(output)} chars {'✅' if longitud_valida else '⚠️'}")
            
            # Guardar resultados
            resultados.append({
                "input": input_text,
                "categoria": categoria,
                "output": output,
                "tiempo": tiempo,
                "coherente": es_coherente,
                "palabras_encontradas": palabras_encontradas,
                "palabras_esperadas": palabras_clave,
                "longitud": len(output),
                "longitud_valida": longitud_valida
            })
            
            tiempos.append(tiempo)
            
            # Pequeña pausa entre pruebas
            time.sleep(0.5)
            
        except Exception as e:
            print(f"\n[{i}] ❌ ERROR en \"{input_text}\": {e}")
            resultados.append({
                "input": input_text,
                "error": str(e),
                "coherente": False
            })
    
    return resultados, tiempos

def analizar_resultados(resultados, tiempos):
    """Analiza los resultados de las pruebas"""
    print("\n" + "="*60)
    print("📊 ANÁLISIS ESTADÍSTICO")
    print("="*60)
    
    pruebas_exitosas = [r for r in resultados if r.get("coherente", False)]
    pruebas_totales = len([r for r in resultados if "error" not in r])
    
    if pruebas_totales > 0:
        porcentaje_exito = (len(pruebas_exitosas) / pruebas_totales) * 100
        
        print(f"Pruebas ejecutadas: {pruebas_totales}")
        print(f"Pruebas exitosas: {len(pruebas_exitosas)}")
        print(f"Porcentaje de éxito: {porcentaje_exito:.1f}%")
        
        if tiempos:
            print(f"\n📈 TIEMPOS DE RESPUESTA:")
            print(f"  Promedio: {sum(tiempos)/len(tiempos):.2f}s")
            print(f"  Mínimo: {min(tiempos):.2f}s")
            print(f"  Máximo: {max(tiempos):.2f}s")
        
        # Evaluación general
        print(f"\n🎯 EVALUACIÓN GENERAL:")
        if porcentaje_exito >= 80:
            print("  ✅ COHERENCIA: EXCELENTE")
        elif porcentaje_exito >= 60:
            print("  ⚠️  COHERENCIA: ACEPTABLE")
        else:
            print("  ❌ COHERENCIA: DEFICIENTE")
        
        # Análisis por categoría
        print(f"\n🔍 ANÁLISIS POR CATEGORÍA:")
        categorias = {}
        for r in resultados:
            if "categoria" in r:
                cat = r["categoria"]
                if cat not in categorias:
                    categorias[cat] = {"total": 0, "exitosos": 0}
                categorias[cat]["total"] += 1
                if r.get("coherente", False):
                    categorias[cat]["exitosos"] += 1
        
        for cat, datos in categorias.items():
            if datos["total"] > 0:
                porcentaje = (datos["exitosos"] / datos["total"]) * 100
                print(f"  {cat}: {datos['exitosos']}/{datos['total']} ({porcentaje:.0f}%)")
    
    return porcentaje_exito if pruebas_totales > 0 else 0

def test_casos_limite():
    """Prueba inputs extremos/limite"""
    print("\n" + "="*60)
    print("⚠️  PRUEBA DE CASOS LÍMITE")
    print("="*60)
    
    try:
        from la_santisima_conversacional import crear_servicio
        servicio = crear_servicio(use_langchain=True, usar_sqlite=False)
        
        casos_limite = [
            ("", "vacío"),
            ("   ", "espacios"),
            ("H", "un_caracter"),
            ("a" * 1000, "muy_largo"),
            ("@#$%^&*()", "simbolos"),
            ("123456789", "numeros"),
            ("Hola\n¿Cómo\nestás?", "multilinea"),
        ]
        
        resultados_limite = []
        
        for input_text, tipo in casos_limite:
            try:
                inicio = time.time()
                output = servicio.responder(input_text, session_id="test-limite")
                tiempo = time.time() - inicio
                
                print(f"\n📤 INPUT ({tipo}): \"{input_text[:50]}{'...' if len(input_text) > 50 else ''}\"")
                print(f"📥 OUTPUT: \"{output[:80]}...\"")
                print(f"⏱️  Tiempo: {tiempo:.2f}s")
                print(f"📏 Longitud: {len(output)} chars")
                
                resultados_limite.append({
                    "tipo": tipo,
                    "input": input_text,
                    "output": output,
                    "tiempo": tiempo,
                    "longitud": len(output)
                })
                
                time.sleep(0.3)
                
            except Exception as e:
                print(f"\n📤 INPUT ({tipo}): \"{input_text[:50]}...\"")
                print(f"❌ ERROR: {e}")
        
        # Guardar casos límite
        with open("casos_limite.json", "w", encoding="utf-8") as f:
            json.dump(resultados_limite, f, indent=2, ensure_ascii=False)
            
        print(f"\n💾 Casos límite guardados en: casos_limite.json")
        
    except Exception as e:
        print(f"❌ Error en casos límite: {e}")

def guardar_resultados(resultados, tiempos, porcentaje_exito):
    """Guarda los resultados en archivo JSON"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"resultados_coherencia_{timestamp}.json"
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "resumen": {
                "total_pruebas": len(resultados),
                "exitosas": len([r for r in resultados if r.get("coherente", False)]),
                "porcentaje_exito": porcentaje_exito,
                "tiempo_promedio": sum(tiempos)/len(tiempos) if tiempos else 0
            },
            "detalles": resultados
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Resultados guardados en: {filename}")
    return filename

def main():
    """Función principal"""
    print("🚀 SISTEMA DE VALIDACIÓN INPUT/OUTPUT")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Ejecutar prueba principal
    resultados, tiempos = test_coherencia_directa()
    
    if resultados:
        # Analizar resultados
        porcentaje_exito = analizar_resultados(resultados, tiempos)
        
        # Guardar resultados
        filename = guardar_resultados(resultados, tiempos, porcentaje_exito)
        
        # Ejecutar casos límite (opcional)
        try:
            test_casos_limite()
        except:
            print("\n⚠️  Casos límite omitidos por errores")
    
    print("\n" + "="*60)
    print("📈 RESUMEN RÁPIDO:")
    print("="*60)
    
    print("""
PARA INTERPRETAR:
• > 80% éxito → ✅ Excelente coherencia
• 60-80% éxito → ⚠️  Coherencia aceptable  
• < 60% éxito → ❌ Problemas de coherencia

• < 2s promedio → ⚡ Excelente velocidad
• 2-5s promedio → 🐢 Velocidad aceptable
• > 5s promedio → 🐌 Velocidad lenta
    """)
    
    print(f"\n🕐 Prueba completada: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()