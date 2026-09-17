import os
import json
import logging
from la_santisima_conversacional import crear_servicio

# Configuración básica para evaluación
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("evaluador_voz")

def evaluar_respuesta(input_texto, respuesta_obj):
    # Criterios base
    texto = respuesta_obj.contenido
    
    errores = []
    
    # 1. Brevedad (máx 3 oraciones aprox)
    oraciones = [o for o in texto.split('.') if o.strip()]
    if len(oraciones) > 4:
        errores.append(f"Demasiado larga: {len(oraciones)} oraciones.")
        
    # 2. No-AI cliches
    cliches = ["como modelo de lenguaje", "inteligencia artificial", "soy una ia", "lo siento, pero"]
    if any(cliche in texto.lower() for cliche in cliches):
        errores.append("Ruptura de personaje: cliché de IA detectado.")
        
    return errores

def ejecutar_evaluacion():
    # Obtener API key del entorno
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        raise ValueError("DEEPINFRA_API_KEY no configurada en el entorno.")
        
    api = crear_servicio(use_langchain=True, deepinfra_api_key=api_key)
    
    with open('tests/evaluation/golden_dataset.json', 'r') as f:
        dataset = json.load(f)
        
    resultados = []
    for item in dataset:
        logger.info(f"Evaluando input: {item['input']}")
        respuesta = api.responder(item['input'], session_id="eval-test")
        
        errores = evaluar_respuesta(item['input'], respuesta)
        
        resultados.append({
            "input": item['input'],
            "respuesta": respuesta.contenido,
            "errores": errores,
            "paso": len(errores) == 0
        })
        
    # Resumen
    pasados = [r for r in resultados if r['paso']]
    logger.info(f"Evaluación finalizada. Pasaron: {len(pasados)}/{len(resultados)}")
    
    for r in resultados:
        if not r['paso']:
            logger.warning(f"Input fallido: {r['input']} | Errores: {r['errores']}")

if __name__ == "__main__":
    ejecutar_evaluacion()
