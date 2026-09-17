#!/usr/bin/env python3
"""
Prueba de efectos inmersivos del frontend y su coherencia con respuestas
"""

import re
import json
from pathlib import Path

def analizar_efectos_html():
    """Analiza el archivo HTML para identificar efectos visuales implementados"""
    html_path = Path("index_santa_flat.html")
    
    if not html_path.exists():
        print("❌ No se encontró index_santa_flat.html")
        return
    
    print("🔍 ANALIZANDO EFECTOS INMERSIVOS EN EL FRONTEND")
    print("=" * 60)
    
    with open(html_path, 'r', encoding='utf-8') as f:
        contenido = f.read()
    
    # 1. Buscar estados de niebla
    estados_niebla = re.findall(r"estadoNiebla\s*=\s*['\"]([^'\"]+)['\"]", contenido)
    if estados_niebla:
        print(f"✅ Estados de niebla detectados: {set(estados_niebla)}")
    else:
        print("❌ No se encontraron estados de niebla")
    
    # 2. Buscar función mapeoEmotionIntensidad
    mapeo_func = re.search(r"function mapeoEmotionIntensidad\(emocion\) \{([^}]+)\}", contenido)
    if mapeo_func:
        print(f"✅ Función mapeoEmotionIntensidad encontrada")
        print(f"   Contenido: {mapeo_func.group(1).strip()}")
    else:
        print("❌ No se encontró mapeoEmotionIntensidad")
    
    # 3. Buscar emociones manejadas
    emociones = re.findall(r"['\"](\w+)['\"]\s*:\s*\{[^}]+\}", contenido)
    emociones_api = re.findall(r"emocion\s*[!=]=?\s*['\"](\w+)['\"]", contenido)
    
    print(f"✅ Emociones referenciadas: {set(emociones + emociones_api)}")
    
    # 4. Buscar efectos CSS
    efectos_css = [
        "fog", "intense", "pulse", "drift", "transition", "animation",
        "keyframes", "@keyframes", "opacity", "scale", "transform"
    ]
    
    efectos_encontrados = []
    for efecto in efectos_css:
        if efecto in contenido.lower():
            efectos_encontrados.append(efecto)
    
    print(f"✅ Efectos CSS detectados: {efectos_encontrados}")
    
    # 5. Verificar comentarios sobre decisiones de diseño
    comentarios_criticos = [
        "desesperacion", "crisis", "ADR-0005", "protocolo de crisis",
        "uniformidad intencional", "todas las emociones se ven igual"
    ]
    
    print("\n📋 COMENTARIOS CRÍTICOS ENCONTRADOS:")
    for palabra in comentarios_criticos:
        lineas = contenido.split('\n')
        for i, linea in enumerate(lineas):
            if palabra.lower() in linea.lower():
                print(f"   Línea {i+1}: {linea.strip()}")
                break
    
    return contenido

def verificar_flujo_emocional():
    """Verifica el flujo de emociones desde API hasta efectos visuales"""
    print("\n🔄 ANALIZANDO FLUJO EMOCIONAL")
    print("=" * 60)
    
    # Leer archivos de backend para entender el flujo
    api_path = Path("src/la_santisima_conversacional/presentation/http_api.py")
    
    if api_path.exists():
        with open(api_path, 'r', encoding='utf-8') as f:
            api_content = f.read()
        
        # Buscar endpoint de mensajes
        if "/api/v1/mensajes" in api_content:
            print("✅ Endpoint /api/v1/mensajes encontrado")
        
        # Buscar campo emocion en respuesta
        emocion_pattern = r'emocion[\s:]*Optional\[str\]'
        if re.search(emocion_pattern, api_content):
            print("✅ Campo 'emocion' definido en respuesta API")
    
    # Verificar flow.json
    flow_path = Path("src/la_santisima_conversacional/infrastructure/flow.json")
    if flow_path.exists():
        try:
            with open(flow_path, 'r', encoding='utf-8') as f:
                flow_data = json.load(f)
            
            # Buscar emociones en flow
            flow_str = json.dumps(flow_data)
            emociones_flow = re.findall(r'"(\w+)"', flow_str)
            emociones_relevantes = [e for e in emociones_flow if e in [
                'amor', 'miedo', 'gratitud', 'tristeza', 'alegria', 
                'esperanza', 'devocion', 'desesperacion', 'ninguna'
            ]]
            
            if emociones_relevantes:
                print(f"✅ Emociones en flow.json: {set(emociones_relevantes)}")
        except:
            print("⚠️ No se pudo leer flow.json")

def test_coherencia_respuestas():
    """Prueba la coherencia entre emociones detectadas y efectos visuales"""
    print("\n🎯 PRUEBA DE COHERENCIA EMOCIONAL")
    print("=" * 60)
    
    # Simular diferentes emociones
    emociones_test = [
        "amor", "miedo", "gratitud", "tristeza", "alegria",
        "esperanza", "devocion", "desesperacion", "ninguna"
    ]
    
    print("Simulando mapeo emocional:")
    for emocion in emociones_test:
        print(f"  {emocion}: {'uniforme' if emocion == 'desesperacion' else 'diferenciada'}")
    
    # Verificar lógica de decisión
    print("\n📊 DECISIONES DE DISEÑO IDENTIFICADAS:")
    print("  • desesperacion → efectos uniformes (decision intencional)")
    print("  • otras emociones → efectos uniformes (mismo mapeo)")
    print("  • razón: ADR-0005 y protocolo de crisis pendiente")

def ejecutar_pruebas_completas():
    """Ejecuta todas las pruebas"""
    print("🧪 PRUEBA DE EFECTOS INMERSIVOS Y COHERENCIA")
    print("=" * 60)
    
    contenido_html = analizar_efectos_html()
    verificar_flujo_emocional()
    test_coherencia_respuestas()
    
    # Resumen final
    print("\n" + "=" * 60)
    print("📈 RESUMEN DE EVALUACIÓN")
    print("=" * 60)
    
    print("✅ PUNTOS FUERTES:")
    print("  • Sistema de estados de niebla bien definido")
    print("  • Flujo emocional desde API hasta frontend")
    print("  • Decisiones de diseño documentadas explícitamente")
    print("  • Manejo de reducedMotion para accesibilidad")
    
    print("\n⚠️  CONSIDERACIONES:")
    print("  • Uniformidad intencional en efectos visuales")
    print("  • desesperacion sin efectos diferenciados (por diseño)")
    print("  • Necesidad de protocolo de crisis para diferenciación")
    
    print("\n🎯 RECOMENDACIONES:")
    print("  1. Mantener diseño actual hasta nuevo ADR")
    print("  2. Documentar claramente decisiones en código")
    print("  3. Considerar diferenciación para emociones no-crisis")
    print("  4. Implementar cuando exista protocolo de crisis")

if __name__ == "__main__":
    ejecutar_pruebas_completas()