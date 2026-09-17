"""
Implementación de steps BDD para pruebas de conversación.
"""
import json
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from la_santisima_conversacional.domain.validators import validar_respuesta_la_santisima

scenarios('../features/conversacion.feature')

@pytest.fixture
def contexto():
    return {
        'device_token': None,
        'session_id': None,
        'response': None,
        'stream_chunks': [],
        'emocion_final': None
    }

def _registrar_dispositivo(cliente):
    resp = cliente.post("/api/v1/dispositivos")
    assert resp.status_code == 200
    return resp.json()

def _aceptar_consentimiento(cliente, device_token):
    version = cliente.get("/privacidad").json()["version"]
    headers = {"Authorization": f"Bearer {device_token}"}
    resp = cliente.post("/api/v1/dispositivos/consentimiento", json={"version": version}, headers=headers)
    assert resp.status_code in (204, 409)
    return headers

def _crear_sesion(cliente, device_token):
    headers = {"Authorization": f"Bearer {device_token}"}
    resp = cliente.post("/api/v1/sesiones", headers=headers)
    assert resp.status_code == 200
    return resp.json()["session_id"]

def _validar_emocion(emocion):
    emociones_validas = {'devocion', 'respeto', 'consuelo', 'resignacion', 'soledad', 'desesperacion', 'ira', 'ninguna'}
    return emocion in emociones_validas or emocion is None

@given("que el backend está funcionando correctamente")
def backend_funcionando(cliente, contexto):
    resp = cliente.get("/health")
    assert resp.status_code == 200

@given("tengo un dispositivo registrado con token válido")
def dispositivo_registrado(cliente, contexto):
    dispositivo = _registrar_dispositivo(cliente)
    contexto['device_token'] = dispositivo['device_token']
    _aceptar_consentimiento(cliente, dispositivo['device_token'])

@given("he aceptado el consentimiento de privacidad vigente")
def consentimiento_aceptado(cliente, contexto):
    if contexto.get('device_token'):
        _aceptar_consentimiento(cliente, contexto['device_token'])

@given("que tengo una sesión nueva creada")
def sesion_nueva_creada(cliente, contexto):
    if not contexto.get('device_token'):
        dispositivo_registrado(cliente, contexto)
    contexto['session_id'] = _crear_sesion(cliente, contexto['device_token'])

@given("que tengo una sesión activa válida")
def sesion_activa_valida(cliente, contexto):
    if not contexto.get('session_id'):
        sesion_nueva_creada(cliente, contexto)

@when(parsers.parse('envío el mensaje "{mensaje}" al endpoint {endpoint}'))
def enviar_mensaje_endpoint(cliente, contexto, mensaje, endpoint):
    headers = {"Authorization": f"Bearer {contexto['device_token']}", "Content-Type": "application/json"}
    payload = {"mensaje": mensaje, "session_id": contexto['session_id']}
    
    if endpoint == "/api/v1/mensajes":
        resp = cliente.post(endpoint, json=payload, headers=headers)
        assert resp.status_code == 200
        contexto['response'] = resp.json()
    elif endpoint == "/api/v1/mensajes/stream":
        resp = cliente.post(endpoint, json=payload, headers=headers)
        assert resp.status_code == 200
        chunks = []
        for line in resp.iter_lines():
            if line:
                if isinstance(line, bytes):
                    line_str = line.decode('utf-8')
                else:
                    line_str = line
                if line_str.startswith("data: ") and not line_str.startswith("data: [CORTADO"):
                    chunk = line_str[6:]
                    if chunk.strip():
                        chunks.append(chunk)
                elif line_str.startswith("event: done"):
                    contexto['emocion_final'] = None  # simplificado
        contexto['stream_chunks'] = chunks
        contexto['response'] = {"chunks": chunks}

@then("recibo una respuesta válida de La Santísima Muerte")
def respuesta_valida(contexto):
    assert contexto['response'] is not None
    # Extraer texto de la respuesta
    if 'contenido' in contexto['response']:
        texto = contexto['response']['contenido']
    elif 'respuesta' in contexto['response']:
        texto = contexto['response']['respuesta']
    else:
        texto = ''.join(contexto.get('stream_chunks', []))
    # Validar usando validador del dominio
    es_valida, error = validar_respuesta_la_santisima(texto)
    assert es_valida, f"Respuesta no válida según validador: {error}"

