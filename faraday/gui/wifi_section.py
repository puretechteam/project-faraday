"""
Wi-Fi credentials section (Faraday 3.0.0 redesign).

Rebuilt on the shared widget kit (``faraday.gui.widgets``) while preserving the
exact :class:`VaultManager` read/write calls from the previous implementation.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from ..models.wifi_entry import WifiEntry
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
from .widgets.dialogs import PasswordGeneratorDialog


class WifiSection:
    """Section for managing Wi-Fi network credentials (view contract)."""

    SECURITY_TYPES = ["WPA2", "WPA3", "WEP", "None"]

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize Wi-Fi section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
        self.refresh()

    def _create_widgets(self):
        """Create section widgets."""
        self.header = SectionHeader(
            self.frame,
            title="Wi-Fi",
            count=0,
            on_add=self._add_dialog,
        )
        self.header.pack(side=tk.TOP, fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))

        self.list_container = ttk.Frame(self.frame)
        self.list_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))

        self.card_list = CardList(self.list_container)
        self.card_list.pack(fill=tk.BOTH, expand=True)

        self.empty_state = EmptyState(
            self.list_container,
            message="No Wi-Fi networks yet. Add one to get started.",
            icon_name="wifi",
            action_label="Add Wi-Fi",
            on_action=self._add_dialog,
        )

    def refresh(self):
        """Refresh the card list from the vault manager."""
        self.card_list.clear()
        entries = []
        try:
            entries = list(self.vault_manager.list_entries(entry_type="wifi"))
        except Exception as e:
            messagebox.showerror("Refresh Failed", f"Unable to refresh entry list:\n{e}")
            return

        for entry in entries:
            card = EntryCard(
                self.card_list,
                on_copy=lambda eid=entry.entry_id: self._copy_password(eid),
                on_edit=lambda eid=entry.entry_id: self._edit_dialog(eid),
                on_delete=lambda eid=entry.entry_id: self._delete_selected(eid),
            )
            subtitle = entry.security_type or "Unknown"
            note = getattr(entry, "site_note", "") or ""
            meta = f"{note}\nModified {entry.modified:%Y-%m-%d %H:%M}" if note else f"Modified {entry.modified:%Y-%m-%d %H:%M}"
            card.set_data(title=entry.network_name, subtitle=subtitle, meta=meta)
            self.card_list.add(card)

        self.header.set_count(len(entries))
        if entries:
            self.empty_state.pack_forget()
            self.card_list.pack(fill=tk.BOTH, expand=True)
        else:
            self.card_list.pack_forget()
            self.empty_state.pack(fill=tk.BOTH, expand=True)

    def filter(self, query: str) -> None:
        """Filter visible entries by *query* (empty -> show all)."""
        if not query:
            self.card_list.filter("")
        else:
            self.card_list.filter(query)

    # ------------------------------------------------------------------ forms
    def _add_dialog(self):
        """Open the add Wi-Fi dialog."""
        self._open_dialog(entry=None)

    def _edit_dialog(self, entry_id):
        """Open the edit Wi-Fi dialog for an existing entry."""
        if not require_action_unlock(self.frame):
            return
        entry = self.vault_manager.get_entry(entry_id)
        if not entry or not isinstance(entry, WifiEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        self._open_dialog(entry=entry)

    def _open_dialog(self, entry=None, prefill_password=None):
        """Show the add/edit dialog, pre-filled when *entry* is given."""
        is_edit = entry is not None
        dlg = Dialog(
            self.frame,
            title="Edit Wi-Fi Network" if is_edit else "Add Wi-Fi Network",
            width=460,
            height=340,
        )

        name_field = LabeledEntry(dlg.content, label="Network Name (SSID):", value=getattr(entry, "network_name", ""))
        name_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        pw_value = prefill_password if prefill_password else getattr(entry, "password", "")
        password_field = SecretField(dlg.content, label="Password:", value=pw_value)
        password_field.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))

        def _generate_into_field():
            password = PasswordGeneratorDialog(dlg, title="Password Generator").show()
            if password:
                password_field.set(password)

        gen_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        gen_row.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))
        GhostButton(gen_row, text="Generate", command=_generate_into_field).pack(side=tk.LEFT)

        sec_frame = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        sec_frame.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))
        ttk.Label(sec_frame, text="Security Type:").pack(anchor=tk.W, pady=(0, SPACING["xs"]))
        sec_var = tk.StringVar(value=getattr(entry, "security_type", "WPA2"))
        if sec_var.get() not in self.SECURITY_TYPES:
            sec_var.set("WPA2")
        sec_combo = ttk.Combobox(
            sec_frame, textvariable=sec_var, state="readonly", values=self.SECURITY_TYPES, width=20
        )
        sec_combo.pack(fill=tk.X)

        note_field = LabeledEntry(dlg.content, label="Note:", value=getattr(entry, "site_note", "") or "")
        note_field.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))

        btn_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        btn_row.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["md"]))

        PrimaryButton(
            btn_row,
            text="Save",
            command=lambda: self._save(dlg, name_field, password_field, sec_var, note_field, entry),
        ).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)

    def _save(self, dlg, name_field, password_field, sec_var, note_field, entry):
        """Validate and persist a Wi-Fi entry (add or edit)."""
        network_name = name_field.get().strip()
        password = password_field.get()
        security_type = sec_var.get()
        note = note_field.get().strip()

        valid, error = validate_required_field(network_name, "Network name")
        if not valid:
            messagebox.showerror("Error", error)
            return
        valid, error = validate_required_field(password, "Password")
        if not valid:
            messagebox.showerror("Error", error)
            return

        try:
            if entry is None:
                self.vault_manager.add_entry(WifiEntry(
                    network_name=network_name,
                    password=password,
                    security_type=security_type,
                    site_note=note
                ))
            else:
                new_entry = WifiEntry(
                    network_name=network_name,
                    password=password,
                    security_type=security_type,
                    entry_id=entry.entry_id,
                    site_note=note,
                    created=entry.created,
                )
                self.vault_manager.delete_entry(entry.entry_id)
                self.vault_manager.add_entry(new_entry)
            dlg.destroy()
            self.refresh()
            messagebox.showinfo("Success", "Wi-Fi entry updated" if entry is not None else "Wi-Fi entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to save Wi-Fi entry:\n{e}")

    # ------------------------------------------------------------- operations
    def _copy_password(self, entry_id):
        """Copy password to clipboard (gated by action PIN)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, WifiEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.password, entry.sensitivity_level, root)
            show_status(self.frame, "Wi-Fi password copied to clipboard (clears in 30s)", "success")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy password:\n{e}")

    def _delete_selected(self, entry_id):
        """Delete selected entry (gated by action PIN)."""
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
