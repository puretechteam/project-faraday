"""
Secure note section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from ..models.secure_note_entry import SecureNoteEntry
from ..vault.manager import VaultManager
from .action_guard import require_action_unlock, show_scrollable_secret_dialog


class SecureNoteSection:
    """Section for managing secure note entries."""
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize secure note section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add Secure Note", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(form_frame, text="Title (optional):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.title_var = tk.StringVar()
        title_entry = ttk.Entry(form_frame, textvariable=self.title_var, width=50)
        title_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        title_entry.configure(show="")
        ttk.Label(form_frame, text="Content:").grid(row=1, column=0, sticky=tk.NW, pady=5)
        self.content_text = scrolledtext.ScrolledText(form_frame, width=50, height=10, wrap=tk.WORD)
        self.content_text.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        form_frame.columnconfigure(1, weight=1)
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Add Entry", command=self._add_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        list_frame = ttk.LabelFrame(self.frame, text="Secure Notes", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Title", "Note", "Modified")
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
        """Add new secure note entry."""
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showerror("Error", "Content is required")
            return
        try:
            self.vault_manager.add_entry(SecureNoteEntry(
                title=self.title_var.get().strip(),
                content=content,
                site_note=""
            ))
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "Secure note entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to add secure note entry:\n{e}")
    
    def _clear_form(self):
        """Clear entry form."""
        self.title_var.set("")
        self.content_text.delete("1.0", tk.END)
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="secure_note"):
                title_display = entry.title[:50] + "..." if len(entry.title) > 50 else entry.title
                if not title_display:
                    title_display = "(No title)"
                self.tree.insert("", tk.END, values=(
                    entry.entry_id,
                    title_display,
                    entry.site_note[:50] + "..." if len(entry.site_note) > 50 else entry.site_note,
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
        if not require_action_unlock(self.frame):
            return
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, SecureNoteEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            title_display = entry.title if entry.title else "(No title)"
            body = (
                f"Entry ID: {entry.entry_id}\nTitle: {title_display}\n\n--- Content ---\n{entry.content}\n\n"
                f"Created: {entry.created}\nModified: {entry.modified}"
            )
            show_scrollable_secret_dialog(self.frame, f"Secure note - {title_display}", body)
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

