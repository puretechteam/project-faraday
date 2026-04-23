"""
Emergency/trusted contact section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from ..models.emergency_contact_entry import EmergencyContactEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_required_field, validate_email
from .clipboard_helper import copy_to_clipboard
from .action_guard import require_action_unlock


class EmergencyContactSection:
    """Section for managing emergency contact entries."""
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize emergency contact section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add Emergency Contact", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(form_frame, text="Contact Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.contact_name_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.contact_name_var, width=50).grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Relationship:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.relationship_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.relationship_var, width=50).grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Phone:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.phone_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.phone_var, width=50).grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Email:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.email_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.email_var, width=50).grid(row=3, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Address:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.address_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.address_var, width=50).grid(row=4, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Medical Notes (optional):").grid(row=5, column=0, sticky=tk.NW, pady=5)
        self.medical_notes_text = scrolledtext.ScrolledText(form_frame, width=50, height=4, wrap=tk.WORD)
        self.medical_notes_text.grid(row=5, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Instructions (optional):").grid(row=6, column=0, sticky=tk.NW, pady=5)
        self.instructions_text = scrolledtext.ScrolledText(form_frame, width=50, height=4, wrap=tk.WORD)
        self.instructions_text.grid(row=6, column=1, padx=5, pady=5, sticky=tk.EW)
        
        ttk.Label(form_frame, text="Site Note:").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.note_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.note_var, width=50).grid(row=7, column=1, padx=5, pady=5, sticky=tk.EW)
        
        form_frame.columnconfigure(1, weight=1)
        
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Add Entry", command=self._add_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        
        list_frame = ttk.LabelFrame(self.frame, text="Emergency Contacts", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Contact Name", "Relationship", "Phone", "Modified")
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
        ttk.Button(list_button_frame, text="Copy Phone", command=lambda: self._copy_field("phone")).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Copy Email", command=lambda: self._copy_field("email")).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        self._refresh_list()
    
    def _add_entry(self):
        """Add new emergency contact entry."""
        contact_name = self.contact_name_var.get().strip()
        relationship = self.relationship_var.get().strip()
        phone = self.phone_var.get().strip()
        email = self.email_var.get().strip()
        address = self.address_var.get().strip()
        medical_notes = self.medical_notes_text.get("1.0", tk.END).strip()
        instructions = self.instructions_text.get("1.0", tk.END).strip()
        
        valid, error = validate_required_field(contact_name, "Contact name")
        if not valid:
            messagebox.showerror("Error", error)
            return
        
        valid, error = validate_email(email)
        if not valid and error:
            if not messagebox.askyesno("Warning", f"{error}\n\nContinue anyway?"):
                return
        
        try:
            self.vault_manager.add_entry(EmergencyContactEntry(
                contact_name=contact_name,
                relationship=relationship,
                phone=phone,
                email=email,
                address=address,
                medical_notes=medical_notes if medical_notes else None,
                instructions=instructions if instructions else None,
                site_note=self.note_var.get().strip()
            ))
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "Emergency contact entry added")
        except Exception as e:
            messagebox.showerror("Entry Creation Failed", f"Unable to add emergency contact entry:\n{e}")
    
    def _clear_form(self):
        """Clear entry form."""
        self.contact_name_var.set("")
        self.relationship_var.set("")
        self.phone_var.set("")
        self.email_var.set("")
        self.address_var.set("")
        self.medical_notes_text.delete("1.0", tk.END)
        self.instructions_text.delete("1.0", tk.END)
        self.note_var.set("")
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="emergency_contact"):
                self.tree.insert("", tk.END, values=(
                    entry.entry_id,
                    entry.contact_name[:30] + "..." if len(entry.contact_name) > 30 else entry.contact_name,
                    entry.relationship[:20] + "..." if len(entry.relationship) > 20 else entry.relationship,
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
            if not entry or not isinstance(entry, EmergencyContactEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            medical_display = entry.medical_notes if entry.medical_notes else "(None)"
            instructions_display = entry.instructions if entry.instructions else "(None)"
            messagebox.showinfo("Entry Details", f"Entry ID: {entry.entry_id}\nContact Name: {entry.contact_name}\nRelationship: {entry.relationship}\nPhone: {entry.phone}\nEmail: {entry.email}\nAddress: {entry.address}\nMedical Notes: {medical_display}\nInstructions: {instructions_display}\nSite Note: {entry.site_note}\nCreated: {entry.created}\nModified: {entry.modified}")
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
    
    def _copy_field(self, field_name: str):
        """Copy field value to clipboard."""
        if not require_action_unlock(self.frame):
            return
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, EmergencyContactEntry):
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

