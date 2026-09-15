"""
Implementaciones concretas del ConversationRepository.

Actual:
- ConversationRepositoryMemory: en memoria, para desarrollo/pruebas.
- SQLiteConversationRepository: persistencia simple sin dependencias externas
  (una sola instancia del backend).
- PostgresConversationRepository: persistencia para desplegar el backend en
  varias instancias a la vez (ver ``config.Settings.usar_postgres``).
  Apagado por defecto: no requiere tener Postgres corriendo para usar el
  resto del sistema. Ver README "Escalar a múltiples instancias".
"""

import logging
import sqlite3
import threading
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator, List, Optional

from cryptography.fernet import Fernet, InvalidToken

from ..domain import Message

logger = logging.getLogger(__name__)


class ConversationRepositoryMemory:
    """Repositorio de conversaciones en memoria.

    Util para pruebas y desarrollo local (y como respaldo simple si no hay
    persistencia externa disponible). Almacena los mensajes por session_id
    en un diccionario. El resumen persistente se guarda como un Message
    con role='system'.

    Thread-safe: usa un lock RLock para permitir reentrancia.

    Acota el numero de sesiones en memoria (LRU) para evitar un crecimiento
    sin limite: cada sesion nueva o tocada se mueve al final; al superar
    ``max_sesiones`` se descarta la sesion menos recientemente usada. Sin
    este limite, un proceso de larga duracion con muchas sesiones distintas
    iria acumulando historiales para siempre y terminaria agotando memoria.
    """

    def __init__(self, max_sesiones: int = 10_000) -> None:
        self._stores: "OrderedDict[str, list[Message]]" = OrderedDict()
        self._lock = threading.RLock()
        self._max_sesiones = max_sesiones

    def _ensure_session(self, session_id: str) -> list[Message]:
        with self._lock:
            if session_id not in self._stores:
                self._evict_si_necesario()
                self._stores[session_id] = []
            self._stores.move_to_end(session_id)
            return self._stores[session_id]

    def _evict_si_necesario(self) -> None:
        """Descarta la sesion menos recientemente usada si se alcanza el limite."""
        while len(self._stores) >= self._max_sesiones:
            self._stores.popitem(last=False)

    def get_history(self, session_id: str) -> List[Message]:
        with self._lock:
            store = self._stores.get(session_id)
            if store is None:
                return []
            return list(store)

    def save_message(self, session_id: str, message: Message) -> None:
        with self._lock:
            store = self._ensure_session(session_id)
            store.append(message)

    def clear_history(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._stores:
                del self._stores[session_id]

    def get_resumen(self, session_id: str) -> str:
        """Extrae el ultimo resumen persistente (role='system')."""
        with self._lock:
            store = self._stores.get(session_id)
            if not store:
                return ""
            for msg in reversed(store):
                if msg.role == "system":
                    return msg.content
            return ""

    def save_resumen(self, session_id: str, resumen: str) -> None:
        """Guarda o actualiza el resumen persistente."""
        with self._lock:
            store = self._ensure_session(session_id)
            for i, msg in enumerate(store):
                if msg.role == "system":
                    store[i] = Message(role="system", content=resumen, timestamp=datetime.now())
                    return
            store.append(Message(role="system", content=resumen, timestamp=datetime.now()))


class SQLiteConversationRepository:
    """Repositorio de conversaciones usando SQLite.

    Usa una tabla `messages` con las columnas:
      - session_id: str
      - role: str (user|assistant|system)
      - content: str
      - timestamp: str (ISO 8601)

    Cada sesion es una conversacion identificada por su session_id.
    Los mensajes se almacenan en orden de insercion (rowid).
    """

    def __init__(
        self,
        db_path: str = "conversations.db",
        clave_cifrado: Optional[str] = None,
        retencion_dias: int = 90,
    ) -> None:
        """
        Args:
            db_path: Ruta del archivo SQLite.
            clave_cifrado: Clave Fernet (``Fernet.generate_key()``) para
                cifrar ``content`` en reposo. Antes los mensajes —incluyendo
                creencias religiosas y estado emocional, datos de categoría
                especial— se guardaban en texto plano sin ninguna opción de
                cifrado. Si es None, se guarda sin cifrar (solo aceptable en
                desarrollo local).
            retencion_dias: Días que se conservan los mensajes antes de que
                ``purgar_expirados`` pueda borrarlos. Antes no existía
                ningún límite de retención.
        """
        self.db_path = db_path
        self.retencion_dias = retencion_dias
        self._fernet = Fernet(clave_cifrado.encode("utf-8")) if clave_cifrado else None
        self._inicializar_base_datos()

    def _cifrar(self, texto: str) -> str:
        if self._fernet is None:
            return texto
        return self._fernet.encrypt(texto.encode("utf-8")).decode("ascii")

    def _descifrar(self, texto: str) -> str:
        if self._fernet is None:
            return texto
        try:
            return self._fernet.decrypt(texto.encode("ascii")).decode("utf-8")
        except InvalidToken:
            # Fila escrita sin cifrado (antes de configurar clave_cifrado, o
            # con una clave distinta): se devuelve tal cual en vez de
            # reventar toda la lectura del historial por un solo mensaje
            # ilegible. Se deja registrado para que sea detectable.
            logger.warning(
                "No se pudo descifrar un mensaje (clave rotada o dato legado); "
                "se devuelve sin descifrar."
            )
            return texto

    def _inicializar_base_datos(self) -> None:
        """Crea la tabla si no existe."""
        with self._conexion() as conn:
            # WAL permite lectores concurrentes mientras hay un escritor
            # activo, en vez del locking exclusivo del modo por defecto
            # (rollback journal): bajo varias sesiones/ventanas concurrentes
            # el modo por defecto serializa más de lo necesario.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    modelo TEXT NULL
                )
            """)
            # `rowid` no puede referenciarse explícitamente en CREATE INDEX en
            # SQLite (falla con "no such column: rowid" desde este backend
            # nunca se había ejercitado con una prueba real). No hace falta
            # de todos modos: basta indexar session_id, porque las filas ya
            # se recuperan en orden de rowid (orden de inserción) de forma
            # natural dentro de cada valor de session_id.
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages (session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp
                ON messages (timestamp)
            """)

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        """Abre una conexion a la base de datos y garantiza su cierre.

        ``sqlite3.Connection`` usada como ``with conn:`` solo hace
        commit/rollback de la transaccion: NO cierra la conexion. Usar ese
        patron directamente (como hacia esta clase antes) deja una conexion
        abierta por cada llamada a get_history/save_message/etc., agotando
        file descriptors bajo carga sostenida. Este context manager envuelve
        ese mismo patron pero cierra la conexion en el `finally`, sin cambiar
        la forma en que se usa en el resto de la clase (`with self._conexion() as conn:`).
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get_history(self, session_id: str) -> List[Message]:
        """Recupera el historial completo de una sesion, en orden."""
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT role, content, timestamp, modelo FROM messages "
                "WHERE session_id = ? ORDER BY rowid",
                (session_id,),
            )
            return [
                Message(
                    role=row["role"],
                    content=self._descifrar(row["content"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    modelo=row["modelo"],
                )
                for row in cursor.fetchall()
            ]

    def save_message(self, session_id: str, message: Message) -> None:
        """Persiste un mensaje en el historial de la sesion."""
        with self._conexion() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp, modelo) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    session_id,
                    message.role,
                    self._cifrar(message.content),
                    message.timestamp.isoformat(),
                    message.modelo,
                ),
            )

    def clear_history(self, session_id: str) -> None:
        """Elimina el historial completo de una sesion."""
        with self._conexion() as conn:
            conn.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,),
            )

    def get_resumen(self, session_id: str) -> str:
        """Extrae el ultimo resumen persistente (role='system')."""
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT content FROM messages "
                "WHERE session_id = ? AND role = 'system' "
                "ORDER BY rowid DESC LIMIT 1",
                (session_id,),
            )
            row = cursor.fetchone()
            return self._descifrar(row["content"]) if row else ""

    def save_resumen(self, session_id: str, resumen: str) -> None:
        """Guarda o actualiza el resumen persistente (upsert)."""
        resumen_cifrado = self._cifrar(resumen)
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT rowid FROM messages "
                "WHERE session_id = ? AND role = 'system' "
                "ORDER BY rowid DESC LIMIT 1",
                (session_id,),
            )
            existing = cursor.fetchone()
            if existing:
                conn.execute(
                    "UPDATE messages SET content = ?, timestamp = ? WHERE rowid = ?",
                    (resumen_cifrado, datetime.now().isoformat(), existing[0]),
                )
            else:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, timestamp) "
                    "VALUES (?, 'system', ?, ?)",
                    (session_id, resumen_cifrado, datetime.now().isoformat()),
                )

    def purgar_expirados(self, retencion_dias: Optional[int] = None) -> int:
        """Borra mensajes más antiguos que la retención configurada.

        Antes no existía ningún mecanismo de retención: la base crecía sin
        límite, acumulando indefinidamente datos sensibles (creencias,
        estado emocional) mucho después de que dejaran de tener utilidad
        para la conversación activa. Pensado para invocarse desde un job
        periódico (cron/scheduler), no en el camino de cada request.

        Args:
            retencion_dias: Sobrescribe ``self.retencion_dias`` para esta
                llamada.

        Returns:
            Número de filas borradas.
        """
        dias = retencion_dias if retencion_dias is not None else self.retencion_dias
        limite = (datetime.now() - timedelta(days=dias)).isoformat()
        with self._conexion() as conn:
            cursor = conn.execute("DELETE FROM messages WHERE timestamp < ?", (limite,))
            borradas = cursor.rowcount
        if borradas:
            logger.info("Retención: %d mensajes purgados (anteriores a %s).", borradas, limite)
        return borradas


class PostgresConversationRepository:
    """Repositorio de conversaciones usando PostgreSQL.

    Mismo esquema y mismo contrato que ``SQLiteConversationRepository``
    (misma tabla ``messages``, mismo cifrado opcional, misma política de
    retención); la diferencia es que Postgres es un servidor aparte al que
    varias instancias del backend pueden conectarse a la vez, así que este
    repositorio es el que hace falta el día que el backend deje de correr
    en un solo proceso (ver README "Escalar a múltiples instancias").

    Se apaga por defecto (``Settings.usar_postgres = False``): nada del
    resto del sistema requiere tener un servidor Postgres corriendo para
    funcionar. ``psycopg`` se importa perezosamente en el constructor, no
    al nivel del módulo, para que ``import repositories`` no falle en un
    entorno donde el extra ``postgres`` no está instalado (mismo patrón que
    ``crewai``/``langchain_openai`` en el resto del proyecto).

    Diseño deliberadamente simple: una conexión nueva por operación (como
    ``SQLiteConversationRepository``), no un pool. Bajo el volumen que
    justifica migrar a Postgres en primer lugar (necesitas más de una
    instancia, no necesariamente mucho tráfico por instancia) el overhead
    de conectar por operación no suele ser el cuello de botella; si algún
    día lo es, `psycopg_pool.ConnectionPool` es la evolución natural sin
    cambiar el contrato de esta clase hacia el resto del sistema.
    """

    def __init__(
        self,
        dsn: str,
        clave_cifrado: Optional[str] = None,
        retencion_dias: int = 90,
    ) -> None:
        """
        Args:
            dsn: Cadena de conexión de Postgres, p. ej.
                ``postgresql://usuario:password@host:5432/basededatos``.
            clave_cifrado: Igual que en ``SQLiteConversationRepository``.
            retencion_dias: Igual que en ``SQLiteConversationRepository``.
        """
        try:
            import psycopg  # noqa: F401  (solo para validar que está instalado)
        except ImportError as exc:
            raise ImportError(
                "PostgresConversationRepository requiere el extra 'postgres' "
                "(pip install -e '.[postgres]')."
            ) from exc
        self._psycopg = psycopg
        self.dsn = dsn
        self.retencion_dias = retencion_dias
        self._fernet = Fernet(clave_cifrado.encode("utf-8")) if clave_cifrado else None
        self._inicializar_base_datos()

    # --- Cifrado: misma lógica que SQLiteConversationRepository ---------
    # (no se comparte código entre ambas clases a propósito: cada una debe
    # poder evolucionar su esquema de almacenamiento sin arrastrar a la
    # otra; sí comparten el mismo contrato observable, verificado por
    # tests idénticos parametrizados sobre ambas implementaciones.)

    def _cifrar(self, texto: str) -> str:
        if self._fernet is None:
            return texto
        return self._fernet.encrypt(texto.encode("utf-8")).decode("ascii")

    def _descifrar(self, texto: str) -> str:
        if self._fernet is None:
            return texto
        try:
            return self._fernet.decrypt(texto.encode("ascii")).decode("utf-8")
        except InvalidToken:
            logger.warning(
                "No se pudo descifrar un mensaje (clave rotada o dato legado); "
                "se devuelve sin descifrar."
            )
            return texto

    @contextmanager
    def _conexion(self) -> Iterator["psycopg.Connection"]:  # type: ignore[name-defined]
        """Abre una conexión y la cierra al salir.

        A diferencia de ``sqlite3.Connection``, el context manager de
        ``psycopg.Connection`` sí cierra la conexión al salir del bloque
        ``with`` (hace commit/rollback y luego close) — no hace falta el
        envoltorio adicional que sí hizo falta para sqlite3.
        """
        with self._psycopg.connect(self.dsn, autocommit=True) as conn:
            yield conn

    def _inicializar_base_datos(self) -> None:
        with self._conexion() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    modelo TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages (timestamp)"
            )

    def get_history(self, session_id: str) -> List[Message]:
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT role, content, timestamp, modelo FROM messages "
                "WHERE session_id = %s ORDER BY id",
                (session_id,),
            )
            return [
                Message(
                    role=row[0], 
                    content=self._descifrar(row[1]), 
                    timestamp=row[2],
                    modelo=row[3]
                )
                for row in cursor.fetchall()
            ]

    def save_message(self, session_id: str, message: Message) -> None:
        with self._conexion() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp, modelo) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    session_id, 
                    message.role, 
                    self._cifrar(message.content), 
                    message.timestamp,
                    message.modelo
                ),
            )

    def clear_history(self, session_id: str) -> None:
        with self._conexion() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))

    def get_resumen(self, session_id: str) -> str:
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT content FROM messages "
                "WHERE session_id = %s AND role = 'system' ORDER BY id DESC LIMIT 1",
                (session_id,),
            )
            row = cursor.fetchone()
            return self._descifrar(row[0]) if row else ""

    def save_resumen(self, session_id: str, resumen: str) -> None:
        """Guarda o actualiza el resumen persistente.

        Usa ``INSERT ... ON CONFLICT`` no aplica aquí (no hay una columna
        única de "resumen actual" en el esquema compartido con SQLite); se
        resuelve igual que allá, con un SELECT + UPDATE/INSERT explícito
        dentro de la misma conexión ``autocommit`` — el resumen no está en
        la ruta caliente de escrituras concurrentes de la misma sesión
        (siempre es la misma conversación respondiendo a un mismo
        creyente), así que la carrera SELECT→UPDATE entre dos requests de
        sesiones distintas no aplica; entre requests de la *misma* sesión,
        el caso de uso ya las serializa (una respuesta a la vez por turno).
        """
        resumen_cifrado = self._cifrar(resumen)
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT id FROM messages "
                "WHERE session_id = %s AND role = 'system' ORDER BY id DESC LIMIT 1",
                (session_id,),
            )
            existing = cursor.fetchone()
            if existing:
                conn.execute(
                    "UPDATE messages SET content = %s, timestamp = %s WHERE id = %s",
                    (resumen_cifrado, datetime.now(), existing[0]),
                )
            else:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, timestamp) "
                    "VALUES (%s, 'system', %s, %s)",
                    (session_id, resumen_cifrado, datetime.now()),
                )

    def purgar_expirados(self, retencion_dias: Optional[int] = None) -> int:
        """Igual semántica que ``SQLiteConversationRepository.purgar_expirados``."""
        dias = retencion_dias if retencion_dias is not None else self.retencion_dias
        limite = datetime.now() - timedelta(days=dias)
        with self._conexion() as conn:
            cursor = conn.execute("DELETE FROM messages WHERE timestamp < %s", (limite,))
            borradas: int = cursor.rowcount
        if borradas:
            logger.info("Retención: %d mensajes purgados (anteriores a %s).", borradas, limite)
        return borradas
