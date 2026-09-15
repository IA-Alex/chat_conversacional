"""Tests para la configuración centralizada (fail-fast de Settings)."""

import pytest
from pydantic import ValidationError

from src.la_santisima_conversacional.config import Settings


class TestSettings:
    def test_falla_sin_deepinfra_api_key(self, monkeypatch):
        monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    def test_acepta_deepinfra_api_key_por_env(self, monkeypatch):
        monkeypatch.setenv("DEEPINFRA_API_KEY", "sk-test")
        settings = Settings(_env_file=None)
        assert settings.deepinfra_api_key == "sk-test"

    def test_api_keys_acepta_csv(self):
        settings = Settings(deepinfra_api_key="sk-test", api_keys="a,b, c")
        assert settings.api_keys == ["a", "b", "c"]

    def test_validar_produccion_no_exige_api_keys_fuera_de_debug(self):
        """api_keys es solo para endpoints de administración: su ausencia
        no debe bloquear el arranque (la app de un usuario final se
        identifica por dispositivo, no por api_key)."""
        settings = Settings(
            deepinfra_api_key="sk-test", debug=False, api_keys=[], 
            session_secret="x", clave_cifrado="test-cifrado-key-123456789012345678901234567890"
        )
        settings.validar_produccion()  # no debe lanzar

    def test_validar_produccion_exige_session_secret_fuera_de_debug(self):
        settings = Settings(
            deepinfra_api_key="sk-test", debug=False, api_keys=["k"], session_secret=None
        )
        with pytest.raises(RuntimeError, match="SESSION_SECRET"):
            settings.validar_produccion()

    def test_validar_produccion_exige_clave_cifrado_fuera_de_debug(self):
        settings = Settings(
            deepinfra_api_key="sk-test", debug=False, api_keys=["k"], 
            session_secret="test-secret", clave_cifrado=None
        )
        with pytest.raises(RuntimeError, match="CLAVE_CIFRADO"):
            settings.validar_produccion()

    def test_validar_produccion_no_exige_clave_cifrado_en_debug(self):
        settings = Settings(
            deepinfra_api_key="sk-test", debug=True, api_keys=[], 
            session_secret=None, clave_cifrado=None
        )
        settings.validar_produccion()  # no debe lanzar

    def test_validar_produccion_no_exige_nada_en_debug(self):
        settings = Settings(
            deepinfra_api_key="sk-test", debug=True, api_keys=[], session_secret=None
        )
        settings.validar_produccion()  # no debe lanzar

    def test_usar_postgres_sin_dsn_falla_al_construir(self):
        """Config incoherente falla al arrancar, no en el primer request."""
        with pytest.raises(ValidationError, match="POSTGRES_DSN"):
            Settings(deepinfra_api_key="sk-test", usar_postgres=True, postgres_dsn=None)

    def test_usar_postgres_con_dsn_no_falla(self):
        settings = Settings(
            deepinfra_api_key="sk-test", usar_postgres=True, postgres_dsn="postgresql://x/y"
        )
        assert settings.usar_postgres is True

    def test_usar_redis_rate_limit_sin_url_falla_al_construir(self):
        with pytest.raises(ValidationError, match="REDIS_URL"):
            Settings(deepinfra_api_key="sk-test", usar_redis_rate_limit=True, redis_url=None)

    def test_usar_redis_rate_limit_con_url_no_falla(self):
        settings = Settings(
            deepinfra_api_key="sk-test", usar_redis_rate_limit=True, redis_url="redis://x/0"
        )
        assert settings.usar_redis_rate_limit is True

    def test_por_defecto_postgres_y_redis_apagados(self):
        """Sin configurar nada nuevo, el comportamiento no cambia (opt-in)."""
        settings = Settings(deepinfra_api_key="sk-test")
        assert settings.usar_postgres is False
        assert settings.usar_redis_rate_limit is False

    def test_debug_en_produccion_sin_confirmacion_falla(self, monkeypatch):
        """debug=true en entorno productivo sin confirmación debe fallar."""
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "true")
        with pytest.raises(ValueError, match="debug=true detectado en entorno productivo"):
            Settings(deepinfra_api_key="sk-test", debug=True)

    def test_debug_en_produccion_con_confirmacion_pasa(self, monkeypatch):
        """debug=true en entorno productivo CON confirmación debe pasar."""
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "true")
        settings = Settings(deepinfra_api_key="sk-test", debug=True, confirmo_debug_en_prod=True)
        assert settings.debug is True
        assert settings.confirmo_debug_en_prod is True

    def test_debug_fuera_de_produccion_pasa_sin_confirmacion(self):
        """debug=true fuera de entorno productivo pasa sin confirmación."""
        settings = Settings(deepinfra_api_key="sk-test", debug=True)
        assert settings.debug is True
        assert settings.confirmo_debug_en_prod is False

    def test_santissima_entorno_production_sin_confirmacion_falla(self, monkeypatch):
        """SANTISIMA_ENTORNO=production con debug=true sin confirmación falla."""
        monkeypatch.setenv("SANTISIMA_ENTORNO", "production")
        with pytest.raises(ValueError, match="debug=true detectado en entorno productivo"):
            Settings(deepinfra_api_key="sk-test", debug=True)

    def test_santissima_entorno_production_con_confirmacion_pasa(self, monkeypatch):
        """SANTISIMA_ENTORNO=production con debug=true y confirmación pasa."""
        monkeypatch.setenv("SANTISIMA_ENTORNO", "production")
        settings = Settings(
            deepinfra_api_key="sk-test",
            debug=True,
            confirmo_debug_en_prod=True
        )
        assert settings.debug is True
        assert settings.confirmo_debug_en_prod is True

    def test_use_langchain_default_no_se_revierte(self, monkeypatch):
        """`CrewAIAdapter._configurar_flow()` carga el flow declarativo con
        `Flow.from_file(...)`, método que no existe en la versión de
        `crewai` instalada (ver `infrastructure/crewai_adapter.py`): la
        carga falla silenciosamente y el adaptador queda degradado
        permanentemente a `_crear_flow_basico()`, sin enrutamiento de
        intención/emoción, por lo que la detección de crisis queda
        inoperante en ese motor (ver `docs/compliance/gobernanza-ia.md`
        §4). Mientras esa incompatibilidad no se corrija, el default de
        `Settings.use_langchain` debe seguir siendo True."""
        monkeypatch.setenv("DEEPINFRA_API_KEY", "sk-test")
        settings = Settings(_env_file=None)
        assert settings.use_langchain is True, (
            "Settings.use_langchain volvió a False: reintroduce el hallazgo "
            "documentado (CrewAIAdapter queda degradado, sin detección de "
            "crisis) en el motor activo por defecto. Ver docs/compliance/"
            "gobernanza-ia.md §4."
        )
