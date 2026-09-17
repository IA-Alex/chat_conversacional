#!/usr/bin/env python3
"""
Prueba mínima - 1 minuto máximo
Solo verifica que funciona y mide tiempos básicos
"""

import time
import requests

def test_minimo():
    print("🚀 PRUEBA MÍNIMA (30 segundos)")
    
    # 1. Verificar servidor
    try:
        resp = requests.get("http://127.0.0.1:8000/health", timeout=5)
        print(f"✅ Servidor activo: {resp.status_code}")
    except:
        print("❌ Servidor NO disponible")
        return
    
    # 2. Flujo completo rápido
    session = requests.Session()
    
    # Registrar
    try:
        reg = session.post("http://127.0.0.1:8000/api/v1/dispositivos")
        token = reg.json()["device_token"]
        print("✅ Dispositivo registrado")
    except:
        print("❌ Error registro")
        return
    
    # Sesión
    try:
        ses = session.post(
            "http://127.0.0.1:8000/api/v1/sesiones",
            headers={"Authorization": f"Bearer {token}"}
        )
        session_id = ses.json()["session_id"]
        print(f"✅ Sesión: {session_id[:8]}...")
    except:
        print("❌ Error sesión")
        return
    
    # 3. Enviar 3 mensajes rápidos
    mensajes = [
        "Hola",
        "¿Cómo estás?",
        "Gracias"
    ]
    
    tiempos = []
    
    for msg in mensajes:
        try:
            inicio = time.time()
            resp = session.post(
                "http://127.0.0.1:8000/api/v1/mensajes",
                json={"session_id": session_id, "mensaje": msg},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30
            )
            t = time.time() - inicio
            tiempos.append(t)
            
            print(f"\n📤 '{msg}' → {t:.2f}s")
            respuesta = resp.json()["respuesta"]
            print(f"📥 '{respuesta[:60]}...'")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            tiempos.append(None)
    
    # 4. Resultado
    tiempos_validos = [t for t in tiempos if t is not None]
    if tiempos_validos:
        promedio = sum(tiempos_validos) / len(tiempos_validos)
        print(f"\n📊 PROMEDIO: {promedio:.2f}s")
        
        if promedio < 3:
            print("🎯 VELOCIDAD: BUENA")
        elif promedio < 6:
            print("⚠️  VELOCIDAD: ACEPTABLE")
        else:
            print("🐌 VELOCIDAD: LENTA")
    else:
        print("\n❌ Ningún mensaje exitoso")

if __name__ == "__main__":
    test_minimo()