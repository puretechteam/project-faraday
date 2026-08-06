"""
Secure note section for the Faraday 3.0.0 GUI redesign.

Rebuilt on shared components (SectionHeader / CardList / EntryCard / Dialog)
while preserving all VaultManager read/write logic byte-faithfully.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from ..models.secure_note_entry import SecureNoteEntry
from ..vault.manager import VaultManager
from .action_guard import require_action_unlock, show_scrollable_secret_dialog
from .design_system import SPACING, font_role
from .widgets import (
    CardList,
    Dialog,
    EmptyState,
    EntryCard,
    GhostButton,
    LabeledEntry,
    PrimaryButton,
    SectionHeader,
)


class SecureNoteSection:
    """Section for managing secure note entries (3.0.0 view)."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize secure note section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()

    def _create_widgets(self):
        """Create the section view (header + card list)."""
        self.header = SectionHeader(
            self.frame,
            title="Secure Notes",
            count=0,
            on_add=self._open_add_dialog,
        )
        self.header.pack(side=tk.TOP, fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))

        self._body = ttk.Frame(self.frame)
        self._body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))

        self.card_list = CardList(self._body)
        self.card_list.pack(fill=tk.BOTH, expand=True)

        self._empty = EmptyState(
            self._body,
            message="No secure notes yet. Add one to get started.",
            icon_name="note",
        )

        self.refresh()

    # ------------------------------------------------------------- view api
    def refresh(self):
        """Reload entries from the VaultManager and rebuild the card list."""
        for item in list(self.card_list._cards):
            try:
                item.destroy()
            except Exception:
                pass
        self.card_list.clear()

        entries = []
        try:
            entries = list(self.vault_manager.list_entries(entry_type="secure_note"))
        except Exception as e:
            messagebox.showerror("Refresh Failed", f"Unable to refresh entry list:\n{e}")
            return

        self.header.set_count(len(entries))

        if not entries:
            self.card_list.pack_forget()
            self._empty.pack(fill=tk.BOTH, expand=True)
            return

        self._empty.pack_forget()
        self.card_list.pack(fill=tk.BOTH, expand=True)

        for entry in entries:
            title_display = entry.title if entry.title else "(No title)"
            preview = entry.content[:80].replace("\n", " ")
            if len(entry.content) > 80:
                preview += "…"
            card = EntryCard(
                self.card_list,
                title=title_display,
                subtitle=preview,
                meta=entry.modified.strftime("%Y-%m-%d %H:%M"),
                on_edit=lambda eid=entry.entry_id: self._open_edit_dialog(eid),
                on_delete=lambda eid=entry.entry_id: self._delete_entry(eid),
            )
            card.set_data(title=title_display, subtitle=preview, meta=entry.modified.strftime("%Y-%m-%d %H:%M"))
            self.card_list.add(card)

    def filter(self, query):
        """Filter visible entries; empty query shows all."""
        if not query:
            self.card_list.filter("")
        else:
            self.card_list.filter(query)

    # --------------------------------------------------------------- add/edit
    def _open_add_dialog(self):
        """Open the add dialog for a new secure note."""
        self._build_form_dialog(title="Add Secure Note", entry=None)

    def _open_edit_dialog(self, entry_id):
        """Open the edit dialog for an existing secure note."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if not entry or not isinstance(entry, SecureNoteEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        self._build_form_dialog(title="Edit Secure Note", entry=entry)

    def _build_form_dialog(self, title, entry):
        """Build the shared add/edit dialog for a secure note."""
        dlg = Dialog(self.frame, title=title, width=520, height=460)
        content = dlg.content

        title_field = LabeledEntry(content, label="Title (optional):")
        title_field.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))
        if entry is not None:
            title_field.set(entry.title or "")

        tk.Label(content, text="Content:", font=font_role("body"), anchor=tk.W).pack(
            anchor=tk.W, padx=SPACING["md"], pady=(0, SPACING["xs"])
        )
        content_text = scrolledtext.ScrolledText(content, width=50, height=10, wrap=tk.WORD)
        content_text.pack(fill=tk.BOTH, expand=True, padx=SPACING["md"])
        if entry is not None:
            content_text.insert("1.0", entry.content)

        note_field = LabeledEntry(content, label="Note (optional):")
        note_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], 0))
        if entry is not None:
            note_field.set(entry.site_note or "")

        btn_row = tk.Frame(content, bd=0, highlightthickness=0)
        btn_row.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], 0))

        def _save():
            content_val = content_text.get("1.0", tk.END).strip()
            if not content_val:
                messagebox.showerror("Error", "Content is required", parent=dlg)
                return
            try:
                self.vault_manager.add_entry(SecureNoteEntry(
                    title=title_field.get().strip(),
                    content=content_val,
                    site_note=note_field.get().strip(),
                    entry_id=entry.entry_id if entry is not None else None,
                ))
                dlg.destroy()
                self.refresh()
                messagebox.showinfo("Success", "Secure note entry added" if entry is None else "Secure note entry updated")
            except Exception as e:
                messagebox.showerror("Entry Creation Failed", f"Unable to add secure note entry:\n{e}", parent=dlg)

        PrimaryButton(btn_row, text="Save", command=_save).pack(side=tk.RIGHT, padx=(8, 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)

    # ---------------------------------------------------------------- delete
    def _delete_entry(self, entry_id):
        """Delete a secure note entry (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if not entry or not isinstance(entry, SecureNoteEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        title_display = entry.title if entry.title else "(No title)"
        body = (
            f"Entry ID: {entry.entry_id}\nTitle: {title_display}\n\n--- Content ---\n{entry.content}\n\n"
            f"Created: {entry.created}\nModified: {entry.modified}"
        )
        show_scrollable_secret_dialog(self.frame, f"Secure note - {title_display}", body)
        if not messagebox.askyesno("Confirm", "Delete this entry?", parent=self.frame):
            return
        try:
            if self.vault_manager.delete_entry(entry_id):
                self.refresh()
                messagebox.showinfo("Success", "Entry deleted")
            else:
                messagebox.showerror("Error", "Entry not found")
        except Exception as e:
            messagebox.showerror("Deletion Failed", f"Unable to delete entry:\n{e}")
