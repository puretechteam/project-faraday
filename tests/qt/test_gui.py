"""Offscreen tests of the Qt GUI against throwaway vaults."""

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPlainTextEdit

from faraday.models.schema import REGISTRY

pytestmark = pytest.mark.qt

SECRET = "TopSecret!Value-981"


def _add(ctx, qtbot, type_id, values):
    done = []
    ctx.service.add(REGISTRY[type_id].build(values), done.append)
    qtbot.waitUntil(lambda: bool(done), timeout=5000)
    return done[0]


def _visible_texts():
    texts = []
    for w in QApplication.allWidgets():
        if isinstance(w, QLabel):
            texts.append(w.text())
        elif isinstance(w, QLineEdit):
            texts.append(w.text())
        elif isinstance(w, QPlainTextEdit):
            texts.append(w.toPlainText())
    return texts


def test_every_page_opens(gui, qtbot):
    ctx, window = gui
    _add(ctx, qtbot, "credential", {"site_note": "example.com", "username": "alice", "password": SECRET})
    keys = ["overview", "all", *REGISTRY, "generator", "transfer", "backups", "access_log", "threat", "settings", "about"]
    for key in keys:
        window.navigate(key)
        qtbot.wait(5)
        assert window.shell.current_page().key == key


def test_editor_add_and_edit_keeps_identity(gui, qtbot):
    from faraday.qt.views.entries_view import EntryEditor
    ctx, window = gui
    spec = REGISTRY["credential"]
    saved = []
    editor = EntryEditor(window, ctx, spec, on_saved=saved.append)
    editor.inputs["site_note"].setText("github.com")
    editor.inputs["username"].setText("alice")
    editor.inputs["password"].setText(SECRET)
    editor._save()
    qtbot.waitUntil(lambda: bool(saved), timeout=5000)
    entry = ctx.service.entry(saved[0])
    created = entry.created

    editor = EntryEditor(window, ctx, spec, entry, on_saved=saved.append)
    editor.inputs["password"].setText("changed-password")
    editor._save()
    qtbot.waitUntil(lambda: len(saved) == 2, timeout=5000)
    again = ctx.service.entry(saved[0])
    assert saved[1] == saved[0] and again.created == created and again.password == "changed-password"
    assert len(ctx.service.summaries()) == 1


def test_editor_blocks_invalid_and_warns(gui, qtbot):
    from faraday.qt.views.entries_view import EntryEditor
    ctx, window = gui
    editor = EntryEditor(window, ctx, REGISTRY["card"])
    editor.inputs["cardholder_name"].setText("A")
    editor.inputs["card_number"].setText("1234")
    editor.inputs["expiration_month"].setText("13")
    editor.inputs["expiration_year"].setText("2030")
    editor.inputs["cvv"].setText("123")
    editor._save()
    assert not editor.messages["expiration_month"].isHidden()
    assert ctx.service.summaries() == []
    editor.reject()


def test_idle_lock_destroys_secrets(gui, qtbot):
    ctx, window = gui
    entry_id = _add(ctx, qtbot, "credential", {"site_note": "bank", "username": "alice", "password": SECRET})
    window.navigate("credential", entry_id)
    page = window.shell.current_page()
    rows = page.detail.findChildren(__import__("faraday.qt.views.entries_view", fromlist=["FieldRow"]).FieldRow)
    pw_row = next(r for r in rows if r.f.key == "password")
    assert SECRET not in pw_row.value.text()  # masked by default
    pw_row.toggle_reveal()  # no PIN set, so no prompt
    assert pw_row.value.text() == SECRET

    window.idle.set_milliseconds(150)
    qtbot.waitUntil(lambda: not ctx.service.is_unlocked, timeout=3000)
    qtbot.wait(50)  # let deleteLater run
    assert window.shell is None
    assert not any(SECRET in t for t in _visible_texts())


def test_clipboard_auto_clears(gui, qtbot):
    ctx, window = gui
    ctx.settings.clipboard_seconds = 1
    ctx.clipboard.copy(SECRET, "Password copied", secret=True)
    assert QGuiApplication.clipboard().text() == SECRET
    qtbot.waitUntil(lambda: QGuiApplication.clipboard().text() == "", timeout=3000)


def test_clipboard_leaves_other_content(gui, qtbot):
    ctx, window = gui
    ctx.settings.clipboard_seconds = 1
    ctx.clipboard.copy(SECRET, "Password copied", secret=True)
    QGuiApplication.clipboard().setText("something the user copied later")
    qtbot.wait(1300)
    assert QGuiApplication.clipboard().text() == "something the user copied later"


def test_lock_clears_clipboard(gui, qtbot):
    ctx, window = gui
    ctx.settings.clipboard_seconds = 0
    ctx.clipboard.copy(SECRET, "Password copied", secret=True)
    window.lock("manual")
    assert QGuiApplication.clipboard().text() == ""


def test_wrong_password_on_unlock(gui, qtbot):
    ctx, window = gui
    path = ctx.service.path
    window.lock("manual")
    view = window.unlock_view
    view.refresh(select=path)
    view.password.setText("not the password")
    view._unlock()
    qtbot.waitUntil(lambda: not view.error.isHidden(), timeout=5000)
    assert "Wrong password" in view.error.text()
    view.password.setText("correct horse battery staple")
    view._unlock()
    qtbot.waitUntil(lambda: window.shell is not None, timeout=5000)


