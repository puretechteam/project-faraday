"""
Credit/debit card section for the Faraday 3.0.0 GUI redesign.

Rebuilt on shared components (SectionHeader / CardList / EntryCard / Dialog)
while preserving all VaultManager read/write logic byte-faithfully.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from ..models.card_entry import CardEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_card_number, validate_cvv, validate_required_field
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


class CardSection:
    """Section for managing credit/debit card entries (3.0.0 view)."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize card section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()

    def _create_widgets(self):
        """Create the section view (header + card list)."""
        self.header = SectionHeader(
            self.frame,
            title="Cards",
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
            message="No cards yet. Add a card to get started.",
            icon_name="card",
        )

        self.refresh()

    # ------------------------------------------------------------- view api
    def refresh(self):
        """Reload entries from the VaultManager and rebuild the card list."""
        self.card_list.clear()

        entries = []
        try:
            entries = list(self.vault_manager.list_entries(entry_type="card"))
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
            masked_card = "****" + entry.card_number[-4:] if len(entry.card_number) > 4 else "****"
            exp_str = f"{entry.expiration_month:02d}/{entry.expiration_year}"
            subtitle = f"{entry.cardholder_name}  •  {masked_card}"
            card = EntryCard(
                self.card_list,
                title=entry.cardholder_name[:30] + "..." if len(entry.cardholder_name) > 30 else entry.cardholder_name,
                subtitle=f"{masked_card}  •  Exp {exp_str}",
                meta=entry.modified.strftime("%Y-%m-%d %H:%M"),
                on_copy=lambda eid=entry.entry_id: self._copy_card_number(eid),
                on_edit=lambda eid=entry.entry_id: self._open_edit_dialog(eid),
                on_delete=lambda eid=entry.entry_id: self._delete_entry(eid),
            )
            card.set_data(
                title=entry.cardholder_name[:30] + "..." if len(entry.cardholder_name) > 30 else entry.cardholder_name,
                subtitle=f"{masked_card}  •  Exp {exp_str}",
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
        """Open the add dialog for a new card."""
        self._build_form_dialog(title="Add Card", entry=None)

    def _open_edit_dialog(self, entry_id):
        """Open the edit dialog for an existing card."""
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if not entry or not isinstance(entry, CardEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return
        self._build_form_dialog(title="Edit Card", entry=entry)

    def _build_form_dialog(self, title, entry):
        """Build the shared add/edit dialog for a card."""
        dlg = Dialog(self.frame, title=title, width=520, height=430)
        content = dlg.content

        # Packed first so the action row always owns the bottom of the dialog
        # and can never be clipped by the fields above it.
        btn_row = tk.Frame(content, bd=0, highlightthickness=0)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])

        cardholder_field = LabeledEntry(content, label="Cardholder Name:")
        cardholder_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))
        if entry is not None:
            cardholder_field.set(entry.cardholder_name)

        card_number_field = SecretField(content, label="Card Number:")
        card_number_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))
        if entry is not None:
            card_number_field.set(entry.card_number)

        exp_row = tk.Frame(content, bd=0, highlightthickness=0)
        exp_row.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))
        month_field = LabeledEntry(exp_row, label="Expiration Month:")
        month_field.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, SPACING["sm"]))
        year_field = LabeledEntry(exp_row, label="Expiration Year:")
        year_field.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if entry is not None:
            month_field.set(f"{entry.expiration_month:02d}")
            year_field.set(str(entry.expiration_year))
        else:
            month_field.set("01")
            year_field.set("2024")

        cvv_field = SecretField(content, label="CVV:")
        cvv_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))
        if entry is not None:
            cvv_field.set(entry.cvv)

        zip_field = LabeledEntry(content, label="Billing ZIP:")
        zip_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))
        if entry is not None:
            zip_field.set(entry.billing_zip)

        note_field = LabeledEntry(content, label="Note (optional):")
        note_field.pack(fill=tk.X,         padx=SPACING["md"], pady=(0, SPACING["sm"]))
        if entry is not None:
            note_field.set(entry.site_note or "")

        def _save():
            cardholder = cardholder_field.get().strip()
            card_number = card_number_field.get().strip()

            valid, error = validate_required_field(cardholder, "Cardholder name")
            if not valid:
                messagebox.showerror("Error", error, parent=dlg)
                return

            valid, error = validate_card_number(card_number)
            if not valid:
                messagebox.showerror("Error", error, parent=dlg)
                return

            try:
                exp_month = int(month_field.get())
                exp_year = int(year_field.get())
            except ValueError:
                messagebox.showerror("Error", "Invalid expiration date", parent=dlg)
                return

            cvv = cvv_field.get().strip()
            valid, error = validate_cvv(cvv)
            if not valid:
                messagebox.showerror("Error", error, parent=dlg)
                return

            zip_code = zip_field.get().strip()
            valid, error = validate_required_field(zip_code, "Billing ZIP")
            if not valid:
                messagebox.showerror("Error", error, parent=dlg)
                return

            try:
                self.vault_manager.add_entry(CardEntry(
                    cardholder_name=cardholder,
                    card_number=card_number,
                    expiration_month=exp_month,
                    expiration_year=exp_year,
                    cvv=cvv,
                    billing_zip=zip_code,
                    site_note=note_field.get().strip(),
                    entry_id=entry.entry_id if entry is not None else None,
                ))
                dlg.destroy()
                self.refresh()
                messagebox.showinfo("Success", "Card entry added" if entry is None else "Card entry updated")
            except Exception as e:
                messagebox.showerror("Entry Creation Failed", f"Unable to add card entry:\n{e}", parent=dlg)

        PrimaryButton(btn_row, text="Save", command=_save).pack(side=tk.RIGHT, padx=(8, 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)

    # -------------------------------------------------------------- clipboard
    def _copy_card_number(self, entry_id):
        """Copy card number to clipboard (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, CardEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.card_number, entry.sensitivity_level, root)
            show_status(self.frame, "Card number copied to clipboard (clears in 30s)", "success")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy card number:\n{e}")

    # ---------------------------------------------------------------- delete
    def _delete_entry(self, entry_id):
        """Delete a card entry (PIN-gated)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if not entry or not isinstance(entry, CardEntry):
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
