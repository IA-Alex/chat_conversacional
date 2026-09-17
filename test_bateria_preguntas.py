#!/usr/bin/env python3
"""
Batería de pruebas para La Santísima Muerte Conversacional

Mide:
1. Coherencia de respuestas
2. Tiempo de respuesta promedio
3. Robustez ante diferentes tipos de entrada
4. Comportamiento con sesiones múltiples

Uso:
    python test_bateria_preguntas.py
"""

import json
import time
import statistics
import requests
from typing import Dict, List, Tuple
from datetime import datetime

class TesterConversacional:
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def registrar_dispositivo(self) -> str:
        """Registra un nuevo dispositivo y obtiene token"""
        url = f"{self.base_url}/api/v1/dispositivos"
        response = self.session.post(url)
        response.raise_for_status()
        data = response.json()
        return data["device_token"]
    
    def obtener_session_id(self, device_token: str) -> str:
        """Crea una nueva sesión para el dispositivo"""
        url = f"{self.base_url}/api/v1/sesiones"
        headers = {"Authorization": f"Bearer {device_token}"}
        response = self.session.post(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["session_id"]
    
    def aceptar_consentimiento(self, device_token: str, version: str = "1.0"):
        """Acepta el consentimiento de privacidad"""
        url = f"{self.base_url}/api/v1/dispositivos/consentimiento"
        headers = {"Authorization": f"Bearer {device_token}"}
        payload = {"version": version}
        response = self.session.post(url, json=payload, headers=headers)
        response.raise_for_status()
    
    def enviar_mensaje(self, session_id: str, mensaje: str, device_token: str) -> Tuple[str, float]:
        """Envía un mensaje y mide el tiempo de respuesta"""
        url = f"{self.base_url}/api/v1/mensajes"
        headers = {"Authorization": f"Bearer {device_token}"}
        payload = {"session_id": session_id, "mensaje": mensaje}
        
        inicio = time.time()
        response = self.session.post(url, json=payload, headers=headers)
        tiempo_respuesta = time.time() - inicio
        
        response.raise_for_status()
        data = response.json()
        return data["respuesta"], tiempo_respuesta
    
    def test_coherencia_basica(self, num_preguntas: int = 10) -> Dict:
        """Prueba básica de coherencia con preguntas variadas"""
        print("\n" + "="*60)
        print("TEST 1: Coherencia Básica")
        print("="*60)
        
        resultados = []
        device_token = self.registrar_dispositivo()
        self.aceptar_consentimiento(device_token)
        session_id = self.obtener_session_id(device_token)
        
        preguntas = [
            "Hola, ¿cómo estás?",
            "¿Qué eres?",
            "¿Cómo puedes ayudarme?",
            "Estoy triste, ¿qué puedo hacer?",
            "¿Me puedes dar esperanza?",
            "Necesito protección, ¿qué debo hacer?",
            "¿Cómo rezo correctamente?",
            "¿Qué significa tener fe?",
            "Me siento solo, ¿me acompañarías?",
            "Gracias por escucharme"
        ]
        
        for i, pregunta in enumerate(preguntas[:num_preguntas], 1):
            try:
                respuesta, tiempo = self.enviar_mensaje(session_id, pregunta, device_token)
                print(f"\nPregunta {i}: {pregunta}")
                print(f"Respuesta: {respuesta[:100]}...")
                print(f"Tiempo: {tiempo:.2f}s")
                resultados.append({
                    "pregunta": pregunta,
                    "respuesta": respuesta,
                    "tiempo": tiempo,
                    "longitud_respuesta": len(respuesta)
                })
                time.sleep(0.5)
            except Exception as e:
                print(f"Error en pregunta {i}: {e}")
                resultados.append({
                    "pregunta": pregunta,
                    "error": str(e),
                    "tiempo": None
                })
        
        tiempos_validos = [r["tiempo"] for r in resultados if r.get("tiempo") is not None]
        return {
            "test": "coherencia_basica",
            "resultados": resultados,
            "tiempo_promedio": statistics.mean(tiempos_validos) if tiempos_validos else 0,
            "tiempo_total": sum(tiempos_validos) if tiempos_validos else 0
        }
    
    def test_robustez_entradas(self) -> Dict:
        """Prueba robustez con diferentes tipos de entrada"""
        print("\n" + "="*60)
        print("TEST 2: Robustez de Entradas")
        print("="*60)
        
        resultados = []
        device_token = self.registrar_dispositivo()
        self.aceptar_consentimiento(device_token)
        session_id = self.obtener_session_id(device_token)
        
        entradas = [
            ("Entrada vacía", ""),
            ("Espacios", "   "),
            ("Muy corta", "Hola"),
            ("Larga", "Esta es una pregunta muy larga "*10),
            ("Con emojis", "Hola 😊 ¿me ayudas? 🙏"),
            ("Con caracteres especiales", "@#!$%^&*()"),
            ("Pregunta compleja", "Estoy pasando por un momento muy difícil en mi vida, " + 
             "mi familia está pasando por problemas económicos y de salud, " +
             "y no sé cómo seguir adelante. ¿Qué me recomiendas hacer?"),
        ]
        
        for nombre, entrada in entradas:
            try:
                respuesta, tiempo = self.enviar_mensaje(session_id, entrada, device_token)
                print(f"\nEntrada: {nombre}")
                print(f"Contenido: '{entrada[:50]}...'" if len(entrada) > 50 else f"Contenido: '{entrada}'")
                print(f"Respuesta: {respuesta[:100]}..." if respuesta else "Sin respuesta")
                print(f"Tiempo: {tiempo:.2f}s")
                resultados.append({
                    "tipo": nombre,
                    "entrada": entrada,
                    "respuesta": respuesta,
                    "tiempo": tiempo,
                    "exito": True
                })
            except Exception as e:
                print(f"\nError con entrada '{nombre}': {e}")
                resultados.append({
                    "tipo": nombre,
                    "entrada": entrada,
                    "error": str(e),
                    "tiempo": None,
                    "exito": False
                })
            time.sleep(0.5)
        
        return {
            "test": "robustez_entradas",
            "resultados": resultados,
            "exitosos": sum(1 for r in resultados if r["exito"]),
            "total": len(resultados)
        }
    
    def test_multiples_sesiones(self, num_sesiones: int = 3) -> Dict:
        """Prueba con múltiples sesiones concurrentes"""
        print("\n" + "="*60)
        print("TEST 3: Múltiples Sesiones")
        print("="*60)
        
        resultados = []
        
        for i in range(num_sesiones):
            print(f"\n--- Sesión {i+1} ---")
            try:
                device_token = self.registrar_dispositivo()
                self.aceptar_consentimiento(device_token)
                session_id = self.obtener_session_id(device_token)
                
                mensaje = f"Hola, soy el usuario {i+1}"
                respuesta, tiempo = self.enviar_mensaje(session_id, mensaje, device_token)
                
                print(f"Mensaje: {mensaje}")
                print(f"Respuesta: {respuesta[:100]}...")
                print(f"Tiempo: {tiempo:.2f}s")
                
                resultados.append({
                    "sesion": i+1,
                    "respuesta": respuesta,
                    "tiempo": tiempo,
                    "exito": True
                })
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Error en sesión {i+1}: {e}")
                resultados.append({
                    "sesion": i+1,
                    "error": str(e),
                    "exito": False
                })
        
        return {
            "test": "multiples_sesiones",
            "resultados": resultados,
            "exitosos": sum(1 for r in resultados if r["exito"]),
            "total": len(resultados)
        }
    
    def test_tiempo_respuesta_sustentado(self, num_mensajes: int = 20) -> Dict:
        """Prueba de tiempo de respuesta sostenido"""
        print("\n" + "="*60)
        print("TEST 4: Tiempo de Respuesta Sostenido")
        print("="*60)
        
        device_token = self.registrar_dispositivo()
        self.aceptar_consentimiento(device_token)
        session_id = self.obtener_session_id(device_token)
        
        tiempos = []
        
        for i in range(num_mensajes):
            mensaje = f"Mensaje de prueba {i+1} para medir tiempos"
            try:
                respuesta, tiempo = self.enviar_mensaje(session_id, mensaje, device_token)
                tiempos.append(tiempo)
                print(f"Mensaje {i+1}: {tiempo:.2f}s")
                time.sleep(0.3)
            except Exception as e:
                print(f"Error en mensaje {i+1}: {e}")
                tiempos.append(None)
        
        tiempos_validos = [t for t in tiempos if t is not None]
        
        return {
            "test": "tiempo_respuesta_sustentado",
            "num_mensajes": num_mensajes,
            "tiempos": tiempos,
            "promedio": statistics.mean(tiempos_validos) if tiempos_validos else 0,
            "maximo": max(tiempos_validos) if tiempos_validos else 0,
            "minimo": min(tiempos_validos) if tiempos_validos else 0,
            "desviacion": statistics.stdev(tiempos_validos) if len(tiempos_validos) > 1 else 0
        }
    
    def ejecutar_bateria_completa(self) -> Dict:
        """Ejecuta toda la batería de pruebas"""
        print("="*60)
        print("BATERÍA DE PRUEBAS - LA SANTÍSIMA MUERTE CONVERSACIONAL")
        print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        resultados = {}
        
        try:
            resultados["coherencia"] = self.test_coherencia_basica()
            resultados["robustez"] = self.test_robustez_entradas()
            resultados["sesiones"] = self.test_multiples_sesiones()
            resultados["tiempos"] = self.test_tiempo_respuesta_sustentado()
            
            print("\n" + "="*60)
            print("RESUMEN FINAL")
            print("="*60)
            
            if "coherencia" in resultados:
                print(f"Coherencia: {len(resultados['coherencia']['resultados'])} preguntas procesadas")
                print(f"  Tiempo promedio: {resultados['coherencia']['tiempo_promedio']:.2f}s")
            
            if "robustez" in resultados:
                print(f"Robustez: {resultados['robustez']['exitosos']}/{resultados['robustez']['total']} exitosos")
            
            if "sesiones" in resultados:
                print(f"Sesiones: {resultados['sesiones']['exitosos']}/{resultados['sesiones']['total']} exitosas")
            
            if "tiempos" in resultados:
                print(f"Tiempos: Promedio {resultados['tiempos']['promedio']:.2f}s "
                      f"(min: {resultados['tiempos']['minimo']:.2f}s, "
                      f"max: {resultados['tiempos']['maximo']:.2f}s)")
                print(f"  Desviación estándar: {resultados['tiempos']['desviacion']:.2f}s")
            
            with open("resultados_pruebas.json", "w", encoding="utf-8") as f:
                json.dump(resultados, f, indent=2, ensure_ascii=False)
            
            print(f"\nResultados guardados en: resultados_pruebas.json")
            print(f"Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except KeyboardInterrupt:
            print("\nPruebas interrumpidas por el usuario")
        except Exception as e:
            print(f"\nError durante las pruebas: {e}")
        
        return resultados

def main():
    """Función principal"""
    tester = TesterConversacional("http://127.0.0.1:8000")
    
    try:
        health_check = requests.get("http://127.0.0.1:8000/health")
        if health_check.status_code == 200:
            print("✅ Servidor funcionando correctamente")
        else:
            print(f"⚠️  Servidor respondió con código: {health_check.status_code}")
            print("Continuando de todas formas...")
    except:
        print("❌ No se puede conectar al servidor en http://127.0.0.1:8000")
        print("Asegúrate de que el servidor esté corriendo con:")
        print("  uvicorn la_santisima_conversacional.presentation.http_api:app --reload")
        return
    
    resultados = tester.ejecutar_bateria_completa()
    
    print("\n" + "="*60)
    print("ANÁLISIS RÁPIDO")
    print("="*60)
    
    if "tiempos" in resultados:
        tiempo_prom = resultados["tiempos"]["promedio"]
        if tiempo_prom < 2:
            print(f"✅ Tiempo de respuesta EXCELENTE: {tiempo_prom:.2f}s")
        elif tiempo_prom < 5:
            print(f"⚠️  Tiempo de respuesta ACEPTABLE: {tiempo_prom:.2f}s")
        else:
            print(f"❌ Tiempo de respuesta LENTO: {tiempo_prom:.2f}s")
    
    if "robustez" in resultados:
        exito_rate = resultados["robustez"]["exitosos"] / resultados["robustez"]["total"] * 100
        if exito_rate >= 90:
            print(f"✅ Robustez EXCELENTE: {exito_rate:.0f}% de éxito")
        elif exito_rate >= 70:
            print(f"⚠️  Robustez ACEPTABLE: {exito_rate:.0f}% de éxito")
        else:
            print(f"❌ Robustez BAJA: {exito_rate:.0f}% de éxito")

if __name__ == "__main__":
    main()