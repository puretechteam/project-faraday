"""
2FA/Recovery codes section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from ..models.two_factor_entry import TwoFactorEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_required_field
from .clipboard_helper import copy_to_clipboard
from .action_guard import require_action_unlock, show_scrollable_secret_dialog


class TwoFactorSection:
    """Section for managing 2FA/recovery code entries."""
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize 2FA section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _show_sensitivity_warning(self):
        """Show warning for critical sensitivity level."""
        return messagebox.askyesno(
            "Security Warning",
            "This entry contains highly sensitive 2FA/recovery codes.\n\n"
            "These codes can be used to bypass two-factor authentication.\n"
            "Ensure you keep this data secure.\n\n"
            "Continue?"
        )
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add 2FA/Recovery Codes", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(form_frame, text="Service Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.service_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.service_var, width=50).grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Backup Codes (one per line):").grid(row=1, column=0, sticky=tk.NW, pady=5)
        self.codes_text = scrolledtext.ScrolledText(form_frame, width=50, height=8, wrap=tk.WORD)
        self.codes_text.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="TOTP Secret (optional):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.totp_var = tk.StringVar()
        totp_entry = ttk.Entry(form_frame, textvariable=self.totp_var, width=50, show="*")
        totp_entry.grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Note:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.note_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.note_var, width=50).grid(row=3, column=1, padx=5, pady=5, sticky=tk.EW)
        
        form_frame.columnconfigure(1, weight=1)
        
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Add Entry", command=self._add_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        
        list_frame = ttk.LabelFrame(self.frame, text="2FA/Recovery Codes", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Service Name", "Codes Count", "Has TOTP", "Modified")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=200 if col == "ID" else 120)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        list_button_frame = ttk.Frame(self.frame, padding=10)
        list_button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(list_button_frame, text="Refresh", command=self._refresh_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="View Selected", command=self._view_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Copy backup codes", command=self._copy_backup_codes).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        self._refresh_list()
    
    def _add_entry(self):
        """Add new 2FA entry."""
        service_name = self.service_var.get().strip()
        codes_text = self.codes_text.get("1.0", tk.END).strip()
        totp_secret = self.totp_var.get().strip()
        
        valid, error = validate_required_field(service_name, "Service name")
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        if not codes_text and not totp_secret:
            messagebox.showerror("Error", "At least backup codes or TOTP secret is required")
            return
        
        # Show sensitivity warning for critical entries
        if not self._show_sensitivity_warning():
            return
        
        backup_codes = [line.strip() for line in codes_text.split('\n') if line.strip()]
        
        try:
            self.vault_manager.add_entry(TwoFactorEntry(
                service_name=service_name,
                backup_codes=backup_codes,
                totp_secret=totp_secret if totp_secret else None,
                site_note=self.note_var.get().strip()
            ))
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "2FA entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to add 2FA entry:\n{e}")
    
    def _clear_form(self):
        """Clear entry form."""
        self.service_var.set("")
        self.codes_text.delete("1.0", tk.END)
        self.totp_var.set("")
        self.note_var.set("")
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="two_factor"):
                codes_count = len(entry.backup_codes) if entry.backup_codes else 0
                has_totp = "Yes" if entry.totp_secret else "No"
                self.tree.insert("", tk.END, values=(
                    entry.entry_id,
                    entry.service_name[:30] + "..." if len(entry.service_name) > 30 else entry.service_name,
                    str(codes_count),
                    has_totp,
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
        """View selected entry details (scrollable; OS message boxes truncate long code lists)."""
        if not require_action_unlock(self.frame):
            return
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, TwoFactorEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            if entry.sensitivity_level == "critical":
                if not messagebox.askyesno(
                    "Sensitive data",
                    "You are about to show recovery codes and any TOTP secret on screen.\n\nContinue?",
                ):
                    return
            codes_display = "\n".join(entry.backup_codes) if entry.backup_codes else "(No backup codes stored)"
            ts = (entry.totp_secret or "").strip()
            totp_display = ts if ts else "(None)"
            body = (
                f"Entry ID: {entry.entry_id}\n"
                f"Service: {entry.service_name}\n"
                f"Note: {entry.site_note}\n"
                f"Created: {entry.created}\n"
                f"Modified: {entry.modified}\n\n"
                f"--- Backup codes (one per line) ---\n{codes_display}\n\n"
                f"--- TOTP secret (if stored) ---\n{totp_display}\n"
            )
            show_scrollable_secret_dialog(self.frame, f"2FA - {entry.service_name}", body)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")

    def _copy_backup_codes(self):
        """Copy all backup codes to the clipboard (newline separated)."""
        if not require_action_unlock(self.frame):
            return
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, TwoFactorEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            if not entry.backup_codes:
                messagebox.showwarning("Warning", "No backup codes in this entry")
                return
            root = self.frame.winfo_toplevel()
            text = "\n".join(entry.backup_codes)
            copy_to_clipboard(text, entry.sensitivity_level, root)
            messagebox.showinfo("Copied", "Backup codes copied to clipboard (will clear automatically).")
        except Exception as e:
            messagebox.showerror("Clipboard Operation Failed", str(e))
    
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

