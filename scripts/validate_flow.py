#!/usr/bin/env python3
import json
from pathlib import Path

def validate_flow(flow_path):
    with open(flow_path, 'r') as f:
        flow = json.load(f)
    
    methods = flow['methods']
    print(f"\n=== VALIDACIÓN DE FLOW ({len(methods)} métodos) ===\n")
    
    # 1. Verificar métodos con start: true
    start_methods = [name for name, method in methods.items() if method.get('start')]
    print(f"1. Métodos con start: true: {start_methods}")
    
    # 2. Verificar routers
    routers = [(name, method) for name, method in methods.items() if method.get('router')]
    print(f"\n2. Routers encontrados ({len(routers)}):")
    for name, method in routers:
        emit = method.get('emit', [])
        print(f"   - {name}: emit={emit}")
    
    # 3. Verificar listen references
    all_events = set()
    print(f"\n3. Referencias listen (eventos y métodos):")
    
    for name, method in methods.items():
        listen = method.get('listen')
        if listen:
            if isinstance(listen, list):
                all_events.update(listen)
                print(f"   - {name} listens to: {listen}")
            else:
                all_events.add(listen)
                print(f"   - {name} listens to: {listen}")
    
    # 4. Métodos y eventos definidos
    defined_methods = set(methods.keys())
    print(f"\n4. Métodos definidos: {len(defined_methods)}")
    
    # 5. Verificar referencias
    missing_refs = []
    for event in all_events:
        if event not in defined_methods:
            # Puede ser un evento emitido por un router
            is_router_event = any(event in m.get('emit', []) for n, m in routers)
            if not is_router_event:
                missing_refs.append(event)
    
    if missing_refs:
        print(f"\n⚠️  ADVERTENCIA: Referencias missing: {missing_refs}")
    else:
        print(f"\n✓ Todas las referencias son válidas")
    
    # 6. Validar routers
    print(f"\n5. Validación de routers:")
    for name, method in routers:
        emit = method.get('emit', [])
        if not emit:
            print(f"   ⚠️  {name}: Router sin eventos emitidos")
        else:
            print(f"   ✓ {name}: Tiene {len(emit)} eventos emitidos")
    
    return True

if __name__ == "__main__":
    flow_path = (
        Path(__file__).resolve().parent.parent
        / "src" / "la_santisima_conversacional" / "infrastructure" / "flow.json"
    )
    validate_flow(str(flow_path))