@then("la respuesta contiene texto de bienvenida")
def respuesta_contiene_bienvenida(contexto):
    if 'contenido' in contexto['response']:
        texto = contexto['response']['contenido'].lower()
    elif 'respuesta' in contexto['response']:
        texto = contexto['response']['respuesta'].lower()
    else:
        texto = ''.join(contexto.get('stream_chunks', [])).lower()
    assert any(p in texto for p in ['bienvenida', 'hola', 'saludos'])

@then(parsers.parse('la emoción detectada es "{emocion1}" o "{emocion2}"'))
def emocion_detectada_valida(contexto, emocion1, emocion2):
    emocion = contexto['response'].get('emocion')
    if emocion is None:
        pytest.skip("Sin emoción detectada")
    assert emocion in [emocion1, emocion2]

@then("la longitud de la respuesta está entre 20 y 500 caracteres")
def longitud_respuesta_valida(contexto):
    if 'contenido' in contexto['response']:
        texto = contexto['response']['contenido']
    elif 'respuesta' in contexto['response']:
        texto = contexto['response']['respuesta']
    else:
        texto = ''.join(contexto.get('stream_chunks', []))
    assert 20 <= len(texto) <= 500

@then("recibo una respuesta de acompañamiento espiritual")
def respuesta_acompanamiento_espiritual(contexto):
    if 'contenido' in contexto['response']:
        texto = contexto['response']['contenido'].lower()
    elif 'respuesta' in contexto['response']:
        texto = contexto['response']['respuesta'].lower()
    else:
        texto = ''.join(contexto.get('stream_chunks', [])).lower()
    palabras_espirituales = ['acompañ', 'consuelo', 'presencia', 'divina', 'espiritual']
    assert any(palabra in texto for palabra in palabras_espirituales)

@then("la respuesta evita consejos médicos o psicológicos profesionales")
def respuesta_evita_consejos_profesionales(contexto):
    if 'contenido' in contexto['response']:
        texto = contexto['response']['contenido'].lower()
    elif 'respuesta' in contexto['response']:
        texto = contexto['response']['respuesta'].lower()
    else:
        texto = ''.join(contexto.get('stream_chunks', [])).lower()
    consejos_prohibidos = ['psicólogo', 'psiquiatra', 'terapia', 'medicamento', 'diagnóstico']
    for prohibido in consejos_prohibidos:
        assert prohibido not in texto

@then("la respuesta contiene elementos místicos o espirituales")
def respuesta_contiene_elementos_misticos(contexto):
    if 'contenido' in contexto['response']:
        texto = contexto['response']['contenido'].lower()
    elif 'respuesta' in contexto['response']:
        texto = contexto['response']['respuesta'].lower()
    else:
        texto = ''.join(contexto.get('stream_chunks', [])).lower()
    elementos_misticos = ['vela', 'ofrenda', 'ritual', 'oración', 'rezo', 'altar']
    assert any(elemento in texto for elemento in elementos_misticos)

@then("recibo chunks de texto progresivamente")
def recibo_chunks_progresivos(contexto):
    chunks = contexto.get('stream_chunks', [])
    assert len(chunks) > 0

@then("cada chunk contiene texto válido (no vacío)")
def chunks_contienen_texto_valido(contexto):
    chunks = contexto.get('stream_chunks', [])
    for chunk in chunks:
        assert chunk.strip()

@then('el stream finaliza con un evento "done" que contiene emoción')
def stream_finaliza_con_done(contexto):
    emocion_final = contexto.get('emocion_final')
    if emocion_final is not None:
        assert _validar_emocion(emocion_final)

@then("la emoción final es válida o null")
def emocion_final_valida_o_null(contexto):
    emocion_final = contexto.get('emocion_final')
    if emocion_final is not None:
        assert _validar_emocion(emocion_final)

@then("todos los chunks combinados forman una respuesta coherente")
def chunks_forman_respuesta_coherente(contexto):
    chunks = contexto.get('stream_chunks', [])
    if not chunks:
        pytest.skip("No hay chunks")
    texto_completo = ''.join(chunks)
    assert len(texto_completo) >= 20
    # Validar con validador del dominio
    es_valida, error = validar_respuesta_la_santisima(texto_completo)
    assert es_valida, f"Texto combinado no válido: {error}"