#!/usr/bin/env python3
import json
from pathlib import Path

_FLOW_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "la_santisima_conversacional" / "infrastructure" / "flow.json"
)


def main():
    with open(_FLOW_PATH, 'r') as f:
        flow = json.load(f)
    
    methods = flow['methods']
    
    print("\n=== ANÁLISIS DE ROUTERS ===")
    for name, method in methods.items():
        if method.get('router'):
            print(f"\n{name}:")
            print(f"  Listen: {method.get('listen')}")
            print(f"  Emit: {method.get('emit')}")
            do = method.get('do', {})
            call_type = do.get('call')
            print(f"  Call type: {call_type}")
            
            if call_type == 'agent':
                role = do.get('with', {}).get('role', '')
                print(f"  Role: {role[:30]}...")
                print(f"  Descripción: {method.get('description', '')[:50]}...")
                
            elif call_type == 'expression':
                expr = do.get('expr', '')
                print(f"  Expression: {expr[:80]}...")
    
    print("\n=== CHEQUEOS DE BUENAS PRÁCTICAS ===")
    problemas = []
    for name, method in methods.items():
        if method.get('router') and method.get('do', {}).get('call') != 'expression':
            problemas.append(
                f"- {name}: es router (router: true) pero su 'do' no es 'call: expression'. "
                "Un router debería limitarse a decidir el siguiente evento, no generar contenido."
            )
    if problemas:
        print("\n".join(problemas))
    else:
        print("Todos los routers son puros (call: expression). Sin problemas detectados.")

    # Nota: esta verificación estructural (self-listen, referencias listen/emit
    # inválidas) vive ahora como test automatizado en
    # tests/infrastructure/test_flow_structure.py, para que se ejecute en CI
    # en cada cambio a flow.json en vez de depender de correr este script a mano.

if __name__ == "__main__":
    main()