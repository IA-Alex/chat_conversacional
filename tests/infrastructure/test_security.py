"""Tests para autenticación por API key y session_id firmados."""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from la_santisima_conversacional.config import Settings
from la_santisima_conversacional.infrastructure.security import (
    emitir_device_token,
    emitir_session_id,
    validar_session_id,
    verificar_api_key,
    verificar_firma_device_token,
)


def _settings(**overrides) -> Settings:
    base = dict(
        deepinfra_api_key="sk-test",
        api_keys=["key-valida"],
        session_secret="secreto-de-prueba",
        debug=False,
    )
    base.update(overrides)
    return Settings(**base)


class TestVerificarApiKey:
    def test_acepta_api_key_valida(self):
        settings = _settings()
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="key-valida")
        assert verificar_api_key(creds, settings) == "key-valida"

    def test_rechaza_api_key_invalida(self):
        settings = _settings()
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="key-falsa")
        with pytest.raises(HTTPException) as exc:
            verificar_api_key(creds, settings)
        assert exc.value.status_code == 401

    def test_rechaza_sin_credenciales(self):
        settings = _settings()
        with pytest.raises(HTTPException) as exc:
            verificar_api_key(None, settings)
        assert exc.value.status_code == 401

    def test_modo_debug_sin_api_keys_acepta_cualquier_request(self):
        settings = _settings(api_keys=[], debug=True)
        assert verificar_api_key(None, settings) == "debug-api-key"


class TestDeviceToken:
    def test_device_token_emitido_verifica_correctamente(self):
        settings = _settings()
        token = emitir_device_token("device-123", settings)
        assert verificar_firma_device_token(token, settings) == "device-123"

    def test_device_token_fabricado_es_rechazado(self):
        settings = _settings()
        assert verificar_firma_device_token("device-123.firma-inventada", settings) is None

    def test_device_token_malformado_es_rechazado(self):
        settings = _settings()
        assert verificar_firma_device_token("no-tiene-formato-valido", settings) is None

    def test_device_token_firmado_con_otro_secreto_es_rechazado(self):
        settings_a = _settings(session_secret="secreto-a")
        settings_b = _settings(session_secret="secreto-b")
        token = emitir_device_token("device-123", settings_a)
        assert verificar_firma_device_token(token, settings_b) is None

    def test_session_id_puede_atarse_a_un_device_id(self):
        """emitir_session_id/validar_session_id son genéricos: sirven igual
        para un device_id que para un api_key admin."""
        settings = _settings()
        session_id = emitir_session_id("device-123", settings)
        assert validar_session_id(session_id, "device-123", settings) is True
        assert validar_session_id(session_id, "device-456", settings) is False


class TestSessionId:
    def test_session_id_emitido_es_valido_para_el_mismo_api_key(self):
        settings = _settings()
        session_id = emitir_session_id("key-valida", settings)
        assert validar_session_id(session_id, "key-valida", settings) is True

    def test_session_id_no_es_valido_para_otro_api_key(self):
        """Un session_id emitido para un api_key no debe servir para otro.

        Este es el escenario central que P0.2 corrige: antes cualquier
        string servía como session_id para cualquiera.
        """
        settings = _settings(api_keys=["key-valida", "otra-key"])
        session_id = emitir_session_id("key-valida", settings)
        assert validar_session_id(session_id, "otra-key", settings) is False

    def test_session_id_fabricado_a_mano_es_rechazado(self):
        settings = _settings()
        assert validar_session_id("cualquier-cosa-inventada", "key-valida", settings) is False

    def test_session_id_con_firma_alterada_es_rechazado(self):
        settings = _settings()
        session_id = emitir_session_id("key-valida", settings)
        hash_key, token, firma = session_id.split(".")
        # La firma es un hexdigest: sustituir el último carácter por un
        # valor fijo es un no-op ~1/16 de las veces (cuando ya era ese
        # valor), lo que volvía el test flaky. Se garantiza una alteración
        # real eligiendo un carácter hex distinto al original.
        ultimo_alterado = "0" if firma[-1] != "0" else "1"
        alterado = f"{hash_key}.{token}.{firma[:-1]}{ultimo_alterado}"
        assert validar_session_id(alterado, "key-valida", settings) is False
