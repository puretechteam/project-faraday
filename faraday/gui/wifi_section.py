"""
Wi-Fi credentials section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from ..models.wifi_entry import WifiEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_required_field
from .clipboard_helper import copy_to_clipboard


class WifiSection:
    """Section for managing Wi-Fi network credentials."""
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize Wi-Fi section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add Wi-Fi Network", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(form_frame, text="Network Name (SSID):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.network_name_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.network_name_var, width=50).grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(form_frame, textvariable=self.password_var, width=50, show="*")
        password_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Security Type:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.security_type_var = tk.StringVar(value="WPA2")
        security_combo = ttk.Combobox(form_frame, textvariable=self.security_type_var, width=47, state="readonly", values=["WPA2", "WPA3", "WEP", "None"])
        security_combo.grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Note:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.note_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.note_var, width=50).grid(row=3, column=1, padx=5, pady=5, sticky=tk.EW)
        
        form_frame.columnconfigure(1, weight=1)
        
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Add Entry", command=self._add_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        
        list_frame = ttk.LabelFrame(self.frame, text="Wi-Fi Networks", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Network Name", "Security Type", "Modified")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=250 if col == "ID" else 200)
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
        """Add new Wi-Fi entry."""
        network_name = self.network_name_var.get().strip()
        password = self.password_var.get()
        security_type = self.security_type_var.get()
        
        valid, error = validate_required_field(network_name, "Network name")
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        valid, error = validate_required_field(password, "Password")
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        try:
            self.vault_manager.add_entry(WifiEntry(
                network_name=network_name,
                password=password,
                security_type=security_type,
                site_note=self.note_var.get().strip()
            ))
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "Wi-Fi entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to add Wi-Fi entry:\n{e}")
    
    def _clear_form(self):
        """Clear entry form."""
        self.network_name_var.set("")
        self.password_var.set("")
        self.security_type_var.set("WPA2")
        self.note_var.set("")
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="wifi"):
                self.tree.insert("", tk.END, values=(
                    entry.entry_id,
                    entry.network_name[:40] + "..." if len(entry.network_name) > 40 else entry.network_name,
                    entry.security_type,
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
            if not entry or not isinstance(entry, WifiEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            messagebox.showinfo("Entry Details", f"Entry ID: {entry.entry_id}\nNetwork Name: {entry.network_name}\nPassword: {'*' * len(entry.password)}\nSecurity Type: {entry.security_type}\nNote: {entry.site_note}\nCreated: {entry.created}\nModified: {entry.modified}")
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
    
    def _copy_password(self):
        """Copy password to clipboard."""
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, WifiEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.password, entry.sensitivity_level, root)
            messagebox.showinfo("Copied", "Password copied to clipboard (will clear in 30 seconds)")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy password:\n{e}")
    
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

