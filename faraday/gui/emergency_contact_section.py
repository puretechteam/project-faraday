"""
Emergency/trusted contact section for GUI (Project Faraday 3.0.0 redesign).

Rebuilt on the shared widget set (SectionHeader / CardList / EntryCard /
dialogs.Dialog / LabeledEntry). All VaultManager read/write calls are
preserved byte-faithfully from the previous implementation.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from ..models.emergency_contact_entry import EmergencyContactEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_required_field, validate_email
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
    show_status,
)


class EmergencyContactSection:
    """Section for managing emergency contact entries."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize emergency contact section."""
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
            self.frame, title="Emergency Contacts", count=0, on_add=self._add_entry
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
            message="No emergency contacts yet. Add a trusted contact.",
            icon_name="emergency",
            action_label="Add contact",
            on_action=self._add_entry,
        )

    # ----------------------------------------------------------- public api
    def refresh(self):
        """Reload emergency contacts from the vault and rebuild the card list."""
        self.card_list.clear()
        try:
            entries = list(self.vault_manager.list_entries(entry_type="emergency_contact"))
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
        card = EntryCard(
            self.card_list,
            on_copy=lambda eid=entry.entry_id: self._view_selected(eid),
            on_edit=lambda eid=entry.entry_id: self._edit(eid),
            on_delete=lambda eid=entry.entry_id: self._delete(eid),
        )
        card.set_data(
            title=entry.contact_name,
            subtitle=entry.relationship or "(no relationship)",
            meta=entry.modified.strftime("%Y-%m-%d %H:%M"),
        )
        self.card_list.add(card)

    def _add_entry(self):
        """Open the add-contact form."""
        self._open_form(None)

    def _edit(self, entry_id):
        """Open the edit form prefilled from the vault entry."""
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if entry is None or not isinstance(entry, EmergencyContactEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        self._open_form(entry)

    def _copy_field(self, entry_id, field_name):
        """Copy a field value to the clipboard (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if entry is None or not isinstance(entry, EmergencyContactEntry):
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
        """Show the add/edit dialog for an emergency contact entry.

        Editing replaces the existing entry via delete + add so the same
        VaultManager calls are reused (no new backend write path is added).
        """
        editing = entry is not None
        dlg = Dialog(
            self.frame,
            title="Edit Emergency Contact" if editing else "Add Emergency Contact",
            width=460, height=540,
        )

        # Packed first so the action row always owns the bottom of the dialog
        # and can never be clipped by the fields above it.
        btn_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])

        name_field = LabeledEntry(
            dlg.content, label="Contact Name", value=entry.contact_name if editing else ""
        )
        name_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))
        rel_field = LabeledEntry(
            dlg.content, label="Relationship", value=entry.relationship if editing else ""
        )
        rel_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["sm"]))
        phone_field = LabeledEntry(
            dlg.content, label="Phone", value=entry.phone if editing else ""
        )
        phone_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["sm"]))
        email_field = LabeledEntry(
            dlg.content, label="Email", value=entry.email if editing else ""
        )
        email_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["sm"]))
        addr_field = LabeledEntry(
            dlg.content, label="Address", value=entry.address if editing else ""
        )
        addr_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["sm"]))
        note_field = LabeledEntry(
            dlg.content, label="Site Note", value=entry.site_note if editing else ""
        )
        note_field.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["md"]))

        med_label = tk.Label(dlg.content, text="Medical Notes (optional)", anchor=tk.W)
        med_label.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))
        med_text = scrolledtext.ScrolledText(dlg.content, height=3, wrap=tk.WORD)
        med_text.pack(fill=tk.X, padx=SPACING["md"])
        if editing and entry.medical_notes:
            med_text.insert("1.0", entry.medical_notes)

        ins_label = tk.Label(dlg.content, text="Instructions (optional)", anchor=tk.W)
        ins_label.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))
        ins_text = scrolledtext.ScrolledText(dlg.content, height=3, wrap=tk.WORD)
        ins_text.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["md"]))

        def _on_save():
            contact_name = name_field.get().strip()
            relationship = rel_field.get().strip()
            phone = phone_field.get().strip()
            email = email_field.get().strip()
            address = addr_field.get().strip()
            medical_notes = med_text.get("1.0", tk.END).strip()
            instructions = ins_text.get("1.0", tk.END).strip()

            valid, error = validate_required_field(contact_name, "Contact name")
            if not valid:
                messagebox.showerror("Error", error, parent=dlg)
                return

            valid, error = validate_email(email)
            if not valid and error:
                if not messagebox.askyesno("Warning", f"{error}\n\nContinue anyway?", parent=dlg):
                    return

            if editing:
                if not messagebox.askyesno(
                    "Confirm",
                    "Save changes? This replaces the existing entry.",
                    parent=dlg,
                ):
                    return
                self.vault_manager.delete_entry(entry.entry_id)
            self.vault_manager.add_entry(EmergencyContactEntry(
                contact_name=contact_name,
                relationship=relationship,
                phone=phone,
                email=email,
                address=address,
                medical_notes=medical_notes if medical_notes else None,
                instructions=instructions if instructions else None,
                site_note=note_field.get().strip()
            ))
            dlg.destroy()
            self.refresh()
            messagebox.showinfo("Success", "Entry updated" if editing else "Entry added")

        PrimaryButton(btn_row, text="Save", command=_on_save).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)

    # -------------------------------------------------------------- details
    def _view_selected(self, entry_id):
        """Show entry details with copy buttons for phone/email."""
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if entry is None or not isinstance(entry, EmergencyContactEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        dlg = Dialog(self.frame, title=f"Contact - {entry.contact_name}", width=440, height=420)
        medical_display = entry.medical_notes if entry.medical_notes else "(None)"
        instructions_display = entry.instructions if entry.instructions else "(None)"
        body = (
            f"Entry ID: {entry.entry_id}\n"
            f"Contact Name: {entry.contact_name}\n"
            f"Relationship: {entry.relationship}\n"
            f"Phone: {entry.phone}\n"
            f"Email: {entry.email}\n"
            f"Address: {entry.address}\n"
            f"Medical Notes: {medical_display}\n"
            f"Instructions: {instructions_display}\n"
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
            btn_row, text="Copy Phone",
            command=lambda: self._copy_field(entry.entry_id, "phone"),
        ).pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
        PrimaryButton(
            btn_row, text="Copy Email",
            command=lambda: self._copy_field(entry.entry_id, "email"),
        ).pack(side=tk.LEFT)
