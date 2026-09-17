"""Tests para ConversationRepositoryMemory y SQLiteConversationRepository."""

import sqlite3
import threading
from datetime import datetime

import pytest

from la_santisima_conversacional.domain import Message
from la_santisima_conversacional.infrastructure.repositories import (
    ConversationRepositoryMemory,
    SQLiteConversationRepository,
)


class TestConversationRepositoryMemory:
    """Test cases para el repositorio en memoria."""

    def test_get_history_empty(self):
        repo = ConversationRepositoryMemory()
        history = repo.get_history("s1")
        assert history == []

    def test_save_and_get_message(self):
        repo = ConversationRepositoryMemory()
        msg = Message(role="user", content="Hola", timestamp=datetime.now())
        repo.save_message("s1", msg)
        history = repo.get_history("s1")
        assert len(history) == 1
        assert history[0].content == "Hola"
        assert history[0].role == "user"

    def test_clear_history(self):
        repo = ConversationRepositoryMemory()
        repo.save_message("s1", Message(role="user", content="Hola"))
        repo.clear_history("s1")
        assert repo.get_history("s1") == []

    def test_save_resumen(self):
        repo = ConversationRepositoryMemory()
        repo.save_resumen("s1", "Resumen de la conversación")
        resumen = repo.get_resumen("s1")
        assert resumen == "Resumen de la conversación"

    def test_update_resumen(self):
        repo = ConversationRepositoryMemory()
        repo.save_resumen("s1", "Versión 1")
        repo.save_resumen("s1", "Versión 2")
        resumen = repo.get_resumen("s1")
        assert resumen == "Versión 2"

    def test_get_resumen_empty(self):
        repo = ConversationRepositoryMemory()
        assert repo.get_resumen("no-existe") == ""

    def test_thread_safety_concurrent_writes(self):
        """Verifica que escrituras concurrentes no corrompen el estado."""
        repo = ConversationRepositoryMemory()
        n_threads = 20
        msgs_per_thread = 50

        def writer(session_id: str, start: int):
            for i in range(start, start + msgs_per_thread):
                repo.save_message(
                    session_id, Message(role="user", content=f"msg-{i}", timestamp=datetime.now())
                )

        threads = []
        for t_id in range(n_threads):
            t = threading.Thread(
                target=writer, args=(f"session-{t_id % 5}", t_id * msgs_per_thread)
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verificar que cada sesión tiene el número correcto de mensajes
        expected_per_session = (n_threads // 5) * msgs_per_thread
        for sid in range(5):
            history = repo.get_history(f"session-{sid}")
            assert (
                len(history) == expected_per_session
            ), f"session-{sid} esperaba {expected_per_session} mensajes, tiene {len(history)}"

    def test_thread_safety_save_resumen_concurrente(self):
        """Verifica que save_resumen concurrente no cause race conditions."""
        repo = ConversationRepositoryMemory()
        n_threads = 10

        def writer(t_id: int):
            repo.save_resumen("s1", f"resumen-{t_id}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Después de escrituras concurrentes, debe haber exactamente 1 system message
        history = repo.get_history("s1")
        system_msgs = [m for m in history if m.role == "system"]
        assert len(system_msgs) == 1, f"Debe haber exactamente 1 resumen, hay {len(system_msgs)}"
        # El contenido debe ser uno de los escritos
        assert system_msgs[0].content.startswith("resumen-")

    def test_evita_crecimiento_sin_limite_descartando_lru(self):
        """Regresión: sin límite, un proceso de larga duración acumularía
        sesiones para siempre. Con max_sesiones, la sesión menos
        recientemente usada se descarta al llegar al límite."""
        repo = ConversationRepositoryMemory(max_sesiones=3)
        for i in range(3):
            repo.save_message(f"s{i}", Message(role="user", content="hola"))

        # Tocar s0 para que sea la más reciente y no la descarten.
        repo.save_message("s0", Message(role="user", content="de nuevo"))

        # Nueva sesión debe forzar el descarte de la menos reciente (s1).
        repo.save_message("s3", Message(role="user", content="hola"))

        assert repo.get_history("s1") == [], "s1 debía descartarse por LRU"
        assert len(repo.get_history("s0")) == 2, "s0 no debía descartarse (se usó después)"
        assert len(repo.get_history("s3")) == 1


class TestSQLiteConversationRepository:
    """Test cases para el repositorio SQLite (backend de producción)."""

    @pytest.fixture
    def db_path(self, tmp_path):
        return str(tmp_path / "test_conversations.db")

    def test_get_history_empty(self, db_path):
        repo = SQLiteConversationRepository(db_path=db_path)
        assert repo.get_history("s1") == []

    def test_save_and_get_message_preserva_orden(self, db_path):
        repo = SQLiteConversationRepository(db_path=db_path)
        repo.save_message("s1", Message(role="user", content="uno", timestamp=datetime.now()))
        repo.save_message("s1", Message(role="assistant", content="dos", timestamp=datetime.now()))

        historial = repo.get_history("s1")
        assert [m.content for m in historial] == ["uno", "dos"]

    def test_sesiones_distintas_no_se_mezclan(self, db_path):
        repo = SQLiteConversationRepository(db_path=db_path)
        repo.save_message("s1", Message(role="user", content="de s1"))
        repo.save_message("s2", Message(role="user", content="de s2"))

        assert [m.content for m in repo.get_history("s1")] == ["de s1"]
        assert [m.content for m in repo.get_history("s2")] == ["de s2"]

    def test_clear_history(self, db_path):
        repo = SQLiteConversationRepository(db_path=db_path)
        repo.save_message("s1", Message(role="user", content="hola"))
        repo.clear_history("s1")
        assert repo.get_history("s1") == []

    def test_save_and_get_resumen_upsert(self, db_path):
        repo = SQLiteConversationRepository(db_path=db_path)
        repo.save_resumen("s1", "version 1")
        repo.save_resumen("s1", "version 2")
        assert repo.get_resumen("s1") == "version 2"
        # No debe crear un mensaje 'system' por cada save (upsert real).
        systems = [m for m in repo.get_history("s1") if m.role == "system"]
        assert len(systems) == 1

    def test_get_resumen_vacio_si_no_existe(self, db_path):
        repo = SQLiteConversationRepository(db_path=db_path)
        assert repo.get_resumen("no-existe") == ""

    def test_cifrado_en_reposo(self, db_path):
        """El contenido debe ser ilegible directamente en la tabla cuando
        se configura clave_cifrado, y descifrarse correctamente al leer vía
        el repositorio. SQLite es el backend por defecto (Settings.
        usar_sqlite=True); este test antes solo existía para Postgres
        (opt-in), dejando sin verificar el cifrado en el camino que
        realmente corre out-of-the-box."""
        from cryptography.fernet import Fernet

        clave_cifrado = Fernet.generate_key().decode()
        repo = SQLiteConversationRepository(db_path=db_path, clave_cifrado=clave_cifrado)
        repo.save_message("s1", Message(role="user", content="secreto devocional"))

        conn = sqlite3.connect(db_path)
        contenido_crudo = conn.execute(
            "SELECT content FROM messages WHERE session_id = 's1'"
        ).fetchone()[0]
        conn.close()
        assert "secreto devocional" not in contenido_crudo

        assert repo.get_history("s1")[0].content == "secreto devocional"

    def test_purgar_expirados_borra_solo_mensajes_viejos(self, db_path):
        from datetime import timedelta

        repo = SQLiteConversationRepository(db_path=db_path)
        viejo = (datetime.now() - timedelta(days=100)).isoformat()
        reciente = datetime.now().isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) "
            "VALUES ('s1', 'user', 'viejo', ?), ('s1', 'user', 'reciente', ?)",
            (viejo, reciente),
        )
        conn.commit()
        conn.close()

        borradas = repo.purgar_expirados(retencion_dias=90)
        assert borradas == 1
        assert [m.content for m in repo.get_history("s1")] == ["reciente"]

    def test_conexiones_se_cierran_tras_cada_operacion(self, db_path):
        """Regresión de bug crítico: `with sqlite3.Connection() as conn` solo
        hace commit/rollback, NO cierra la conexión. Antes, cada llamada a
        get_history/save_message/etc. dejaba una conexión abierta para
        siempre, agotando file descriptors bajo carga sostenida."""
        repo = SQLiteConversationRepository(db_path=db_path)

        cierres = []

        class ConexionEspia(sqlite3.Connection):
            def close(self):
                cierres.append(self)
                super().close()

        import unittest.mock as mock

        original_connect = sqlite3.connect

        def connect_con_espia(*args, **kwargs):
            kwargs["factory"] = ConexionEspia
            return original_connect(*args, **kwargs)

        with mock.patch("sqlite3.connect", side_effect=connect_con_espia):
            repo.save_message("s1", Message(role="user", content="hola"))
            repo.get_history("s1")
            repo.save_resumen("s1", "resumen")
            repo.get_resumen("s1")
            repo.clear_history("s1")

        assert len(cierres) == 5, (
            "Cada operación debe abrir y CERRAR su propia conexión; "
            f"se cerraron {len(cierres)} de 5 esperadas."
        )
