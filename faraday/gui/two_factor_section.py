"""
2FA/Recovery codes section for GUI (Project Faraday 3.0.0 redesign).

Rebuilt on the shared widget set (SectionHeader / CardList / EntryCard /
dialogs.Dialog / SecretField / LabeledEntry). All VaultManager read/write
calls are preserved byte-faithfully from the previous implementation.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from ..models.two_factor_entry import TwoFactorEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_required_field
from .clipboard_helper import copy_to_clipboard
from .action_guard import require_action_unlock, show_scrollable_secret_dialog
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


class TwoFactorSection:
    """Section for managing 2FA/recovery code entries."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize 2FA section."""
        self.vault_manager = vault_manager
        self.vault_path = vault_path
        self.note_var = tk.StringVar()
        self.frame = ttk.Frame(parent)
        self._empty_state = None
        self._build()
        self.refresh()

    def _show_sensitivity_warning(self):
        """Show warning for critical sensitivity level."""
        return messagebox.askyesno(
            "Security Warning",
            "This entry contains highly sensitive 2FA/recovery codes.\n\n"
            "These codes can be used to bypass two-factor authentication.\n"
            "Ensure you keep this data secure.\n\n"
            "Continue?"
        )

    def _build(self):
        """Build the view's shared chrome (header + card list)."""
        self.header = SectionHeader(
            self.frame, title="Two-Factor", count=0, on_add=self._add_entry
        )
        self.header.pack(
            fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"])
        )
        self.list_container = ttk.Frame(self.frame)
        self.list_container.pack(
            fill=tk.BOTH, expand=True,
            padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]),
        )
        self.card_list = CardList(self.list_container)
        self.card_list.pack(fill=tk.BOTH, expand=True)
        self._empty_state = EmptyState(
            self.list_container,
            message="No 2FA or recovery codes yet. Add your first service.",
            icon_name="shield",
            action_label="Add code",
            on_action=self._add_entry,
        )

    # ----------------------------------------------------------- public api
    def refresh(self):
        """Reload 2FA entries from the vault and rebuild the card list."""
        self.card_list.clear()
        try:
            entries = list(self.vault_manager.list_entries(entry_type="two_factor"))
        except Exception as e:
            messagebox.showerror("Refresh Failed", f"Unable to refresh entry list:\n{e}")
            return
        self.header.set_count(len(entries))
        if not entries:
            self.card_list.pack_forget()
            self._empty_state.pack(fill=tk.BOTH, expand=True)
            return
        self._empty_state.pack_forget()
        self.card_list.pack(fill=tk.BOTH, expand=True)
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
        codes_count = len(entry.backup_codes) if entry.backup_codes else 0
        subtitle = f"{codes_count} backup code{'s' if codes_count != 1 else ''}" + (" · TOTP" if entry.totp_secret else "")
        card = EntryCard(
            self.card_list,
            on_copy=lambda eid=entry.entry_id: self._view_selected(eid),
            on_edit=lambda eid=entry.entry_id: self._edit(eid),
            on_delete=lambda eid=entry.entry_id: self._delete(eid),
        )
        card.set_data(
            title=entry.service_name,
            subtitle=subtitle,
            meta=entry.modified.strftime("%Y-%m-%d %H:%M"),
        )
        self.card_list.add(card)

    def _add_entry(self):
        """Open the add-2FA form."""
        self._open_form(None)

    def _edit(self, entry_id):
        """Open the edit form prefilled from the vault entry."""
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if entry is None or not isinstance(entry, TwoFactorEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        self._open_form(entry)

    def _copy_backup_codes(self, entry_id):
        """Copy all backup codes to the clipboard (newline separated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if entry is None or not isinstance(entry, TwoFactorEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            if not entry.backup_codes:
                messagebox.showwarning("Warning", "No backup codes in this entry")
                return
            root = self.frame.winfo_toplevel()
            text = "\n".join(entry.backup_codes)
            copy_to_clipboard(text, entry.sensitivity_level, root)
            show_status(self.frame, "Backup codes copied to clipboard (clears in 30s)", "success")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", str(e))

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
        """Show the add/edit dialog for a 2FA entry.

        Editing replaces the existing entry via delete + add so the same
        VaultManager calls are reused (no new backend write path is added).
        """
        editing = entry is not None
        dlg = Dialog(
            self.frame,
            title="Edit 2FA/Recovery Codes" if editing else "Add 2FA/Recovery Codes",
            width=460, height=460,
        )

        # Packed first so the action row always owns the bottom of the dialog
        # and can never be clipped by the fields above it.
        btn_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])

        service_field = LabeledEntry(
            dlg.content, label="Service Name", value=entry.service_name if editing else ""
        )
        service_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        codes_label = tk.Label(dlg.content, text="Backup Codes (one per line)", anchor=tk.W)
        codes_label.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))
        codes_text = scrolledtext.ScrolledText(dlg.content, height=6, wrap=tk.WORD)
        codes_text.pack(fill=tk.X, padx=SPACING["md"])
        if editing and entry.backup_codes:
            codes_text.insert("1.0", "\n".join(entry.backup_codes))

        totp_field = SecretField(
            dlg.content, label="TOTP Secret (optional)", value=entry.totp_secret if editing else ""
        )
        totp_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["sm"]))

        note_field = LabeledEntry(
            dlg.content, label="Note", value=entry.site_note if editing else ""
        )
        note_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["md"]))

        def _on_save():
            service_name = service_field.get().strip()
            codes_text_value = codes_text.get("1.0", tk.END).strip()
            totp_secret = totp_field.get().strip()

            valid, error = validate_required_field(service_name, "Service name")
            if not valid:
                messagebox.showerror("Error", error, parent=dlg)
                return

            if not codes_text_value and not totp_secret:
                messagebox.showerror("Error", "At least backup codes or TOTP secret is required", parent=dlg)
                return

            backup_codes = [line.strip() for line in codes_text_value.split('\n') if line.strip()]

            if editing:
                if not messagebox.askyesno(
                    "Confirm",
                    "Save changes? This replaces the existing entry.",
                    parent=dlg,
                ):
                    return
                self.vault_manager.delete_entry(entry.entry_id)
            self.vault_manager.add_entry(TwoFactorEntry(
                service_name=service_name,
                backup_codes=backup_codes,
                totp_secret=totp_secret if totp_secret else None,
                site_note=note_field.get().strip()
            ))
            dlg.destroy()
            self.refresh()
            show_status(self.frame, "2FA entry updated" if editing else "2FA entry added", "success")

        PrimaryButton(btn_row, text="Save", command=_on_save).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        if editing:
            GhostButton(
                btn_row,
                text="Copy codes",
                command=lambda eid=entry.entry_id: self._copy_backup_codes(eid),
            ).pack(side=tk.LEFT)

    # -------------------------------------------------------------- details
    def _view_selected(self, entry_id):
        """View selected entry details (scrollable)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if entry is None or not isinstance(entry, TwoFactorEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        if entry.sensitivity_level == "critical":
            if not messagebox.askyesno(
                "Sensitive data",
                "You are about to show recovery codes and any TOTP secret on screen.\n\nContinue?",
            ):
                return
        codes_display = "\n".join(entry.backup_codes) if entry.backup_codes else "(No backup codes stored)"
        ts = (entry.totp_secret or "").strip()
        totp_display = ts if ts else "(None)"
        body = (
            f"Entry ID: {entry.entry_id}\n"
            f"Service: {entry.service_name}\n"
            f"Note: {entry.site_note}\n"
            f"Created: {entry.created}\n"
            f"Modified: {entry.modified}\n\n"
            f"--- Backup codes (one per line) ---\n{codes_display}\n\n"
            f"--- TOTP secret (if stored) ---\n{totp_display}\n"
        )
        show_scrollable_secret_dialog(self.frame, f"2FA - {entry.service_name}", body)
