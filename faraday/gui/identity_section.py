"""
Identity profile section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from ..models.identity_entry import IdentityEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_email, validate_required_field
from .clipboard_helper import copy_to_clipboard


class IdentitySection:
    """Section for managing identity profile entries."""
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize identity section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add Identity Profile", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(form_frame, text="Full Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.name_var, width=50).grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Address:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.address_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.address_var, width=50).grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Phone:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.phone_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.phone_var, width=50).grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Date of Birth:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.dob_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.dob_var, width=50).grid(row=3, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Email:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.email_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.email_var, width=50).grid(row=4, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Note:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.note_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.note_var, width=50).grid(row=5, column=1, padx=5, pady=5, sticky=tk.EW)
        
        form_frame.columnconfigure(1, weight=1)
        
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Add Entry", command=self._add_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        
        list_frame = ttk.LabelFrame(self.frame, text="Identity Profiles", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Full Name", "Email", "Phone", "Modified")
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
        ttk.Button(list_button_frame, text="Copy Email", command=lambda: self._copy_field("email")).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Copy Phone", command=lambda: self._copy_field("phone")).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        self._refresh_list()
    
    def _add_entry(self):
        """Add new identity entry."""
        full_name = self.name_var.get().strip()
        address = self.address_var.get().strip()
        phone = self.phone_var.get().strip()
        dob = self.dob_var.get().strip()
        email = self.email_var.get().strip()
        
        valid, error = validate_required_field(full_name, "Full name")
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        valid, error = validate_email(email)
        if not valid and error:
            # Non-blocking: just warn
            if not messagebox.askyesno("Warning", f"{error}\n\nContinue anyway?"):
                return
        
        try:
            self.vault_manager.add_entry(IdentityEntry(
                full_name=full_name,
                address=address,
                phone=phone,
                date_of_birth=dob,
                email=email,
                site_note=self.note_var.get().strip()
            ))
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "Identity profile entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to add identity entry:\n{e}")
    
    def _clear_form(self):
        """Clear entry form."""
        self.name_var.set("")
        self.address_var.set("")
        self.phone_var.set("")
        self.dob_var.set("")
        self.email_var.set("")
        self.note_var.set("")
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="identity"):
                self.tree.insert("", tk.END, values=(
                    entry.entry_id,
                    entry.full_name[:30] + "..." if len(entry.full_name) > 30 else entry.full_name,
                    entry.email[:30] + "..." if len(entry.email) > 30 else entry.email,
                    entry.phone[:20] + "..." if len(entry.phone) > 20 else entry.phone,
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
            if not entry or not isinstance(entry, IdentityEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            messagebox.showinfo("Entry Details", f"Entry ID: {entry.entry_id}\nFull Name: {entry.full_name}\nAddress: {entry.address}\nPhone: {entry.phone}\nDate of Birth: {entry.date_of_birth}\nEmail: {entry.email}\nNote: {entry.site_note}\nCreated: {entry.created}\nModified: {entry.modified}")
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
    
    def _copy_field(self, field_name: str):
        """Copy field value to clipboard."""
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
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
            messagebox.showinfo("Copied", f"{field_name.capitalize()} copied to clipboard (will clear in 30 seconds)")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy {field_name}:\n{e}")
    
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

