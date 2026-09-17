#!/usr/bin/env python3
"""Prueba del flujo completo de usuario en modo producción."""

import json
import time
import httpx
import sys
from pathlib import Path

BASE_URL = "http://localhost:8000"

def test_flujo_completo():
    """Prueba registro -> consentimiento -> sesión -> mensaje."""
    print("=== Prueba de flujo completo de usuario ===")
    
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)
    
    try:
        # 1. Registrar dispositivo (sin auth)
        print("1. Registrando dispositivo...")
        resp = client.post("/api/v1/dispositivos", json={})
        assert resp.status_code == 200, f"Registro falló: {resp.status_code}"
        dispositivo = resp.json()
        device_id = dispositivo["device_id"]
        device_token = dispositivo["device_token"]
        print(f"   Device ID: {device_id}")
        print(f"   Device Token: {device_token[:20]}...")
        
        # Configurar headers con token para siguientes llamadas
        headers = {"Authorization": f"Bearer {device_token}"}
        
        # 2. Aceptar consentimiento (versión actual v1)
        print("2. Aceptando consentimiento...")
        resp = client.post(
            "/api/v1/dispositivos/consentimiento",
            json={"version": "v1"},
            headers=headers
        )
        assert resp.status_code == 204, f"Consentimiento falló: {resp.status_code}"
        
        # 3. Crear sesión
        print("3. Creando sesión...")
        resp = client.post("/api/v1/sesiones", headers=headers)
        assert resp.status_code == 200, f"Crear sesión falló: {resp.status_code}"
        sesion = resp.json()
        session_id = sesion["session_id"]
        print(f"   Session ID: {session_id}")
        
        # 4. Enviar mensaje (con sesión)
        print("4. Enviando mensaje de prueba...")
        resp = client.post(
            "/api/v1/mensajes",
            json={
                "session_id": session_id,
                "mensaje": "Hola, ¿puedes darme una bendición?"
            },
            headers=headers
        )
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            mensaje_resp = resp.json()
            print(f"   Respuesta ID: {mensaje_resp.get('id', 'N/A')}")
            print(f"   ¿Streaming?: {mensaje_resp.get('streaming', False)}")
            print("   ✓ Mensaje enviado exitosamente")
        elif resp.status_code == 503:
            print("   ⚠️ Servicio degradado (LLM no disponible)")
        else:
            print(f"   ❌ Error inesperado: {resp.text}")
        
        # 5. Verificar health/ready
        print("5. Verificando health endpoints...")
        resp = client.get("/health")
        assert resp.status_code == 200
        print(f"   Health: {resp.json()['status']}")
        
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        print(f"   Ready: {resp.json()['status']}")
        
        # 6. Verificar métricas
        print("6. Verificando métricas...")
        resp = client.get("/metrics/health")
        if resp.status_code == 200:
            metrics = resp.json()
            print(f"   LLM Adapter: {metrics.get('llm_adapter_status', 'N/A')}")
            print(f"   DB Backend: {metrics.get('db_backend', 'N/A')}")
            print(f"   Última purga: {metrics.get('ultima_purga', 'N/A')}")
        
        print("\n=== Prueba completada ===")
        return True
        
    except Exception as e:
        print(f"\n❌ Error durante la prueba: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.close()

if __name__ == "__main__":
    import subprocess
    import signal
    import os
    
    # Verificar si el servidor está corriendo
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=2.0)
        if resp.status_code == 200:
            print("Servidor ya está corriendo en localhost:8000")
            server_process = None
        else:
            raise ConnectionError("Health check falló")
    except:
        print("Iniciando servidor local...")
        # Iniciar servidor en background
        server_process = subprocess.Popen(
            [
                "uvicorn", 
                "la_santisima_conversacional.presentation.http_api:app",
                "--host", "127.0.0.1",
                "--port", "8000",
                "--log-level", "error"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(5)  # Esperar a que el servidor arranque
    
    try:
        success = test_flujo_completo()
        sys.exit(0 if success else 1)
    finally:
        if 'server_process' in locals() and server_process:
            print("\nDeteniendo servidor...")
            server_process.terminate()
            server_process.wait()