import time

import pytest
from sqlalchemy import create_engine, inspect, text

from app.database.migrations import run_migrations
from app.database.session import (
    _make_engine,
    _normalise_host,
    _redact,
    probe_connection,
)

pytestmark = pytest.mark.unit

# Port 1 is reserved and never listening, so a connect is refused instantly.
UNREACHABLE_PG = "postgresql://u:p@127.0.0.1:1/arcas"


class TestEngineConstructionIsLazy:
    def test_create_engine_succeeds_against_a_dead_server(self):
        engine = _make_engine(UNREACHABLE_PG)
        assert engine is not None, (
            "create_engine opens no socket, so it cannot detect a stopped "
            "server. Any liveness check must issue a real query."
        )

    def test_probe_connection_detects_the_dead_server(self, monkeypatch):
        import app.database.session as session_mod

        monkeypatch.setattr(session_mod, "engine", _make_engine(UNREACHABLE_PG))
        ok, reason = probe_connection()

        assert ok is False
        assert reason, "a failed probe must explain itself"

    def test_probe_connection_succeeds_on_a_live_engine(self, monkeypatch, tmp_path):
        import app.database.session as session_mod

        url = f"sqlite:///{tmp_path / 'live.db'}"
        monkeypatch.setattr(session_mod, "engine", _make_engine(url))

        ok, reason = probe_connection()
        assert ok is True
        assert reason == ""


class TestConnectTimeout:
    def test_postgres_engines_carry_a_bounded_connect_timeout(self):
        engine = _make_engine(UNREACHABLE_PG)
        start = time.time()
        ok, _ = _probe(engine)
        assert ok is False
        assert time.time() - start < 30

    def test_sqlite_engines_allow_cross_thread_use(self, tmp_path):
        engine = _make_engine(f"sqlite:///{tmp_path / 'x.db'}")
        _, opts = engine.dialect.create_connect_args(engine.url)
        assert opts.get("check_same_thread") is False


def _probe(engine):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


class TestUrlHandling:
    def test_localhost_is_pinned_to_ipv4(self):
        assert _normalise_host(
            "postgresql://u:p@localhost:5432/arcas"
        ) == "postgresql://u:p@127.0.0.1:5432/arcas"

    def test_named_hosts_are_left_alone(self):
        url = "postgresql://u:p@postgres:5432/arcas"
        assert _normalise_host(url) == url

    def test_sqlite_urls_are_left_alone(self):
        url = "sqlite:///./arcas_fallback.db"
        assert _normalise_host(url) == url

    def test_credentials_are_redacted_for_logging(self):
        redacted = _redact("postgresql://arcas_user:s3cret@127.0.0.1:5432/arcas")
        assert "s3cret" not in redacted
        assert "arcas_user" not in redacted
        assert "127.0.0.1:5432" in redacted


