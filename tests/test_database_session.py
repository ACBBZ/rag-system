import pytest

from app.api import dependencies


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def install_fake_session(monkeypatch, session):
    monkeypatch.setattr(dependencies, "get_settings", lambda: object())
    monkeypatch.setattr(dependencies, "get_async_engine", lambda settings: object())
    monkeypatch.setattr(
        dependencies,
        "get_sessionmaker",
        lambda engine: lambda: SessionContext(session),
    )


async def test_get_session_commits_after_success(monkeypatch):
    session = FakeSession()
    install_fake_session(monkeypatch, session)
    generator = dependencies.get_session()

    yielded = await anext(generator)
    assert yielded is session
    with pytest.raises(StopAsyncIteration):
        await anext(generator)

    assert session.commits == 1
    assert session.rollbacks == 0


async def test_get_session_rolls_back_after_exception(monkeypatch):
    session = FakeSession()
    install_fake_session(monkeypatch, session)
    generator = dependencies.get_session()

    assert await anext(generator) is session
    with pytest.raises(RuntimeError, match="boom"):
        await generator.athrow(RuntimeError("boom"))

    assert session.commits == 0
    assert session.rollbacks == 1
