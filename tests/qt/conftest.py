import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from tests.conftest import FAST_KDF  # noqa: E402

PASSWORD = "correct horse battery staple"


@pytest.fixture
def gui(qtbot, tmp_path, fast_kdf, monkeypatch):
    """A running main window with a fresh, unlocked throwaway vault."""
    import faraday.qt.services.vault_service as vs
    from faraday.qt.app import build_app

    monkeypatch.setattr(vs, "get_argon2_params", lambda level="standard": dict(FAST_KDF))
    from faraday import pin
    pin.mark_offer_shown()  # the one-time "set a PIN?" prompt is modal and would block offscreen
    app, ctx, window = build_app([])
    window.show()
    path = str(tmp_path / "gui.vault")
    ctx.service.create(path, PASSWORD.encode(), "standard")
    qtbot.waitUntil(lambda: window.shell is not None, timeout=5000)
    yield ctx, window
    for w in app.topLevelWidgets():
        if w is not window and w.isVisible() and hasattr(w, "reject"):
            w.reject()
    if ctx.service.is_unlocked:
        ctx.service.lock("manual")
    window.tray.hide()
    window.hide()
    window.deleteLater()
    qtbot.wait(10)
