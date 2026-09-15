"""Registro de dispositivos: identidad anónima por instalación de la app.

Sustituye el modelo de "API key fija repartida a mano" (razonable para un
puñado de usuarios conocidos, inviable para una app pública en Android/iOS
— una clave embebida en un binario que cualquiera descarga se puede
extraer descompilando el APK/IPA o inspeccionando el tráfico de red) por
identidad **por dispositivo**, emitida por el propio servidor, sin pedir
nombre/email/contraseña a nadie.

Flujo:
1. La app llama ``POST /api/v1/dispositivos`` una sola vez (primer uso).
   El servidor genera un ``device_id`` nuevo y lo registra aquí.
2. Devuelve un ``device_token`` autoverificable (HMAC, mismo mecanismo que
   ``session_id`` en ``security.py``) — no hace falta que el servidor lo
   guarde, solo el ``device_id`` que representa.
3. Cada request posterior manda ``Authorization: Bearer <device_token>``.
   El servidor valida la firma y consulta aquí si el ``device_id`` sigue
   activo (no fue revocado).

Este módulo solo resuelve el registro/revocación — la verificación
criptográfica del token vive en ``security.py``, igual que ``session_id``.
"""

import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional, Protocol

logger = logging.getLogger(__name__)


class RegistroDispositivos(Protocol):
    """Contrato para el registro de dispositivos (DIP, igual que
    ``ConversationRepository``): cualquier implementación concreta debe
    cumplirlo para ser intercambiable.
    """

    def registrar(self) -> str:
        """Da de alta un dispositivo nuevo y devuelve su ``device_id``."""
        ...

    def marcar_uso(self, device_id: str) -> None:
        """Actualiza la marca de "último uso" (para detectar dispositivos
        inactivos/abandonados; no bloquea ni valida nada)."""
        ...

    def existe(self, device_id: str) -> bool:
        """True si el device_id tiene un registro (revocado o no).

        Distinto de ``esta_revocado``: un device_token puede traer firma
        HMAC genuina (fue emitido por este backend en algún momento) sin
        que su fila siga en el registro — p. ej. un cliente con el token
        cacheado apuntando a una base de datos de dispositivos distinta o
        restaurada. Eso es un token huérfano, no una revocación deliberada;
        el llamador (ver ``verificar_dispositivo`` en ``http_api.py``) debe
        poder tratarlo distinto (401, autocorregible re-registrando) de un
        dispositivo que sí existe y fue revocado a propósito (403, no debe
        autocorregirse nunca).
        """
        ...

    def esta_revocado(self, device_id: str) -> bool:
        """True si el dispositivo fue revocado (ver ``revocar``).

        Para un device_id que no existe en absoluto, el valor de retorno
        no está definido por este método — usa ``existe`` primero (ver su
        docstring) para distinguir "no existe" de "revocado a propósito".
        """
        ...

    def revocar(self, device_id: str) -> None:
        """Bloquea un dispositivo (p. ej. detectado como abusivo).

        No se borra el registro: se conserva para auditoría de por qué se
        revocó y cuándo, a diferencia de un DELETE que perdería ese rastro.
        """
        ...

    def registrar_consentimiento(self, device_id: str, version: str) -> None:
        """Registra que el dispositivo aceptó el aviso de privacidad, con
        la versión exacta que se le mostró (no solo un booleano): permite
        demostrar en una auditoría qué texto concreto aceptó el usuario, y
        exigir re-consentimiento si el aviso cambia (ver
        ``obtener_version_consentimiento`` y
        ``docs/compliance/DPIA.md`` §4)."""
        ...

    def obtener_version_consentimiento(self, device_id: str) -> Optional[str]:
        """Versión del aviso que el dispositivo aceptó, o ``None`` si nunca
        aceptó ninguna (o fue revocado/no existe)."""
        ...


class RegistroDispositivosMemory:
    """Implementación en memoria — desarrollo/tests, o una sola instancia
    sin necesidad de persistir el registro entre reinicios."""

    def __init__(self) -> None:
        self._dispositivos: dict[str, dict] = {}
        self._lock = threading.Lock()

    def registrar(self) -> str:
        device_id = str(uuid.uuid4())
        with self._lock:
            self._dispositivos[device_id] = {
                "creado": datetime.now(),
                "ultimo_uso": datetime.now(),
                "revocado": False,
                "consentimiento_en": None,
                "consentimiento_version": None,
            }
        return device_id

    def marcar_uso(self, device_id: str) -> None:
        with self._lock:
            registro = self._dispositivos.get(device_id)
            if registro is not None:
                registro["ultimo_uso"] = datetime.now()

    def existe(self, device_id: str) -> bool:
        with self._lock:
            return device_id in self._dispositivos

    def esta_revocado(self, device_id: str) -> bool:
        with self._lock:
            registro = self._dispositivos.get(device_id)
            return registro is None or registro["revocado"]

    def revocar(self, device_id: str) -> None:
        with self._lock:
            registro = self._dispositivos.get(device_id)
            if registro is not None:
                registro["revocado"] = True

    def registrar_consentimiento(self, device_id: str, version: str) -> None:
        with self._lock:
            registro = self._dispositivos.get(device_id)
            if registro is not None:
                registro["consentimiento_en"] = datetime.now()
                registro["consentimiento_version"] = version

    def obtener_version_consentimiento(self, device_id: str) -> Optional[str]:
        with self._lock:
            registro = self._dispositivos.get(device_id)
            if registro is None:
                return None
            return registro["consentimiento_version"]  # type: ignore[no-any-return]


