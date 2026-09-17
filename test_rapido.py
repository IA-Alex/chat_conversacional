#!/usr/bin/env python3
"""
Prueba rápida para La Santísima Muerte Conversacional

Mide lo básico en 2-3 minutos máximo:
1. ¿El servidor responde?
2. Tiempo de respuesta promedio
3. Coherencia básica

Uso:
    python test_rapido.py
"""

import json
import time
import statistics
import requests
from typing import List, Tuple
from datetime import datetime

def test_rapido(base_url: str = "http://127.0.0.1:8000"):
    """Ejecuta prueba rápida"""
    print("="*60)
    print("PRUEBA RÁPIDA - LA SANTÍSIMA MUERTE")
    print(f"Inicio: {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)
    
    session = requests.Session()
    resultados = []
    
    # 1. Verificar salud
    try:
        health = session.get(f"{base_url}/health")
        print(f"✅ Salud del servidor: {health.status_code}")
    except:
        print("❌ Servidor no responde")
        return
    
    # 2. Registrar dispositivo
    try:
        reg = session.post(f"{base_url}/api/v1/dispositivos")
        device_data = reg.json()
        device_token = device_data["device_token"]
        print(f"✅ Dispositivo registrado")
    except:
        print("❌ Error registrando dispositivo")
        return
    
    # 3. Aceptar consentimiento
    try:
        session.post(
            f"{base_url}/api/v1/dispositivos/consentimiento",
            json={"version": "1.0"},
            headers={"Authorization": f"Bearer {device_token}"}
        )
        print(f"✅ Consentimiento aceptado")
    except:
        print("⚠️  Error en consentimiento (continuando)")
    
    # 4. Crear sesión
    try:
        sesion_resp = session.post(
            f"{base_url}/api/v1/sesiones",
            headers={"Authorization": f"Bearer {device_token}"}
        )
        session_id = sesion_resp.json()["session_id"]
        print(f"✅ Sesión creada: {session_id[:8]}...")
    except:
        print("❌ Error creando sesión")
        return
    
    # 5. Enviar preguntas básicas (solo 5 para ser rápido)
    preguntas = [
        "Hola, ¿cómo estás?",
        "¿Puedes ayudarme?",
        "Estoy triste",
        "Gracias",
    ]
    
    tiempos = []
    
    for i, pregunta in enumerate(preguntas, 1):
        try:
            inicio = time.time()
            respuesta = session.post(
                f"{base_url}/api/v1/mensajes",
                json={"session_id": session_id, "mensaje": pregunta},
                headers={"Authorization": f"Bearer {device_token}"}
            )
            tiempo = time.time() - inicio
            tiempos.append(tiempo)
            
            data = respuesta.json()
            print(f"\n[{i}] Pregunta: {pregunta}")
            print(f"    Tiempo: {tiempo:.2f}s")
            print(f"    Respuesta: {data['respuesta'][:80]}...")
            
            resultados.append({
                "pregunta": pregunta,
                "tiempo": tiempo,
                "respuesta_len": len(data['respuesta'])
            })
            
            time.sleep(0.3)
            
        except Exception as e:
            print(f"\n[{i}] Error: {e}")
            tiempos.append(None)
    
    # 6. Análisis rápido
    tiempos_validos = [t for t in tiempos if t is not None]
    
    print("\n" + "="*60)
    print("RESULTADOS RÁPIDOS")
    print("="*60)
    
    if tiempos_validos:
        promedio = statistics.mean(tiempos_validos)
        print(f"Tiempo promedio: {promedio:.2f}s")
        print(f"Mejor tiempo: {min(tiempos_validos):.2f}s")
        print(f"Peor tiempo: {max(tiempos_validos):.2f}s")
        
        if promedio < 2:
            print("✅ RENDIMIENTO EXCELENTE")
        elif promedio < 5:
            print("⚠️  RENDIMIENTO ACEPTABLE")
        else:
            print("❌ RENDIMIENTO LENTO")
    
    print(f"\nFin: {datetime.now().strftime('%H:%M:%S')}")
    
    # Guardar resultados
    with open("test_rapido_resultados.json", "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "promedio_tiempo": promedio if tiempos_validos else 0,
            "resultados": resultados
        }, f, indent=2, ensure_ascii=False)
    
    print("Resultados guardados en: test_rapido_resultados.json")

if __name__ == "__main__":
    test_rapido()