class TestMigrationsArePortable:
    ADDED_COLUMNS = {"intent", "actor", "workspace_name"}

    @staticmethod
    def _legacy_table(engine):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE review_sessions ("
                    "id INTEGER PRIMARY KEY, session_id VARCHAR, "
                    "language VARCHAR, source_code TEXT)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO review_sessions "
                    "(session_id, language, source_code) "
                    "VALUES ('legacy-1', 'python', 'x = 1')"
                )
            )

    def test_migrations_run_on_sqlite(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
        self._legacy_table(engine)

        run_migrations(engine)

        columns = {c["name"] for c in inspect(engine).get_columns("review_sessions")}
        assert self.ADDED_COLUMNS <= columns

    def test_existing_rows_are_backfilled_with_the_default(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
        self._legacy_table(engine)

        run_migrations(engine)

        with engine.connect() as conn:
            intent = conn.execute(
                text("SELECT intent FROM review_sessions WHERE session_id='legacy-1'")
            ).scalar()
        assert intent == "full_review"

    def test_migrations_are_idempotent(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
        self._legacy_table(engine)

        run_migrations(engine)
        run_migrations(engine)  # must not raise

        columns = {c["name"] for c in inspect(engine).get_columns("review_sessions")}
        assert self.ADDED_COLUMNS <= columns

    def test_absent_table_is_skipped_not_failed(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
        run_migrations(engine)  # must not raise

        assert "review_sessions" not in inspect(engine).get_table_names()


class TestFallbackProducesAUsableSchema:
    def test_models_round_trip_on_the_fallback_dialect(self, tmp_path):
        from sqlalchemy.orm import sessionmaker

        from app.database.models import Base, ReviewSession

        engine = create_engine(f"sqlite:///{tmp_path / 'fallback.db'}")
        Base.metadata.create_all(bind=engine)
        run_migrations(engine)

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.add(
                ReviewSession(
                    session_id="smoke-1",
                    language="python",
                    source_code="print(1)",
                )
            )
            db.commit()

            row = db.query(ReviewSession).filter_by(session_id="smoke-1").one()
            assert row.intent == "full_review"
            assert row.actor is None
        finally:
            db.close()


@pytest.fixture(scope="module")
def client():
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    pytest.importorskip("langgraph")  # app.main imports the orchestration graph

    import app.main as main_mod

    with fastapi_testclient.TestClient(main_mod.app) as test_client:
        yield test_client


class TestDocsAreSelfHosted:
    @staticmethod
    def _remote_refs(html: str) -> list[str]:
        import re

        return re.findall(r'(?:src|href)="(https?://[^"]+)"', html)

    def test_swagger_assets_are_vendored(self):
        import app.main as main_mod

        assert main_mod.SWAGGER_ASSETS_VENDORED, (
            "Swagger UI assets are missing from app/static/. "
            "Run: python scripts/vendor_swagger_ui.py"
        )

    def test_docs_page_makes_no_remote_requests(self, client):
        html = client.get("/docs").text
        assert self._remote_refs(html) == []

    def test_redoc_page_makes_no_remote_requests(self, client):
        html = client.get("/redoc").text
        assert self._remote_refs(html) == []

    @pytest.mark.parametrize(
        "path",
        [
            "/static/swagger-ui-bundle.js",
            "/static/swagger-ui.css",
            "/static/redoc.standalone.js",
            "/static/favicon.ico",
        ],
    )
    def test_vendored_assets_are_served(self, client, path):
        response = client.get(path)
        assert response.status_code == 200
        assert len(response.content) > 1000

    def test_oauth2_redirect_is_reachable(self, client):
        assert client.get("/docs/oauth2-redirect").status_code == 200


class TestHealthReportsTruthfully:
    def test_unknown_state_is_not_reported_as_a_fault(self, monkeypatch):
        fastapi_testclient = pytest.importorskip("fastapi.testclient")
        pytest.importorskip("langgraph")

        import app.database.session as session_mod
        import app.main as main_mod

        monkeypatch.setattr(session_mod, "_connected", None)

        # No `with` block, so the lifespan never runs.
        response = fastapi_testclient.TestClient(main_mod.app).get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "unknown"

    def test_known_failure_returns_503(self, monkeypatch):
        fastapi_testclient = pytest.importorskip("fastapi.testclient")
        pytest.importorskip("langgraph")

        import app.database.session as session_mod
        import app.main as main_mod

        monkeypatch.setattr(session_mod, "_connected", False)

        response = fastapi_testclient.TestClient(main_mod.app).get("/health")

        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"

    def test_fallback_is_reported_as_degraded_not_healthy(self, monkeypatch):
        fastapi_testclient = pytest.importorskip("fastapi.testclient")
        pytest.importorskip("langgraph")

        import app.database.session as session_mod
        import app.main as main_mod

        monkeypatch.setattr(session_mod, "_connected", True)
        monkeypatch.setattr(session_mod, "_using_fallback", True)

        response = fastapi_testclient.TestClient(main_mod.app).get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "degraded", (
            "running on the SQLite fallback must never be reported as healthy"
        )
