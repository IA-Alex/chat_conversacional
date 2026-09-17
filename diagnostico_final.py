#!/usr/bin/env python3
"""
Diagnóstico rápido del sistema
"""

import os
import sys
from datetime import datetime

def main():
    print("🔍 DIAGNÓSTICO RÁPIDO")
    print("="*60)
    print(f"Hora: {datetime.now().strftime('%H:%M:%S')}")
    print(f"Directorio: {os.getcwd()}")
    print()
    
    # 1. Verificar API key
    key = os.getenv('DEEPINFRA_API_KEY', 'NO_CONFIGURADA')
    if key == 'di-...' or key == 'NO_CONFIGURADA':
        print("🔑 API Key: ❌ NO CONFIGURADA")
        print("   Actual: 'di-...' (placeholder)")
    else:
        print(f"🔑 API Key: ✅ CONFIGURADA")
        print(f"   Longitud: {len(key)} caracteres")
    
    # 2. Verificar servidor
    try:
        import requests
        resp = requests.get('http://127.0.0.1:8000/health', timeout=2)
        print(f"🌐 Servidor: ✅ ACTIVO ({resp.status_code})")
    except ImportError:
        print("🌐 Servidor: ⚠️  No se puede verificar (requests no instalado)")
    except:
        print("🌐 Servidor: ❌ INACTIVO")
    
    # 3. Verificar scripts
    print("\n📜 SCRIPTS DISPONIBLES:")
    scripts = [
        ('test_minimo.py', 'Prueba rápida (30s)'),
        ('test_rapido.py', 'Prueba completa (2-3min)'),
        ('ejecutar_pruebas.sh', 'Menú interactivo'),
        ('iniciar_servidor.sh', 'Inicia servidor'),
        ('check_servidor.sh', 'Verifica servidor')
    ]
    
    for archivo, desc in scripts:
        if os.path.exists(archivo):
            print(f"   ✅ {archivo:20} - {desc}")
        else:
            print(f"   ❌ {archivo:20} - NO ENCONTRADO")
    
    # 4. Recomendaciones
    print("\n" + "="*60)
    print("🚀 RECOMENDACIONES INMEDIATAS")
    print("="*60)
    
    key_ok = key not in ['di-...', 'NO_CONFIGURADA']
    
    if not key_ok:
        print("1. 🔧 CONFIGURAR API KEY:")
        print("   Edita .env y cambia:")
        print("     DEEPINFRA_API_KEY=di-...")
        print("   Por tu key real de DeepInfra")
        print("   O ejecuta: export DEEPINFRA_API_KEY='tu_key'")
    
    # Intentar verificar servidor más detalladamente
    server_active = False
    try:
        import requests
        resp = requests.get('http://127.0.0.1:8000/health', timeout=2)
        server_active = resp.status_code == 200
    except:
        server_active = False
    
    if not server_active and key_ok:
        print("\n2. 🚀 INICIAR SERVIDOR:")
        print("   ./iniciar_servidor.sh")
        print("   Luego espera 5 segundos")
    
    if key_ok and server_active:
        print("\n3. 🧪 EJECUTAR PRUEBAS:")
        print("   Opción rápida:   python test_minimo.py")
        print("   Opción completa: python test_rapido.py")
        print("   Menú interactivo: ./ejecutar_pruebas.sh")
    elif key_ok:
        print("\n3. 🔍 VERIFICAR:")
        print("   Primero inicia servidor, luego ejecuta pruebas")
    else:
        print("\n3. ⚠️  CONFIGURAR PRIMERO:")
        print("   Sin API key no se puede probar el sistema")
    
    print("\n" + "="*60)
    print("📞 RESUMEN FINAL")
    print("="*60)
    
    if key_ok and server_active:
        print("🎉 TODO LISTO PARA PRUEBAS")
        print("   Ejecuta: ./ejecutar_pruebas.sh")
    elif key_ok:
        print("⚠️  FALTA INICIAR SERVIDOR")
        print("   Ejecuta: ./iniciar_servidor.sh")
    else:
        print("❌ FALTA API KEY")
        print("   Configura DEEPINFRA_API_KEY en .env")
    
    print(f"\n🕐 Diagnóstico completado")

if __name__ == "__main__":
    main()