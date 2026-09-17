#!/usr/bin/env python3
"""
Prueba de coherencia vía HTTP - Inputs/Outputs directos
"""

import requests
import json
import time
from datetime import datetime

class TesterHTTP:
    def __init__(self, base_url="http://127.0.0.1:8001"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def flujo_completo(self, input_text: str):
        """Realiza flujo completo: registro → sesión → mensaje"""
        try:
            # 1. Registrar dispositivo
            reg_resp = self.session.post(f"{self.base_url}/api/v1/dispositivos")
            if reg_resp.status_code != 200:
                return None, f"Error registro: {reg_resp.status_code}"
            
            device_data = reg_resp.json()
            device_token = device_data["device_token"]
            
            # 2. Crear sesión
            ses_resp = self.session.post(
                f"{self.base_url}/api/v1/sesiones",
                headers={"Authorization": f"Bearer {device_token}"}
            )
            if ses_resp.status_code != 200:
                return None, f"Error sesión: {ses_resp.status_code}"
            
            session_data = ses_resp.json()
            session_id = session_data["session_id"]
            
            # 3. Enviar mensaje
            msg_resp = self.session.post(
                f"{self.base_url}/api/v1/mensajes",
                headers={"Authorization": f"Bearer {device_token}"},
                json={"session_id": session_id, "mensaje": input_text}
            )
            
            if msg_resp.status_code != 200:
                return None, f"Error mensaje: {msg_resp.status_code}"
            
            msg_data = msg_resp.json()
            return msg_data["respuesta"], None
            
        except Exception as e:
            return None, str(e)

def test_coherencia_http():
    """Prueba de coherencia via HTTP"""
    print("🌐 PRUEBA HTTP - INPUTS/OUTPUTS")
    print("="*60)
    
    tester = TesterHTTP("http://127.0.0.1:8001")
    
    # Pruebas simples y directas
    pruebas = [
        ("Hola", ["hola", "saludo", "bienvenido", "gracias"]),
        ("¿Cómo estás?", ["bien", "aquí", "contigo", "acompañ"]),
        ("Estoy triste", ["triste", "acompañ", "escuch", "entend"]),
        ("Necesito ayuda", ["ayuda", "apoyo", "aquí", "puedo"]),
        ("Gracias", ["gracias", "bienvenido", "aquí", "siempre"]),
        ("¿Qué eres?", ["muerte", "santísima", "entidad", "espíritu"]),
        ("Tengo miedo", ["miedo", "tranquilo", "acompañ", "protección"]),
        ("¿Puedes protegerme?", ["protección", "cuidar", "seguro", "amparo"]),
        ("¿Cómo rezo?", ["oración", "rezar", "ritual", "plegaria"]),
        ("Me siento solo", ["solo", "acompañ", "aquí", "siempre"]),
    ]
    
    resultados = []
    tiempos = []
    
    print("🚀 Enviando preguntas al modelo...")
    print("-"*60)
    
    for i, (input_text, palabras_clave) in enumerate(pruebas, 1):
        try:
            print(f"\n[{i}] 📤 Enviando: \"{input_text}\"")
            
            inicio = time.time()
            output, error = tester.flujo_completo(input_text)
            tiempo = time.time() - inicio
            
            if error:
                print(f"   ❌ Error: {error}")
                resultados.append({
                    "input": input_text,
                    "error": error,
                    "coherente": False
                })
            else:
                # Analizar coherencia
                output_lower = output.lower()
                palabras_encontradas = [p for p in palabras_clave if p in output_lower]
                es_coherente = len(palabras_encontradas) > 0
                
                # Mostrar resultados
                status = "✅" if es_coherente else "❌"
                print(f"   {status} Recibido en {tiempo:.2f}s")
                print(f"   📥 Respuesta: \"{output[:100]}...\"")
                print(f"   🔍 Coherencia: {es_coherente} ({len(palabras_encontradas)}/{len(palabras_clave)} palabras)")
                
                # Guardar
                resultados.append({
                    "input": input_text,
                    "output": output,
                    "tiempo": tiempo,
                    "coherente": es_coherente,
                    "palabras_encontradas": palabras_encontradas,
                    "palabras_clave": palabras_clave,
                    "longitud": len(output)
                })
                tiempos.append(tiempo)
            
            # Pequeña pausa
            time.sleep(0.5)
            
        except Exception as e:
            print(f"\n[{i}] ❌ Error general: {e}")
            resultados.append({
                "input": input_text,
                "error": str(e),
                "coherente": False
            })
    
    return resultados, tiempos

def analizar_resultados_http(resultados, tiempos):
    """Análisis de resultados HTTP"""
    print("\n" + "="*60)
    print("📊 ANÁLISIS COMPLETO")
    print("="*60)
    
    exitos = sum(1 for r in resultados if r.get("coherente", False))
    total = len([r for r in resultados if "error" not in r])
    
    if total > 0:
        porcentaje = (exitos / total) * 100
        
        print(f"📈 ESTADÍSTICAS:")
        print(f"   Pruebas ejecutadas: {total}")
        print(f"   Respuestas coherentes: {exitos}")
        print(f"   Porcentaje de éxito: {porcentaje:.1f}%")
        
        if tiempos:
            print(f"\n⏱️  TIEMPOS:")
            print(f"   Promedio: {sum(tiempos)/len(tiempos):.2f}s")
            print(f"   Mínimo: {min(tiempos):.2f}s")
            print(f"   Máximo: {max(tiempos):.2f}s")
        
        print(f"\n🎯 EVALUACIÓN:")
        if porcentaje >= 80:
            print("   ✅ COHERENCIA EXCELENTE")
        elif porcentaje >= 60:
            print("   ⚠️  COHERENCIA ACEPTABLE")
        else:
            print("   ❌ COHERENCIA DEFICIENTE")
        
        # Detalles por prueba
        print(f"\n🔍 DETALLE POR PRUEBA:")
        for i, r in enumerate(resultados, 1):
            if "output" in r:
                status = "✅" if r.get("coherente", False) else "❌"
                print(f"   [{i}] {status} \"{r['input']}\" → {r['tiempo']:.2f}s")
    
    return porcentaje if total > 0 else 0

def main():
    """Función principal"""
    print(f"🕐 Inicio: {datetime.now().strftime('%H:%M:%S')}")
    print(f"🌍 Conectando a: http://127.0.0.1:8001")
    
    # Verificar conexión primero
    try:
        resp = requests.get("http://127.0.0.1:8001/health", timeout=5)
        if resp.status_code == 200:
            print("✅ Servidor HTTP activo")
        else:
            print(f"⚠️  Servidor responde con código: {resp.status_code}")
    except:
        print("❌ No se puede conectar al servidor")
        print("💡 Verifica que ./start.sh esté ejecutándose")
        return
    
    # Ejecutar pruebas
    resultados, tiempos = test_coherencia_http()
    
    if resultados:
        porcentaje = analizar_resultados_http(resultados, tiempos)
        
        # Guardar resultados
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"resultados_http_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "servidor": "http://127.0.0.1:8001",
                "resumen": {
                    "total_pruebas": len(resultados),
                    "exitosas": sum(1 for r in resultados if r.get("coherente", False)),
                    "porcentaje_exito": porcentaje,
                    "tiempo_promedio": sum(tiempos)/len(tiempos) if tiempos else 0
                },
                "detalles": resultados
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Resultados guardados en: {filename}")
    
    print(f"\n🕐 Fin: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()