class RegistroDispositivosSQLite:
    """Implementación persistente en SQLite (backend por defecto fuera de
    tests): el registro de dispositivos debe sobrevivir un reinicio del
    proceso — si no, cada reinicio "olvidaría" qué dispositivos fueron
    revocados y readmitiría abusadores ya bloqueados.

    Tabla separada de ``messages`` (``ConversationRepository``) a
    propósito: son datos de naturaleza distinta (identidad/abuso vs.
    contenido conversacional) con ciclos de vida y sensibilidad distintos
    — no hay razón para acoplar su almacenamiento.
    """

    def __init__(self, db_path: str = "dispositivos.db") -> None:
        self.db_path = db_path
        self._inicializar_base_datos()

    def _inicializar_base_datos(self) -> None:
        with self._conexion() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dispositivos (
                    device_id TEXT PRIMARY KEY,
                    creado TEXT NOT NULL,
                    ultimo_uso TEXT NOT NULL,
                    revocado INTEGER NOT NULL DEFAULT 0,
                    consentimiento_en TEXT,
                    consentimiento_version TEXT
                )
            """)
            # Migración para bases creadas antes de estas dos columnas:
            # CREATE TABLE IF NOT EXISTS no las agrega a una tabla que ya
            # existía. PRAGMA table_info + ALTER TABLE es idempotente, así
            # que correr esto en cada arranque es seguro.
            columnas = {fila[1] for fila in conn.execute("PRAGMA table_info(dispositivos)")}
            if "consentimiento_en" not in columnas:
                conn.execute("ALTER TABLE dispositivos ADD COLUMN consentimiento_en TEXT")
            if "consentimiento_version" not in columnas:
                conn.execute("ALTER TABLE dispositivos ADD COLUMN consentimiento_version TEXT")

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        # Mismo patrón (y mismo motivo) que SQLiteConversationRepository:
        # `with sqlite3.Connection()` no cierra la conexión por sí solo.
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def registrar(self) -> str:
        device_id = str(uuid.uuid4())
        ahora = datetime.now().isoformat()
        with self._conexion() as conn:
            conn.execute(
                "INSERT INTO dispositivos (device_id, creado, ultimo_uso, revocado) "
                "VALUES (?, ?, ?, 0)",
                (device_id, ahora, ahora),
            )
        return device_id

    def marcar_uso(self, device_id: str) -> None:
        with self._conexion() as conn:
            conn.execute(
                "UPDATE dispositivos SET ultimo_uso = ? WHERE device_id = ?",
                (datetime.now().isoformat(), device_id),
            )

    def existe(self, device_id: str) -> bool:
        with self._conexion() as conn:
            cursor = conn.execute("SELECT 1 FROM dispositivos WHERE device_id = ?", (device_id,))
            return cursor.fetchone() is not None

    def esta_revocado(self, device_id: str) -> bool:
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT revocado FROM dispositivos WHERE device_id = ?", (device_id,)
            )
            row = cursor.fetchone()
            return row is None or bool(row[0])

    def revocar(self, device_id: str) -> None:
        with self._conexion() as conn:
            conn.execute("UPDATE dispositivos SET revocado = 1 WHERE device_id = ?", (device_id,))
        logger.warning("Dispositivo revocado: %s", device_id)

    def registrar_consentimiento(self, device_id: str, version: str) -> None:
        with self._conexion() as conn:
            conn.execute(
                "UPDATE dispositivos SET consentimiento_en = ?, consentimiento_version = ? "
                "WHERE device_id = ?",
                (datetime.now().isoformat(), version, device_id),
            )

    def obtener_version_consentimiento(self, device_id: str) -> Optional[str]:
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT consentimiento_version FROM dispositivos WHERE device_id = ?",
                (device_id,),
            )
            row = cursor.fetchone()
            return row[0] if row is not None else None
