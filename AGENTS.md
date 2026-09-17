name: ux_frontend_architect
description: >
  Audita, diseña y optimiza arquitecturas front-end y flujos UX/UI bajo criterios 
  estrictos de fricción mínima, coherencia espacial, jerarquía visual y paletas premium.
parameters:
  type: object
  properties:
    action:
      type: string
      description: Tarea específica a ejecutar.
      enum:
        - audit_interface
        - generate_spec
        - optimize_flow
        - define_palette
      required: true
    context:
      type: string
      description: Contexto del producto, problema a resolver o interfaz objetivo.
      required: true
    input_data:
      type: object
      description: Código, estructura de componentes o diagrama de flujo actual.
      properties:
        wireframe_or_code:
          type: string
        interaction_depth:
          type: integer
          description: Número actual de clics/pasos del flujo.
      required: false
  required:
    - action
    - context