def test_pin_lockout_falls_back_to_master_password(gui, monkeypatch):
    from faraday import pin
    from faraday.qt.services import guard as guard_mod
    from faraday.qt.widgets import dialogs
    ctx, window = gui
    pin.set_pin("4821")

    class FakePinDialog:
        def __init__(self, parent, prompt, verify, keep_trying):
            self.verify, self.keep_trying = verify, keep_trying

        def exec(self):
            while True:
                if self.verify("0000"):
                    return 1
                if not self.keep_trying():
                    return 2
    asked = []
    monkeypatch.setattr(dialogs, "PinDialog", FakePinDialog)
    monkeypatch.setattr(ctx.guard, "master_password", lambda *a, **k: asked.append(k) or b"pw")
    assert ctx.guard.require(guard_mod.SENSITIVE, window, "copy") is True
    assert asked and asked[0].get("after_pin_lockout")
    # Still locked out of PIN entry until the next unlock.
    assert ctx.guard.require(guard_mod.SENSITIVE, window, "copy") is True and len(asked) == 2
    ctx.guard.reset()
    pin.disable_pin()


def test_stylesheet_fully_substituted_for_every_theme():
    from faraday import themes
    from faraday.qt import theme
    for theme_id in themes.THEMES:
        pal = theme.build_palette(theme_id)
        assert "$" not in theme.stylesheet(pal), theme_id
        assert pal.dark == themes.is_dark(theme_id)


def test_switching_themes_from_settings(gui, qtbot):
    from faraday.qt import theme
    ctx, window = gui
    window.navigate("settings")
    page = window.shell.current_page()
    page.theme_tiles["spiral"].click()
    assert ctx.settings.theme_mode == "spiral" and theme.current().accent == "#9fd12a"
    page.accent_buttons["#F43F5E"].click()
    assert theme.current().accent.lower() == "#f43f5e"
    page.theme_accent.click()
    assert theme.current().accent == "#9fd12a"


def test_command_palette_scoring():
    from faraday.qt.views.command_palette import score
    assert score("git", "GitHub") > score("git", "Digital tag") > 0
    assert score("xyz", "GitHub") == 0


def test_totp_card_shows_live_code(gui, qtbot):
    from faraday import totp
    from faraday.qt.views.entries_view import TotpCard
    ctx, window = gui
    entry_id = _add(ctx, qtbot, "two_factor",
                    {"service_name": "GitHub", "totp_secret": "JBSWY3DPEHPK3PXP", "backup_codes": "", "site_note": ""})
    window.navigate("two_factor", entry_id)
    [card] = window.shell.current_page().detail.findChildren(TotpCard)
    expected = totp.code(totp.parse("JBSWY3DPEHPK3PXP"))
    assert card.code.text().replace(" ", "") == expected
    window.shell.copy_primary()
    assert QGuiApplication.clipboard().text() == expected


def test_export_archive_and_import_through_service(gui, qtbot, tmp_path, monkeypatch):
    import faraday.transfer.archive as archive_mod
    from faraday.transfer import importers
    from tests.conftest import FAST_KDF
    monkeypatch.setattr(archive_mod, "get_argon2_params", lambda level="standard": dict(FAST_KDF))
    ctx, window = gui
    _add(ctx, qtbot, "credential", {"site_note": "bank", "username": "alice", "password": SECRET,
                                    "url": "https://bank.example", "notes": ""})
    out = str(tmp_path / "everything.faraday")
    done = []
    ctx.service.export_archive(out, b"archive pw", done.append)
    qtbot.waitUntil(lambda: bool(done), timeout=5000)

    result = importers.load(out, b"archive pw")
    importers.split_duplicates(result, ctx.service.manager.list_entries())
    assert result.entries == [] and len(result.duplicates) == 1  # already in this vault

    result = importers.load(out, b"archive pw")
    imported = []
    ctx.service.import_entries(result.entries, result.attachments, imported.append)
    qtbot.waitUntil(lambda: bool(imported), timeout=5000)
    assert imported == [1] and len(ctx.service.summaries("credential")) == 2


def test_import_preview_dialog(gui, tmp_path):
    from faraday.qt.views.transfer_view import ImportPreviewDialog
    from faraday.transfer import importers
    ctx, window = gui
    p = tmp_path / "kp.csv"
    p.write_text('"Title","Username","Password"\n"Mail","a","b"\n', encoding="utf-8")
    result = importers.load(str(p))
    dlg = ImportPreviewDialog(window, str(p), result)
    from PySide6.QtWidgets import QPushButton
    assert "Import 1 item" in [btn.text() for btn in dlg.findChildren(QPushButton)]
    dlg.reject()


def test_only_one_page_visible_after_leaving_footer_pages(gui):
    """Leaving Settings or About used to leave Overview drawn behind the new page."""
    ctx, window = gui
    shell = window.shell
    for footer in ("settings", "about"):
        window.navigate("overview")
        window.navigate("credential")
        window.navigate(footer)
        window.navigate("credential")
        visible = [k for k, p in shell.pages.items() if p.isVisible()]
        assert visible == ["credential"], (footer, visible)
        assert shell.current_page().key == "credential"
