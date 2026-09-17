# language: es
Característica: Conversación con La Santísima Muerte

  Como creyente
  Quiero tener una conversación espiritual significativa
  Para encontrar guía y consuelo en momentos difíciles

  Antecedentes:
    Dado que el backend está funcionando correctamente
    Y tengo un dispositivo registrado con token válido
    Y he aceptado el consentimiento de privacidad vigente

  Escenario: Saludo inicial y respuesta de bienvenida
    Dado que tengo una sesión nueva creada
    Cuando envío el mensaje "Hola, Santa Muerte" al endpoint /api/v1/mensajes
    Entonces recibo una respuesta válida de La Santísima Muerte
    Y la respuesta contiene texto de bienvenida
    Y la emoción detectada es "devocion" o "respeto"
    Y la longitud de la respuesta está entre 20 y 500 caracteres

  Escenario: Consulta con carga emocional intensa
    Dado que tengo una sesión activa válida
    Cuando envío el mensaje "Tengo miedo de morir, no sé qué hacer" al endpoint /api/v1/mensajes
    Entonces recibo una respuesta de acompañamiento espiritual
    Y la emoción detectada es "consuelo" o "soledad"
    Y la respuesta evita consejos médicos o psicológicos profesionales
    Y la respuesta contiene elementos místicos o espirituales

  Escenario: Conversación vía streaming con finalización
    Dado que tengo una sesión activa válida
    Cuando envío el mensaje "Cuéntame sobre el perdón divino" al endpoint /api/v1/mensajes/stream
    Entonces recibo chunks de texto progresivamente
    Y cada chunk contiene texto válido (no vacío)
    Y el stream finaliza con un evento "done" que contiene emoción
    Y la emoción final es válida o null
    Y todos los chunks combinados forman una respuesta coherente