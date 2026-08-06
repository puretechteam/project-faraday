"""
Username/password credential section for GUI (Project Faraday 3.0.0 redesign).

Rebuilt on the shared widget set (SectionHeader / CardList / EntryCard /
dialogs.Dialog / LabeledEntry / SecretField). All VaultManager read/write
calls are preserved byte-faithfully from the previous implementation.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from ..models.credential_entry import CredentialEntry
from ..vault.manager import VaultManager
from .widgets.dialogs import PasswordGeneratorDialog
from .action_guard import require_action_unlock
from .clipboard_helper import copy_to_clipboard
from .design_system import SPACING
from .widgets import (
    CardList,
    Dialog,
    EmptyState,
    EntryCard,
    GhostButton,
    LabeledEntry,
    PrimaryButton,
    SectionHeader,
    SecretField,
    show_status,
)


class CredentialSection:
    """Section for managing username/password entries."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize credential section."""
        self.vault_manager = vault_manager
        self.vault_path = vault_path
        self.note_var = tk.StringVar()
        self.frame = ttk.Frame(parent)
        self._empty_state = None
        self._build()
        self.refresh()

    def _build(self):
        """Build the view's shared chrome (header + toolbar + card list)."""
        self.header = SectionHeader(
            self.frame, title="Credentials", count=0, on_add=self._add_entry
        )
        self.header.pack(
            fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"])
        )

        # Toolbar: a always-reachable, obvious generator affordance so the
        # configurable password generator is never buried inside a form.
        self.toolbar = ttk.Frame(self.frame)
        self.toolbar.pack(
            fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["xs"])
        )
        GhostButton(
            self.toolbar,
            text="Generate Password",
            command=self._generate_password,
        ).pack(side=tk.LEFT)

        self.list_container = ttk.Frame(self.frame)
        self.list_container.pack(fill=tk.BOTH, expand=True)

        self.card_list = CardList(self.list_container)
        self.card_list.pack(
            fill=tk.BOTH, expand=True,
            padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]),
        )

    # ----------------------------------------------------------- public api
    def refresh(self):
        """Reload credentials from the vault and rebuild the card list."""
        if self._empty_state is not None:
            try:
                self._empty_state.destroy()
            except Exception:
                pass
            self._empty_state = None
        self.card_list.clear()
        try:
            entries = list(self.vault_manager.list_entries(entry_type="credential"))
        except Exception as e:
            messagebox.showerror("Refresh Failed", f"Unable to refresh entry list:\n{e}")
            return
        self.header.set_count(len(entries))
        if not entries:
            self.card_list.pack_forget()
            self._empty_state = EmptyState(
                self.list_container,
                message="No credentials yet. Add your first login.",
                icon_name="key",
                action_label="Add credential",
                on_action=self._add_entry,
            )
            self._empty_state.pack(
                fill=tk.BOTH, expand=True,
                padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]),
            )
            return
        self.card_list.pack(
            fill=tk.BOTH, expand=True,
            padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]),
        )
        for entry in entries:
            self._add_card(entry)

    def filter(self, query: str):
        """Filter visible cards by *query* (live, from the topbar search)."""
        if not query:
            self.card_list.filter("")
        else:
            self.card_list.filter(query)

    # ------------------------------------------------------------- plumbing
    def _add_card(self, entry):
        """Append an EntryCard for *entry* to the card list."""
        card = EntryCard(
            self.card_list,
            on_copy=lambda eid=entry.entry_id: self._copy(eid),
            on_edit=lambda eid=entry.entry_id: self._edit(eid),
            on_delete=lambda eid=entry.entry_id: self._delete(eid),
        )
        card.set_data(
            title=entry.username,
            subtitle=entry.site_note or "(no note)",
            meta=entry.modified.strftime("%Y-%m-%d %H:%M"),
        )
        self.card_list.add(card)

    def _add_entry(self):
        """Open the add-credential form."""
        self._open_form(None)

    def _generate_password(self):
        """Open the configurable generator at section level.

        On a generated password, open the Add form pre-filled with it so the
        result lands in the password field of the add/edit form (obvious and
        reachable, matching the documented dialog contract).
        """
        dlg = PasswordGeneratorDialog(self.frame, title="Password Generator")
        password = dlg.show()
        if password:
            self._open_form(None, prefill_password=password)

    def _edit(self, entry_id):
        """Open the edit form prefilled from the vault entry (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if entry is None or not isinstance(entry, CredentialEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        self._open_form(entry)

    def _copy(self, entry_id):
        """Copy the password of an entry to the clipboard (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if entry is None or not isinstance(entry, CredentialEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.password, "sensitive", root)
            show_status(self.frame, "Password copied to clipboard (clears in 30s)", "success")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy password to clipboard:\n{e}")

    def _delete(self, entry_id):
        """Delete an entry (PIN-gated, with confirmation)."""
        if not require_action_unlock(self.frame):
            return
        if not messagebox.askyesno("Confirm", "Delete this entry?"):
            return
        try:
            if self.vault_manager.delete_entry(entry_id):
                self.refresh()
                messagebox.showinfo("Success", "Entry deleted")
            else:
                messagebox.showerror("Error", "Entry not found")
        except Exception as e:
            messagebox.showerror("Deletion Failed", f"Unable to delete entry:\n{e}")

    # ----------------------------------------------------------------- form
    def _open_form(self, entry, prefill_password=None):
        """Show the add/edit dialog for a credential entry.

        Editing upserts the existing entry (same ``entry_id``) through
        ``add_entry`` so no delete-then-add window can lose data.
        ``prefill_password`` seeds the password field (e.g. from the generator).
        """
        editing = entry is not None
        dlg = Dialog(
            self.frame,
            title="Edit Credential" if editing else "Add Credential",
            width=460, height=320,
        )

        # Reserve the button row at the bottom FIRST so it can never be
        # squeezed out by the form fields at large font scales.
        btn_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])

        username_field = LabeledEntry(
            dlg.content, label="Username", value=entry.username if editing else ""
        )
        username_field.pack(
            fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"])
        )
        pw_value = prefill_password if prefill_password else (entry.password if editing else "")
        pw_field = SecretField(
            dlg.content, label="Password", value=pw_value
        )
        pw_field.pack(
            fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["sm"])
        )
        note_field = LabeledEntry(
            dlg.content, label="Site Note", value=entry.site_note if editing else ""
        )
        note_field.pack(
            fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["sm"])
        )

        def _on_save():
            username = username_field.get().strip()
            password = pw_field.get()
            if not username:
                messagebox.showerror("Error", "Username is required", parent=dlg)
                return
            if not password:
                messagebox.showerror("Error", "Password is required", parent=dlg)
                return
            self.note_var.set(note_field.get().strip())
            if editing:
                if not messagebox.askyesno(
                    "Confirm",
                    "Save changes? This replaces the existing entry.",
                    parent=dlg,
                ):
                    return
            self.vault_manager.add_entry(CredentialEntry(
                username=username,
                password=password,
                site_note=self.note_var.get().strip(),
                entry_id=entry.entry_id if editing else None,
            ))
            dlg.destroy()
            self.refresh()
            messagebox.showinfo("Success", "Credential entry saved")

        GhostButton(
            btn_row,
            text="Generate Password",
            command=lambda: PasswordGeneratorDialog(
                self.frame.winfo_toplevel(),
                callback=lambda p: pw_field.set(p),
            ),
        ).pack(side=tk.LEFT)
        PrimaryButton(btn_row, text="Save", command=_on_save).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
