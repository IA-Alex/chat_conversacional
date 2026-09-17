#!/usr/bin/env python3
"""
Validación MINIMALISTA de Inputs/Outputs
Solo mide coherencia básica del modelo
"""

import time
import json
from datetime import datetime

def test_minimalista():
    """Prueba minimalista de coherencia"""
    print("🎯 VALIDACIÓN INPUTS/OUTPUTS")
    print("="*50)
    
    # Intentar importar el servicio
    try:
        from la_santisima_conversacional import crear_servicio
        servicio = crear_servicio(use_langchain=True, usar_sqlite=False)
        print("✅ Servicio listo")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Configura DEEPINFRA_API_KEY en .env")
        return [], []
    
    # Inputs de prueba (solo los esenciales)
    pruebas = [
        ("Hola", ["hola", "saludo", "bienvenido"]),
        ("Estoy triste", ["triste", "acompañ", "escuch"]),
        ("Necesito ayuda", ["ayuda", "apoyo", "aquí"]),
        ("¿Qué eres?", ["muerte", "santísima", "entidad"]),
        ("Tengo miedo", ["miedo", "tranquilo", "acompañ"]),
    ]
    
    resultados = []
    tiempos = []
    
    print("\n📊 EJECUTANDO PRUEBAS:")
    print("-"*50)
    
    for i, (input_text, palabras_clave) in enumerate(pruebas, 1):
        try:
            # Medir tiempo
            inicio = time.time()
            output = servicio.responder(input_text, session_id=f"test-{i}")
            tiempo = time.time() - inicio
            
            # Verificar coherencia básica
            output_lower = output.lower()
            palabras_encontradas = [p for p in palabras_clave if p in output_lower]
            es_coherente = len(palabras_encontradas) > 0
            
            # Mostrar resultados
            status = "✅" if es_coherente else "❌"
            print(f"{status} [{i}] Input:  \"{input_text}\"")
            print(f"     Output: \"{output[:60]}...\"")
            print(f"     Tiempo: {tiempo:.2f}s | Coherente: {es_coherente}")
            
            # Guardar
            resultados.append({
                "input": input_text,
                "output": output,
                "tiempo": tiempo,
                "coherente": es_coherente,
                "palabras_encontradas": palabras_encontradas,
                "palabras_clave": palabras_clave
            })
            tiempos.append(tiempo)
            
            time.sleep(0.3)
            
        except Exception as e:
            print(f"❌ [{i}] Error: \"{input_text}\" → {e}")
            resultados.append({
                "input": input_text,
                "error": str(e),
                "coherente": False
            })
    
    return resultados, tiempos

def analizar_minimalista(resultados, tiempos):
    """Análisis rápido"""
    if not resultados:
        return
    
    print("\n" + "="*50)
    print("📈 RESULTADOS:")
    print("="*50)
    
    exitos = sum(1 for r in resultados if r.get("coherente", False))
    total = len(resultados)
    
    print(f"Pruebas: {exitos}/{total} exitosas")
    
    if exitos > 0:
        porcentaje = (exitos / total) * 100
        print(f"Porcentaje: {porcentaje:.1f}%")
        
        if porcentaje >= 80:
            print("Evaluación: ✅ EXCELENTE")
        elif porcentaje >= 60:
            print("Evaluación: ⚠️  ACEPTABLE")
        else:
            print("Evaluación: ❌ DEFICIENTE")
    
    if tiempos:
        promedio = sum(tiempos) / len(tiempos)
        print(f"\n⏱️  Tiempo promedio: {promedio:.2f}s")
        if promedio < 2:
            print("Velocidad: ⚡ RÁPIDA")
        elif promedio < 5:
            print("Velocidad: 🐢 NORMAL")
        else:
            print("Velocidad: 🐌 LENTA")

def main():
    """Función principal minimalista"""
    print(f"🕐 Inicio: {datetime.now().strftime('%H:%M:%S')}")
    
    resultados, tiempos = test_minimalista()
    
    if resultados:
        analizar_minimalista(resultados, tiempos)
        
        # Guardar solo si hay resultados
        with open("validacion_inputs_outputs.json", "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "resultados": resultados,
                "resumen": {
                    "exitos": sum(1 for r in resultados if r.get("coherente", False)),
                    "total": len(resultados),
                    "tiempo_promedio": sum(tiempos)/len(tiempos) if tiempos else 0
                }
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Resultados guardados en: validacion_inputs_outputs.json")
    
    print(f"\n🕐 Fin: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()