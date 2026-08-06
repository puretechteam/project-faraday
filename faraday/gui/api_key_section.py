"""
API/Developer keys section for GUI (Project Faraday 3.0.0 redesign).

Rebuilt on the shared widget set (SectionHeader / CardList / EntryCard /
dialogs.Dialog / SecretField / LabeledEntry). All VaultManager read/write
calls are preserved byte-faithfully from the previous implementation.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from ..models.api_key_entry import ApiKeyEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_required_field
from .clipboard_helper import copy_to_clipboard
from .action_guard import require_action_unlock
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


class ApiKeySection:
    """Section for managing API/developer keys."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize API key section."""
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
            self.frame, title="API Keys", count=0, on_add=self._add_entry
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
        """Reload API keys from the vault and rebuild the card list."""
        if self._empty_state is not None:
            try:
                self._empty_state.destroy()
            except Exception:
                pass
            self._empty_state = None
        self.card_list.clear()
        try:
            entries = list(self.vault_manager.list_entries(entry_type="api_key"))
        except Exception as e:
            messagebox.showerror("Refresh Failed", f"Unable to refresh entry list:\n{e}")
            return
        self.header.set_count(len(entries))
        if not entries:
            self.card_list.pack_forget()
            self._empty_state = EmptyState(
                self.list_container,
                message="No API keys yet. Add a developer key.",
                icon_name="key",
                action_label="Add API key",
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
            on_copy=lambda eid=entry.entry_id: self._copy_api_key(eid),
            on_edit=lambda eid=entry.entry_id: self._edit(eid),
            on_delete=lambda eid=entry.entry_id: self._delete(eid),
        )
        card.set_data(
            title=entry.service_name,
            subtitle=entry.environment,
            meta=entry.modified.strftime("%Y-%m-%d %H:%M"),
        )
        self.card_list.add(card)

    def _add_entry(self):
        """Open the add-API-key form."""
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
        if entry is None or not isinstance(entry, ApiKeyEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        self._open_form(entry)

    def _copy_api_key(self, entry_id):
        """Copy API key to the clipboard (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if entry is None or not isinstance(entry, ApiKeyEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.api_key, entry.sensitivity_level, root)
            show_status(self.frame, "API key copied to clipboard (clears in 30s)", "success")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy API key:\n{e}")

    def _copy_api_secret(self, entry_id):
        """Copy API secret to the clipboard (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if entry is None or not isinstance(entry, ApiKeyEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            if not entry.api_secret:
                messagebox.showwarning("Warning", "No API secret stored")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.api_secret, entry.sensitivity_level, root)
            show_status(self.frame, "API secret copied to clipboard (clears in 30s)", "success")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy API secret:\n{e}")

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
        """Show the add/edit dialog for an API key entry.

        Editing upserts the existing entry (same ``entry_id``) through
        ``add_entry`` so no delete-then-add window can lose data.
        """
        editing = entry is not None
        dlg = Dialog(
            self.frame,
            title="Edit API Key" if editing else "Add API Key",
            width=460, height=480,
        )

        # Reserve the button row at the bottom FIRST so it can never be
        # squeezed out by the form fields at large font scales.
        btn_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])

        service_field = LabeledEntry(
            dlg.content, label="Service Name", value=entry.service_name if editing else ""
        )
        service_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))
        key_field = SecretField(
            dlg.content, label="API Key", value=entry.api_key if editing else ""
        )
        key_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["sm"]))
        secret_field = SecretField(
            dlg.content, label="API Secret (optional)", value=entry.api_secret if editing else ""
        )
        secret_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["sm"]))

        env_label = tk.Label(dlg.content, text="Environment", anchor=tk.W)
        env_label.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))
        env_var = tk.StringVar(value=entry.environment if editing else "prod")
        env_combo = ttk.Combobox(
            dlg.content, textvariable=env_var, state="readonly", values=["prod", "dev", "staging"]
        )
        env_combo.pack(fill=tk.X, padx=SPACING["md"])

        notes_label = tk.Label(dlg.content, text="Notes", anchor=tk.W)
        notes_label.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))
        notes_text = scrolledtext.ScrolledText(dlg.content, width=50, height=3, wrap=tk.WORD)
        notes_text.pack(fill=tk.X, padx=SPACING["md"])
        if editing and entry.notes:
            notes_text.insert("1.0", entry.notes)

        note_field = LabeledEntry(
            dlg.content, label="Site Note", value=entry.site_note if editing else ""
        )
        note_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["md"]))

        def _on_save():
            service_name = service_field.get().strip()
            api_key = key_field.get().strip()
            api_secret = secret_field.get().strip()
            environment = env_var.get()
            notes = notes_text.get("1.0", tk.END).strip()

            valid, error = validate_required_field(service_name, "Service name")
            if not valid:
                messagebox.showerror("Error", error, parent=dlg)
                return

            valid, error = validate_required_field(api_key, "API key")
            if not valid:
                messagebox.showerror("Error", error, parent=dlg)
                return

            if editing:
                if not messagebox.askyesno(
                    "Confirm",
                    "Save changes? This replaces the existing entry.",
                    parent=dlg,
                ):
                    return
            self.vault_manager.add_entry(ApiKeyEntry(
                service_name=service_name,
                api_key=api_key,
                api_secret=api_secret if api_secret else None,
                environment=environment,
                notes=notes,
                site_note=note_field.get().strip(),
                entry_id=entry.entry_id if editing else None,
            ))
            dlg.destroy()
            self.refresh()
            messagebox.showinfo("Success", "API key entry added")

        PrimaryButton(btn_row, text="Save", command=_on_save).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)

    # -------------------------------------------------------------- details
    def _view_selected(self, entry_id):
        """Show entry details with copy buttons for key/secret."""
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if entry is None or not isinstance(entry, ApiKeyEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        dlg = Dialog(self.frame, title=f"API Key - {entry.service_name}", width=440, height=360)
        masked_key = "***" + entry.api_key[-4:] if len(entry.api_key) > 4 else "***"
        masked_secret = "***" if entry.api_secret else "(None)"
        body = (
            f"Entry ID: {entry.entry_id}\n"
            f"Service Name: {entry.service_name}\n"
            f"API Key: {masked_key}\n"
            f"API Secret: {masked_secret}\n"
            f"Environment: {entry.environment}\n"
            f"Notes: {entry.notes}\n"
            f"Site Note: {entry.site_note}\n"
            f"Created: {entry.created}\n"
            f"Modified: {entry.modified}"
        )
        detail = tk.Label(
            dlg.content, text=body, anchor=tk.W, justify=tk.LEFT,
            font=("Consolas", 10) if "Consolas" in tk.font.families() else ("TkFixedFont", 10),
        )
        detail.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        btn_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        btn_row.pack(fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])
        PrimaryButton(
            btn_row, text="Copy API Key",
            command=lambda: self._copy_api_key(entry.entry_id),
        ).pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
        PrimaryButton(
            btn_row, text="Copy API Secret",
            command=lambda: self._copy_api_secret(entry.entry_id),
        ).pack(side=tk.LEFT)
