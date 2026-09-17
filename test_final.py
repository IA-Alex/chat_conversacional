#!/usr/bin/env python3
"""
Prueba FINAL - Inputs/Outputs reales del modelo
"""

import requests
import json
import time
from datetime import datetime

def prueba_inputs_outputs():
    """Envía inputs al modelo y captura outputs"""
    print("🤖 PRUEBA REAL DEL MODELO")
    print("="*50)
    
    base = "http://127.0.0.1:8001"
    s = requests.Session()
    
    try:
        # 1. Registrar
        reg = s.post(f"{base}/api/v1/dispositivos")
        if reg.status_code != 200:
            print(f"❌ Error registro: {reg.status_code}")
            return []
        
        token = reg.json()["device_token"]
        print("✅ Dispositivo registrado")
        
        # 2. Consentimiento
        s.post(
            f"{base}/api/v1/dispositivos/consentimiento",
            headers={"Authorization": f"Bearer {token}"},
            json={"version": "v1"}
        )
        print("✅ Consentimiento aceptado")
        
        # 3. Sesión
        ses = s.post(
            f"{base}/api/v1/sesiones",
            headers={"Authorization": f"Bearer {token}"}
        )
        session_id = ses.json()["session_id"]
        print(f"✅ Sesión: {session_id[:12]}...")
        
        # 4. Enviar mensajes
        print("\n📤 ENVIANDO INPUTS AL MODELO:")
        print("-"*50)
        
        tests = [
            "Hola",
            "¿Cómo estás?",
            "Estoy triste",
            "Necesito ayuda",
            "Gracias",
            "¿Qué eres?",
            "Tengo miedo",
            "¿Puedes protegerme?",
            "¿Cómo rezo?",
            "Me siento solo"
        ]
        
        resultados = []
        
        for i, input_text in enumerate(tests, 1):
            try:
                print(f"\n[{i}] 📤 Input: \"{input_text}\"")
                
                inicio = time.time()
                resp = s.post(
                    f"{base}/api/v1/mensajes",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"session_id": session_id, "mensaje": input_text},
                    timeout=30
                )
                tiempo = time.time() - inicio
                
                if resp.status_code == 200:
                    output = resp.json()["respuesta"]
                    
                    print(f"   ✅ Output recibido en {tiempo:.2f}s")
                    print(f"   📥 \"{output[:80]}...\"")
                    print(f"   📏 {len(output)} chars")
                    
                    resultados.append({
                        "input": input_text,
                        "output": output,
                        "tiempo": tiempo,
                        "longitud": len(output),
                        "exito": True
                    })
                    
                else:
                    print(f"   ❌ Error {resp.status_code}")
                    resultados.append({
                        "input": input_text,
                        "error": f"HTTP {resp.status_code}",
                        "exito": False
                    })
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                resultados.append({
                    "input": input_text,
                    "error": str(e),
                    "exito": False
                })
        
        return resultados
        
    except Exception as e:
        print(f"\n❌ Error general: {e}")
        return []

def main():
    print(f"🕐 Inicio: {datetime.now().strftime('%H:%M:%S')}")
    
    resultados = prueba_inputs_outputs()
    
    if resultados:
        # Análisis
        print("\n" + "="*50)
        print("📊 ANÁLISIS FINAL")
        print("="*50)
        
        exitos = sum(1 for r in resultados if r.get("exito", False))
        total = len(resultados)
        
        if total > 0:
            porcentaje = (exitos / total) * 100
            print(f"Pruebas exitosas: {exitos}/{total} ({porcentaje:.1f}%)")
            
            tiempos = [r["tiempo"] for r in resultados if r.get("exito", False)]
            if tiempos:
                promedio = sum(tiempos) / len(tiempos)
                print(f"Tiempo promedio: {promedio:.2f}s")
                
                if promedio < 2:
                    print("Velocidad: ⚡ EXCELENTE")
                elif promedio < 5:
                    print("Velocidad: 🐢 ACEPTABLE")
                else:
                    print("Velocidad: 🐌 LENTA")
            
            # Evaluación
            print(f"\n🎯 EVALUACIÓN DEL MODELO:")
            if porcentaje >= 80:
                print("   ✅ COHERENCIA EXCELENTE")
            elif porcentaje >= 60:
                print("   ⚠️  COHERENCIA ACEPTABLE")
            else:
                print("   ❌ COHERENCIA DEFICIENTE")
        
        # Guardar
        with open("resultados_finales.json", "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "resultados": resultados,
                "resumen": {
                    "total_pruebas": total,
                    "exitosas": exitos,
                    "porcentaje_exito": porcentaje if total > 0 else 0,
                    "tiempo_promedio": promedio if tiempos else 0
                }
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Resultados guardados en: resultados_finales.json")
    
    print(f"\n🕐 Fin: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()