"""
Crypto address entry section for GUI (Project Faraday 3.0.0 redesign).

Rebuilt on the shared widget set (SectionHeader / CardList / EntryCard /
dialogs.Dialog / LabeledEntry). All VaultManager read/write calls are
preserved byte-faithfully from the previous implementation.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from ..models.crypto_entry import CryptoEntry
from ..vault.manager import VaultManager
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
    show_status,
)


class CryptoSection:
    """Section for managing crypto address entries."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize crypto section."""
        self.vault_manager = vault_manager
        self.vault_path = vault_path
        self.note_var = tk.StringVar()
        self.frame = ttk.Frame(parent)
        self._empty_state = None
        self._build()
        self.refresh()

    def _build(self):
        """Build the view's shared chrome (header + card list)."""
        self.header = SectionHeader(
            self.frame, title="Crypto Addresses", count=0, on_add=self._add_entry
        )
        self.header.pack(
            fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"])
        )
        self.list_container = ttk.Frame(self.frame)
        self.list_container.pack(fill=tk.BOTH, expand=True)

        self.card_list = CardList(self.list_container)
        self.card_list.pack(
            fill=tk.BOTH, expand=True,
            padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]),
        )

    # ----------------------------------------------------------- public api
    def refresh(self):
        """Reload crypto addresses from the vault and rebuild the card list."""
        if self._empty_state is not None:
            try:
                self._empty_state.destroy()
            except Exception:
                pass
            self._empty_state = None
        self.card_list.clear()
        try:
            entries = list(self.vault_manager.list_entries(entry_type="crypto"))
        except Exception as e:
            messagebox.showerror("Refresh Failed", f"Unable to refresh entry list:\n{e}")
            return
        self.header.set_count(len(entries))
        if not entries:
            self.card_list.pack_forget()
            self._empty_state = EmptyState(
                self.list_container,
                message="No crypto addresses yet. Add your first address.",
                icon_name="crypto",
                action_label="Add address",
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
            title=entry.address,
            subtitle=entry.site_note or "(no note)",
            meta=entry.modified.strftime("%Y-%m-%d %H:%M"),
        )
        self.card_list.add(card)

    def _add_entry(self):
        """Open the add-address form."""
        self._open_form(None)

    def _edit(self, entry_id):
        """Open the edit form prefilled from the vault entry (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if entry is None:
            messagebox.showerror("Error", "Entry not found")
            return
        self._open_form(entry)

    def _copy(self, entry_id):
        """Copy the address of an entry to the clipboard."""
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if entry is None:
                messagebox.showerror("Error", "Entry not found")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.address, "normal", root)
            show_status(self.frame, "Address copied to clipboard (clears in 30s)", "success")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy address to clipboard:\n{e}")

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
    def _open_form(self, entry):
        """Show the add/edit dialog for a crypto address entry.

        Editing upserts the existing entry (same ``entry_id``) through
        ``add_entry`` so no delete-then-add window can lose data.
        """
        editing = entry is not None
        dlg = Dialog(
            self.frame,
            title="Edit Crypto Address" if editing else "Add Crypto Address",
            width=460, height=280,
        )

        address_field = LabeledEntry(
            dlg.content, label="Address", value=entry.address if editing else ""
        )
        address_field.pack(
            fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"])
        )
        note_field = LabeledEntry(
            dlg.content, label="Site Note", value=entry.site_note if editing else ""
        )
        note_field.pack(
            fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["md"])
        )

        btn_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        btn_row.pack(fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])

        def _on_save():
            address = address_field.get().strip()
            if not address:
                messagebox.showerror("Error", "Address is required", parent=dlg)
                return
            self.note_var.set(note_field.get().strip())
            if editing:
                if not messagebox.askyesno(
                    "Confirm",
                    "Save changes? This replaces the existing entry.",
                    parent=dlg,
                ):
                    return
            self.vault_manager.add_entry(CryptoEntry(
                address=address,
                site_note=self.note_var.get().strip(),
                entry_id=entry.entry_id if editing else None,
            ))
            dlg.destroy()
            self.refresh()
            messagebox.showinfo("Success", "Crypto entry saved")

        PrimaryButton(btn_row, text="Save", command=_on_save).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
