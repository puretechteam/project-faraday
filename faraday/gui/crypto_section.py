"""
Crypto address entry section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from ..models.crypto_entry import CryptoEntry
from ..vault.manager import VaultManager
from .action_guard import require_action_unlock


class CryptoSection:
    """Section for managing crypto address entries."""
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize crypto section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add Crypto Address", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(form_frame, text="Address:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.address_var = tk.StringVar()
        address_entry = ttk.Entry(form_frame, textvariable=self.address_var, width=50)
        address_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        address_entry.configure(show="")
        ttk.Label(form_frame, text="Site Note:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.note_var = tk.StringVar()
        note_entry = ttk.Entry(form_frame, textvariable=self.note_var, width=50)
        note_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        note_entry.configure(show="")
        form_frame.columnconfigure(1, weight=1)
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Add Entry", command=self._add_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        list_frame = ttk.LabelFrame(self.frame, text="Crypto Addresses", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Address", "Note", "Modified")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=300 if col == "ID" else 150)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        list_button_frame = ttk.Frame(self.frame, padding=10)
        list_button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(list_button_frame, text="Refresh", command=self._refresh_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="View Selected", command=self._view_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        self._refresh_list()
    
    def _add_entry(self):
        """Add new crypto entry."""
        address = self.address_var.get().strip()
        if not address:
            messagebox.showerror("Error", "Address is required")
            return
        try:
            self.vault_manager.add_entry(CryptoEntry(address=address, site_note=self.note_var.get().strip()))
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "Crypto entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to add crypto address entry:\n{e}")
    
    def _clear_form(self):
        """Clear entry form."""
        self.address_var.set("")
        self.note_var.set("")
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="crypto"):
                self.tree.insert("", tk.END, values=(entry.entry_id, entry.address[:50] + "..." if len(entry.address) > 50 else entry.address, entry.site_note[:50] + "..." if len(entry.site_note) > 50 else entry.site_note, entry.modified.strftime("%Y-%m-%d %H:%M")), tags=(entry.entry_id,))
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
            if not entry:
                messagebox.showerror("Error", "Entry not found")
                return
            messagebox.showinfo("Entry Details", f"Entry ID: {entry.entry_id}\nAddress: {entry.address}\nNote: {entry.site_note}\nCreated: {entry.created}\nModified: {entry.modified}")
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
    
    def _delete_selected(self):
        """Delete selected entry."""
        if not require_action_unlock(self.frame):
            return
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
