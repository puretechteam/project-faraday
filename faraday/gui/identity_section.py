"""
Identity profile section for the Faraday 3.0.0 GUI redesign.

Rebuilt on shared components (SectionHeader / CardList / EntryCard / Dialog)
while preserving all VaultManager read/write logic byte-faithfully.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from ..models.identity_entry import IdentityEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_email, validate_required_field
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


class IdentitySection:
    """Section for managing identity profile entries (3.0.0 view)."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize identity section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()

    def _create_widgets(self):
        """Create the section view (header + card list)."""
        self.header = SectionHeader(
            self.frame,
            title="Identity",
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
            message="No identity profiles yet. Add one to get started.",
            icon_name="user",
        )

        self.refresh()

    # ------------------------------------------------------------- view api
    def refresh(self):
        """Reload entries from the VaultManager and rebuild the card list."""
        self.card_list.clear()

        entries = []
        try:
            entries = list(self.vault_manager.list_entries(entry_type="identity"))
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
            card = EntryCard(
                self.card_list,
                title=entry.full_name[:30] + "..." if len(entry.full_name) > 30 else entry.full_name,
                subtitle=entry.email[:30] + "..." if len(entry.email) > 30 else entry.email,
                meta=entry.modified.strftime("%Y-%m-%d %H:%M"),
                on_copy=lambda eid=entry.entry_id: self._copy_field(eid, "email"),
                on_edit=lambda eid=entry.entry_id: self._open_edit_dialog(eid),
                on_delete=lambda eid=entry.entry_id: self._delete_entry(eid),
            )
            card.set_data(
                title=entry.full_name[:30] + "..." if len(entry.full_name) > 30 else entry.full_name,
                subtitle=entry.email[:30] + "..." if len(entry.email) > 30 else entry.email,
                meta=entry.modified.strftime("%Y-%m-%d %H:%M"),
            )
            self.card_list.add(card)

    def filter(self, query):
        """Filter visible entries; empty query shows all."""
        if not query:
            self.card_list.filter("")
        else:
            self.card_list.filter(query)

    # --------------------------------------------------------------- add/edit
    def _open_add_dialog(self):
        """Open the add dialog for a new identity profile."""
        self._build_form_dialog(title="Add Identity Profile", entry=None)

    def _open_edit_dialog(self, entry_id):
        """Open the edit dialog for an existing identity profile."""
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if not entry or not isinstance(entry, IdentityEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        self._build_form_dialog(title="Edit Identity Profile", entry=entry)

    def _build_form_dialog(self, title, entry):
        """Build the shared add/edit dialog for an identity profile."""
        dlg = Dialog(self.frame, title=title, width=520, height=490)
        content = dlg.content

        # Packed first so the action row always owns the bottom of the dialog
        # and can never be clipped by the fields above it.
        btn_row = tk.Frame(content, bd=0, highlightthickness=0)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])

        name_field = LabeledEntry(content, label="Full Name:")
        name_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))
        address_field = LabeledEntry(content, label="Address:")
        address_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))
        phone_field = LabeledEntry(content, label="Phone:")
        phone_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))
        dob_field = LabeledEntry(content, label="Date of Birth:")
        dob_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))
        email_field = LabeledEntry(content, label="Email:")
        email_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))
        ssn_field = SecretField(content, label="SSN (optional):")
        ssn_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))
        note_field = LabeledEntry(content, label="Note (optional):")
        note_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))

        if entry is not None:
            name_field.set(entry.full_name)
            address_field.set(entry.address)
            phone_field.set(entry.phone)
            dob_field.set(entry.date_of_birth)
            email_field.set(entry.email)
            ssn_field.set(entry.social_security_number or "")
            note_field.set(entry.site_note or "")

        def _save():
            full_name = name_field.get().strip()
            address = address_field.get().strip()
            phone = phone_field.get().strip()
            dob = dob_field.get().strip()
            email = email_field.get().strip()

            valid, error = validate_required_field(full_name, "Full name")
            if not valid:
                messagebox.showerror("Error", error, parent=dlg)
                return

            if email:
                valid, error = validate_email(email)
                if not valid and error:
                    if not messagebox.askyesno("Warning", f"{error}\n\nContinue anyway?", parent=dlg):
                        return

            try:
                self.vault_manager.add_entry(IdentityEntry(
                    full_name=full_name,
                    address=address,
                    phone=phone,
                    date_of_birth=dob,
                    email=email,
                    social_security_number=ssn_field.get().strip(),
                    site_note=note_field.get().strip(),
                    entry_id=entry.entry_id if entry is not None else None,
                ))
                dlg.destroy()
                self.refresh()
                messagebox.showinfo("Success", "Identity profile entry added" if entry is None else "Identity profile entry updated")
            except Exception as e:
                messagebox.showerror("Entry Creation Failed", f"Unable to add identity entry:\n{e}", parent=dlg)

        PrimaryButton(btn_row, text="Save", command=_save).pack(side=tk.RIGHT, padx=(8, 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        if entry is not None:
            GhostButton(
                btn_row,
                text="Copy SSN",
                command=lambda eid=entry.entry_id: self._copy_field(eid, "social_security_number"),
            ).pack(side=tk.LEFT)

    # -------------------------------------------------------------- clipboard
    def _copy_field(self, entry_id, field_name):
        """Copy a field value to the clipboard (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, IdentityEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            value = getattr(entry, field_name, "")
            if not value:
                messagebox.showwarning("Warning", f"{field_name.capitalize()} is empty")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(value, entry.sensitivity_level, root)
            show_status(self.frame, f"{field_name.capitalize()} copied to clipboard (clears in 30s)", "success")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy {field_name}:\n{e}")

    # ---------------------------------------------------------------- delete
    def _delete_entry(self, entry_id):
        """Delete an identity profile entry (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if not entry or not isinstance(entry, IdentityEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
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
