"""
Username/password credential section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from ..models.credential_entry import CredentialEntry
from ..vault.manager import VaultManager
from .password_generator import PasswordGeneratorDialog


class CredentialSection:
    """Section for managing username/password entries."""
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize credential section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add Credential", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(form_frame, text="Username:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.username_var = tk.StringVar()
        username_entry = ttk.Entry(form_frame, textvariable=self.username_var, width=50)
        username_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        username_entry.configure(show="")
        ttk.Label(form_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(form_frame, textvariable=self.password_var, width=50, show="*")
        password_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        ttk.Label(form_frame, text="Site Note:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.note_var = tk.StringVar()
        note_entry = ttk.Entry(form_frame, textvariable=self.note_var, width=50)
        note_entry.grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)
        note_entry.configure(show="")
        form_frame.columnconfigure(1, weight=1)
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Add Entry", command=self._add_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Generate Password", command=self._generate_password).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        list_frame = ttk.LabelFrame(self.frame, text="Credentials", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Username", "Note", "Modified")
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
        ttk.Button(list_button_frame, text="Copy Password", command=self._copy_password).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        self._refresh_list()
    
    def _add_entry(self):
        """Add new credential entry."""
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username:
            messagebox.showerror("Error", "Username is required")
            return
        if not password:
            messagebox.showerror("Error", "Password is required")
            return
        try:
            self.vault_manager.add_entry(CredentialEntry(username=username, password=password, site_note=self.note_var.get().strip()))
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "Credential entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to add credential entry:\n{e}")
    
    def _generate_password(self):
        """Open password generator dialog."""
        PasswordGeneratorDialog(self.frame.winfo_toplevel(), callback=lambda p: self.password_var.set(p))
    
    def _clear_form(self):
        """Clear entry form."""
        self.username_var.set("")
        self.password_var.set("")
        self.note_var.set("")
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="credential"):
                self.tree.insert("", tk.END, values=(entry.entry_id, entry.username[:50] + "..." if len(entry.username) > 50 else entry.username, entry.site_note[:50] + "..." if len(entry.site_note) > 50 else entry.site_note, entry.modified.strftime("%Y-%m-%d %H:%M")), tags=(entry.entry_id,))
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
            messagebox.showinfo("Entry Details", f"Entry ID: {entry.entry_id}\nUsername: {entry.username}\nPassword: {'*' * len(entry.password)}\nNote: {entry.site_note}\nCreated: {entry.created}\nModified: {entry.modified}")
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
    
    def _copy_password(self):
        """Copy password of selected entry to clipboard."""
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, CredentialEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            root = self.frame.winfo_toplevel()
            root.clipboard_clear()
            root.clipboard_append(entry.password)
            root.after(30000, lambda: root.clipboard_clear())
            messagebox.showinfo("Copied", "Password copied to clipboard (will clear in 30 seconds)")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy password to clipboard:\n{e}")
    
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
