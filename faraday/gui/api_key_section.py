"""
API/Developer keys section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from ..models.api_key_entry import ApiKeyEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_required_field
from .clipboard_helper import copy_to_clipboard
from .action_guard import require_action_unlock


class ApiKeySection:
    """Section for managing API/developer keys."""
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize API key section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._masked = True
        self._create_widgets()
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add API Key", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(form_frame, text="Service Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.service_name_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.service_name_var, width=50).grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="API Key:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(form_frame, textvariable=self.api_key_var, width=50, show="*" if self._masked else "")
        self.api_key_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="API Secret (optional):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.api_secret_var = tk.StringVar()
        self.api_secret_entry = ttk.Entry(form_frame, textvariable=self.api_secret_var, width=50, show="*" if self._masked else "")
        self.api_secret_entry.grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Environment:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.environment_var = tk.StringVar(value="prod")
        env_combo = ttk.Combobox(form_frame, textvariable=self.environment_var, width=47, state="readonly", values=["prod", "dev", "staging"])
        env_combo.grid(row=3, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Notes:").grid(row=4, column=0, sticky=tk.NW, pady=5)
        self.notes_text = scrolledtext.ScrolledText(form_frame, width=50, height=4, wrap=tk.WORD)
        self.notes_text.grid(row=4, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Site Note:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.note_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.note_var, width=50).grid(row=5, column=1, padx=5, pady=5, sticky=tk.EW)
        
        form_frame.columnconfigure(1, weight=1)
        
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Add Entry", command=self._add_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Toggle Masking", command=self._toggle_masking).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        
        list_frame = ttk.LabelFrame(self.frame, text="API Keys", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Service Name", "Environment", "Modified")
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
        ttk.Button(list_button_frame, text="Copy API Key", command=self._copy_api_key).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Copy API Secret", command=self._copy_api_secret).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        self._refresh_list()
    
    def _toggle_masking(self):
        """Toggle masking of sensitive fields."""
        self._masked = not self._masked
        self.api_key_entry.configure(show="*" if self._masked else "")
        self.api_secret_entry.configure(show="*" if self._masked else "")
    
    def _add_entry(self):
        """Add new API key entry."""
        service_name = self.service_name_var.get().strip()
        api_key = self.api_key_var.get().strip()
        api_secret = self.api_secret_var.get().strip()
        environment = self.environment_var.get()
        notes = self.notes_text.get("1.0", tk.END).strip()
        
        valid, error = validate_required_field(service_name, "Service name")
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        valid, error = validate_required_field(api_key, "API key")
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        try:
            self.vault_manager.add_entry(ApiKeyEntry(
                service_name=service_name,
                api_key=api_key,
                api_secret=api_secret if api_secret else None,
                environment=environment,
                notes=notes,
                site_note=self.note_var.get().strip()
            ))
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "API key entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to add API key entry:\n{e}")
    
    def _clear_form(self):
        """Clear entry form."""
        self.service_name_var.set("")
        self.api_key_var.set("")
        self.api_secret_var.set("")
        self.environment_var.set("prod")
        self.notes_text.delete("1.0", tk.END)
        self.note_var.set("")
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="api_key"):
                self.tree.insert("", tk.END, values=(
                    entry.entry_id,
                    entry.service_name[:40] + "..." if len(entry.service_name) > 40 else entry.service_name,
                    entry.environment,
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
            if not entry or not isinstance(entry, ApiKeyEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            masked_key = "***" + entry.api_key[-4:] if len(entry.api_key) > 4 else "***"
            masked_secret = "***" if entry.api_secret else "(None)"
            messagebox.showinfo("Entry Details", f"Entry ID: {entry.entry_id}\nService Name: {entry.service_name}\nAPI Key: {masked_key}\nAPI Secret: {masked_secret}\nEnvironment: {entry.environment}\nNotes: {entry.notes}\nSite Note: {entry.site_note}\nCreated: {entry.created}\nModified: {entry.modified}")
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
    
    def _copy_api_key(self):
        """Copy API key to clipboard."""
        if not require_action_unlock(self.frame):
            return
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, ApiKeyEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.api_key, entry.sensitivity_level, root)
            messagebox.showinfo("Copied", "API key copied to clipboard (will clear in 30 seconds)")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy API key:\n{e}")
    
    def _copy_api_secret(self):
        """Copy API secret to clipboard."""
        if not require_action_unlock(self.frame):
            return
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, ApiKeyEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            if not entry.api_secret:
                messagebox.showwarning("Warning", "No API secret stored")
                return
            root = self.frame.winfo_toplevel()
            copy_to_clipboard(entry.api_secret, entry.sensitivity_level, root)
            messagebox.showinfo("Copied", "API secret copied to clipboard (will clear in 30 seconds)")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", f"Unable to copy API secret:\n{e}")
    
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

