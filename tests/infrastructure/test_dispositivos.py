"""Tests para el registro de dispositivos (identidad de usuario final)."""

import pytest

from la_santisima_conversacional.infrastructure.dispositivos import (
    RegistroDispositivosMemory,
    RegistroDispositivosSQLite,
)


class _CasosRegistroDispositivos:
    """Casos compartidos entre ambas implementaciones (memoria y SQLite):
    deben cumplir exactamente el mismo contrato observable."""

    def crear_registro(self):
        raise NotImplementedError

    def test_registrar_devuelve_device_id_no_vacio(self):
        registro = self.crear_registro()
        device_id = registro.registrar()
        assert device_id

    def test_cada_registro_da_un_device_id_distinto(self):
        registro = self.crear_registro()
        assert registro.registrar() != registro.registrar()

    def test_dispositivo_nuevo_no_esta_revocado(self):
        registro = self.crear_registro()
        device_id = registro.registrar()
        assert registro.esta_revocado(device_id) is False

    def test_device_id_desconocido_se_trata_como_revocado(self):
        """Un device_id que nunca se registró no debe tratarse como válido
        (p. ej. si alguien fabrica una firma válida para un ID al azar que
        nunca pasó por `registrar`, pero eso ya lo bloquea la firma HMAC;
        este es el nivel de defensa del registro en sí)."""
        registro = self.crear_registro()
        assert registro.esta_revocado("device-que-nunca-existio") is True

    def test_dispositivo_registrado_existe(self):
        registro = self.crear_registro()
        device_id = registro.registrar()
        assert registro.existe(device_id) is True

    def test_device_id_desconocido_no_existe(self):
        """Distinto de esta_revocado (que trata 'desconocido' como
        'revocado' por seguridad): existe() debe decir la verdad — esto es
        lo que permite a http_api.py distinguir un token huérfano (401,
        autocorregible) de una revocación real (403, nunca autocorregible).
        Ver verificar_dispositivo en http_api.py."""
        registro = self.crear_registro()
        assert registro.existe("device-que-nunca-existio") is False

    def test_dispositivo_revocado_sigue_existiendo(self):
        """Revocar no borra el registro (ver docstring de `revocar`): un
        dispositivo revocado debe seguir siendo 'existente' para que
        verificar_dispositivo lo reporte como 403 revocado, no como 401
        desconocido."""
        registro = self.crear_registro()
        device_id = registro.registrar()
        registro.revocar(device_id)
        assert registro.existe(device_id) is True
        assert registro.esta_revocado(device_id) is True

    def test_revocar_bloquea_el_dispositivo(self):
        registro = self.crear_registro()
        device_id = registro.registrar()
        registro.revocar(device_id)
        assert registro.esta_revocado(device_id) is True

    def test_revocar_no_afecta_a_otros_dispositivos(self):
        registro = self.crear_registro()
        a = registro.registrar()
        b = registro.registrar()
        registro.revocar(a)
        assert registro.esta_revocado(a) is True
        assert registro.esta_revocado(b) is False

    def test_marcar_uso_no_lanza_para_dispositivo_existente(self):
        registro = self.crear_registro()
        device_id = registro.registrar()
        registro.marcar_uso(device_id)  # no debe lanzar

    def test_marcar_uso_no_lanza_para_dispositivo_inexistente(self):
        """marcar_uso es best-effort: no debe tumbar el request si el
        device_id no está (caso raro, pero no debe ser un 500)."""
        registro = self.crear_registro()
        registro.marcar_uso("no-existe")  # no debe lanzar

    def test_dispositivo_nuevo_no_tiene_consentimiento(self):
        registro = self.crear_registro()
        device_id = registro.registrar()
        assert registro.obtener_version_consentimiento(device_id) is None

    def test_registrar_consentimiento_queda_disponible(self):
        registro = self.crear_registro()
        device_id = registro.registrar()
        registro.registrar_consentimiento(device_id, "v1")
        assert registro.obtener_version_consentimiento(device_id) == "v1"

    def test_registrar_consentimiento_de_nuevo_reemplaza_la_version(self):
        """Aceptar una versión nueva del aviso debe reemplazar (no acumular
        junto a) la versión anterior aceptada."""
        registro = self.crear_registro()
        device_id = registro.registrar()
        registro.registrar_consentimiento(device_id, "v1")
        registro.registrar_consentimiento(device_id, "v2")
        assert registro.obtener_version_consentimiento(device_id) == "v2"

    def test_consentimiento_no_afecta_a_otros_dispositivos(self):
        registro = self.crear_registro()
        a = registro.registrar()
        b = registro.registrar()
        registro.registrar_consentimiento(a, "v1")
        assert registro.obtener_version_consentimiento(b) is None


class TestRegistroDispositivosMemory(_CasosRegistroDispositivos):
    def crear_registro(self):
        return RegistroDispositivosMemory()


class TestRegistroDispositivosSQLite(_CasosRegistroDispositivos):
    @pytest.fixture(autouse=True)
    def _db_path(self, tmp_path):
        self._path = str(tmp_path / "dispositivos-test.db")

    def crear_registro(self):
        return RegistroDispositivosSQLite(db_path=self._path)

    def test_revocacion_sobrevive_una_nueva_conexion(self):
        """A diferencia de la versión en memoria, esto debe sobrevivir un
        reinicio del proceso (aquí simulado: una instancia nueva apuntando
        al mismo archivo)."""
        registro_1 = RegistroDispositivosSQLite(db_path=self._path)
        device_id = registro_1.registrar()
        registro_1.revocar(device_id)

        registro_2 = RegistroDispositivosSQLite(db_path=self._path)
        assert registro_2.esta_revocado(device_id) is True

    def test_consentimiento_sobrevive_una_nueva_conexion(self):
        registro_1 = RegistroDispositivosSQLite(db_path=self._path)
        device_id = registro_1.registrar()
        registro_1.registrar_consentimiento(device_id, "v1")

        registro_2 = RegistroDispositivosSQLite(db_path=self._path)
        assert registro_2.obtener_version_consentimiento(device_id) == "v1"

    def test_migra_base_de_datos_anterior_sin_columnas_de_consentimiento(self):
        """Una base creada por una versión anterior del código (sin las
        columnas de consentimiento) no debe romper al arrancar — debe
        migrarse en el sitio (ver ``_inicializar_base_datos``)."""
        import sqlite3

        conn = sqlite3.connect(self._path)
        conn.execute("""
            CREATE TABLE dispositivos (
                device_id TEXT PRIMARY KEY,
                creado TEXT NOT NULL,
                ultimo_uso TEXT NOT NULL,
                revocado INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("INSERT INTO dispositivos VALUES ('viejo', '2020-01-01', '2020-01-01', 0)")
        conn.commit()
        conn.close()

        registro = RegistroDispositivosSQLite(db_path=self._path)  # no debe lanzar
        assert registro.obtener_version_consentimiento("viejo") is None
        registro.registrar_consentimiento("viejo", "v1")
        assert registro.obtener_version_consentimiento("viejo") == "v1"
