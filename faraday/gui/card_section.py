"""
Credit/debit card section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from ..models.card_entry import CardEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_card_number, validate_cvv, validate_required_field
from .clipboard_helper import copy_to_clipboard


class CardSection:
    """Section for managing credit/debit card entries."""
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize card section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._masked = True
        self._create_widgets()
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add Card", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(form_frame, text="Cardholder Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.cardholder_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.cardholder_var, width=50).grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Card Number:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.card_number_var = tk.StringVar()
        self.card_number_entry = ttk.Entry(form_frame, textvariable=self.card_number_var, width=50, show="*" if self._masked else "")
        self.card_number_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Expiration Month:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.exp_month_var = tk.StringVar()
        month_spinbox = ttk.Spinbox(form_frame, from_=1, to=12, textvariable=self.exp_month_var, width=10, format="%02.0f")
        month_spinbox.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(form_frame, text="Expiration Year:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.exp_year_var = tk.StringVar()
        year_spinbox = ttk.Spinbox(form_frame, from_=2024, to=2099, textvariable=self.exp_year_var, width=10)
        year_spinbox.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(form_frame, text="CVV:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.cvv_var = tk.StringVar()
        self.cvv_entry = ttk.Entry(form_frame, textvariable=self.cvv_var, width=20, show="*" if self._masked else "")
        self.cvv_entry.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(form_frame, text="Billing ZIP:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.zip_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.zip_var, width=20).grid(row=5, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(form_frame, text="Note:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.note_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.note_var, width=50).grid(row=6, column=1, padx=5, pady=5, sticky=tk.EW)
        
        form_frame.columnconfigure(1, weight=1)
        
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Add Entry", command=self._add_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Toggle Masking", command=self._toggle_masking).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        
        list_frame = ttk.LabelFrame(self.frame, text="Cards", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Cardholder", "Card Number", "Expiration", "Modified")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=200 if col == "ID" else 150)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        list_button_frame = ttk.Frame(self.frame, padding=10)
        list_button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(list_button_frame, text="Refresh", command=self._refresh_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="View Selected", command=self._view_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Copy Card Number", command=self._copy_card_number).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Copy CVV", command=self._copy_cvv).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        self._refresh_list()
    
    def _toggle_masking(self):
        """Toggle masking of sensitive fields."""
        self._masked = not self._masked
        self.card_number_entry.configure(show="*" if self._masked else "")
        self.cvv_entry.configure(show="*" if self._masked else "")
    
    def _add_entry(self):
        """Add new card entry."""
        cardholder = self.cardholder_var.get().strip()
        card_number = self.card_number_var.get().strip()
        
        valid, error = validate_required_field(cardholder, "Cardholder name")
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        valid, error = validate_card_number(card_number)
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        try:
            exp_month = int(self.exp_month_var.get())
            exp_year = int(self.exp_year_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid expiration date")
            return
        
        cvv = self.cvv_var.get().strip()
        valid, error = validate_cvv(cvv)
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        zip_code = self.zip_var.get().strip()
        valid, error = validate_required_field(zip_code, "Billing ZIP")
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        try:
            self.vault_manager.add_entry(CardEntry(
                cardholder_name=cardholder,
                card_number=card_number,
                expiration_month=exp_month,
                expiration_year=exp_year,
                cvv=cvv,
                billing_zip=zip_code,
                site_note=self.note_var.get().strip()
            ))
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "Card entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to add card entry:\n{e}")
    
    def _clear_form(self):
        """Clear entry form."""
        self.cardholder_var.set("")
        self.card_number_var.set("")
        self.exp_month_var.set("1")
        self.exp_year_var.set("2024")
        self.cvv_var.set("")
        self.zip_var.set("")
        self.note_var.set("")
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="card"):
                masked_card = "****" + entry.card_number[-4:] if len(entry.card_number) > 4 else "****"
                exp_str = f"{entry.expiration_month:02d}/{entry.expiration_year}"
                self.tree.insert("", tk.END, values=(
                    entry.entry_id,
                    entry.cardholder_name[:30] + "..." if len(entry.cardholder_name) > 30 else entry.cardholder_name,
                    masked_card,
                    exp_str,
                    entry.modified.strftime("%Y-%m-%d %H:%M")
                ), tags=(entry.entry_id,))
        except Exception as e:
            messagebox.showerror("Refresh Failed", f"Unable to refresh entry list:\n{e}")
    
    def _get_selected_id(self):
        """Get selected entry ID."""
        selection = self.tree.selection()
        if not selection:
            return None
        item = self.tree.item(selection[0])
        return item["tags"][0] if item.get("tags") else None
    
    def _view_selected(self):
        """View selected entry details."""
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, CardEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            masked_card = "****" + entry.card_number[-4:] if len(entry.card_number) > 4 else "****"
            messagebox.showinfo("Entry Details", f"Entry ID: {entry.entry_id}\nCardholder: {entry.cardholder_name}\nCard Number: {masked_card}\nExpiration: {entry.expiration_month:02d}/{entry.expiration_year}\nCVV: ***\nBilling ZIP: {entry.billing_zip}\nNote: {entry.site_note}\nCreated: {entry.created}\nModified: {entry.modified}")
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
    
    def _copy_card_number(self):
        """Copy card number to clipboard."""
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, CardEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.card_number, entry.sensitivity_level, root)
            messagebox.showinfo("Copied", "Card number copied to clipboard (will clear in 30 seconds)")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy card number:\n{e}")
    
    def _copy_cvv(self):
        """Copy CVV to clipboard."""
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, CardEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.cvv, entry.sensitivity_level, root)
            messagebox.showinfo("Copied", "CVV copied to clipboard (will clear in 30 seconds)")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy CVV:\n{e}")
    
    def _delete_selected(self):
        """Delete selected entry."""
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        if not messagebox.askyesno("Confirm", "Delete this entry?"):
            return
        try:
            if self.vault_manager.delete_entry(entry_id):
                self._refresh_list()
                messagebox.showinfo("Success", "Entry deleted")
            else:
                messagebox.showerror("Error", "Entry not found")
        except Exception as e:
            messagebox.showerror("Deletion Failed", f"Unable to delete entry:\n{e}")

