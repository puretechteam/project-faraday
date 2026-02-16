"""
Document storage section for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from ..models.document_entry import DocumentEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_required_field
from .clipboard_helper import copy_to_clipboard


class DocumentSection:
    """Section for managing document entries."""
    
    MAX_FILE_SIZE_MB = 100  # Maximum file size in MB
    
    def __init__(self, parent, vault_manager: VaultManager):
        """Initialize document section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
    
    def _show_sensitivity_warning(self, file_size_mb: float):
        """Show warning for critical sensitivity level and file size."""
        warning_msg = (
            "This entry contains encrypted document files (critical sensitivity).\n\n"
            f"File size: {file_size_mb:.2f} MB\n\n"
            "Documents are encrypted individually and stored separately.\n"
            "Ensure you keep this data secure.\n\n"
            "Continue with upload?"
        )
        return messagebox.askyesno("Security Warning", warning_msg)
    
    def _create_widgets(self):
        """Create section widgets."""
        form_frame = ttk.LabelFrame(self.frame, text="Add Document", padding=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(form_frame, text="Selected File:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.file_path_var = tk.StringVar(value="(No file selected)")
        file_label = ttk.Label(form_frame, textvariable=self.file_path_var, foreground="gray")
        file_label.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(form_frame, text="Note:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.note_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.note_var, width=50).grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        
        form_frame.columnconfigure(1, weight=1)
        
        button_frame = ttk.Frame(self.frame, padding=10)
        button_frame.pack(fill=tk.X, padx=10)
        ttk.Button(button_frame, text="Select File", command=self._select_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Upload Document", command=self._upload_document).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear", command=self._clear_form).pack(side=tk.LEFT, padx=5)
        
        list_frame = ttk.LabelFrame(self.frame, text="Documents", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        columns = ("ID", "Filename", "Size", "Type", "Modified")
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
        ttk.Button(list_button_frame, text="View Details", command=self._view_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Download", command=self._download_document).pack(side=tk.LEFT, padx=5)
        ttk.Button(list_button_frame, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=5)
        self._selected_file_path = None
        self._refresh_list()
    
    def _select_file(self):
        """Select file for upload."""
        file_path = filedialog.askopenfilename(
            title="Select Document to Upload",
            filetypes=[("All files", "*.*")]
        )
        if file_path:
            self._selected_file_path = file_path
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            self.file_path_var.set(f"{filename} ({file_size:.2f} MB)")
    
    def _upload_document(self):
        """Upload document to vault."""
        if not self._selected_file_path or not os.path.exists(self._selected_file_path):
            messagebox.showerror("Error", "Please select a file first")
            return
        
        file_size = os.path.getsize(self._selected_file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        if file_size_mb > self.MAX_FILE_SIZE_MB:
            messagebox.showerror("Error", f"File size exceeds maximum of {self.MAX_FILE_SIZE_MB} MB")
            return
        
        # Show sensitivity warning
        if not self._show_sensitivity_warning(file_size_mb):
            return
        
        attachment_storage = self.vault_manager.get_attachment_storage()
        if not attachment_storage:
            messagebox.showerror("Error", "Attachment storage not available (vault may be locked)")
            return
        
        try:
            # Read file
            with open(self._selected_file_path, 'rb') as f:
                file_data = f.read()
            
            # Store encrypted file
            file_uuid, file_hash = attachment_storage.store_file(file_data)
            
            # Get file info
            filename = os.path.basename(self._selected_file_path)
            import mimetypes
            mime_type, _ = mimetypes.guess_type(self._selected_file_path)
            mime_type = mime_type or "application/octet-stream"
            
            # Create document entry
            self.vault_manager.add_entry(DocumentEntry(
                filename=filename,
                mime_type=mime_type,
                file_reference=file_uuid,
                file_size=file_size,
                file_hash=file_hash,
                site_note=self.note_var.get().strip()
            ))
            
            self._clear_form()
            self._refresh_list()
            messagebox.showinfo("Success", "Document uploaded and encrypted successfully")
        except Exception as e:
            messagebox.showerror("Upload Failed", f"Unable to upload document:\n{e}")
    
    def _clear_form(self):
        """Clear entry form."""
        self._selected_file_path = None
        self.file_path_var.set("(No file selected)")
        self.note_var.set("")
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
    
    def _refresh_list(self):
        """Refresh entry list."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            for entry in self.vault_manager.list_entries(entry_type="document"):
                self.tree.insert("", tk.END, values=(
                    entry.entry_id,
                    entry.filename[:40] + "..." if len(entry.filename) > 40 else entry.filename,
                    self._format_file_size(entry.file_size),
                    entry.mime_type[:20] + "..." if len(entry.mime_type) > 20 else entry.mime_type,
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
        
        # Show warning before viewing critical entry
        entry = self.vault_manager.get_entry(entry_id)
        if entry and hasattr(entry, 'sensitivity_level') and entry.sensitivity_level == "critical":
            if not self._show_sensitivity_warning(entry.file_size / (1024 * 1024)):
                return
        
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, DocumentEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            messagebox.showinfo("Entry Details", f"Entry ID: {entry.entry_id}\nFilename: {entry.filename}\nMIME Type: {entry.mime_type}\nFile Size: {self._format_file_size(entry.file_size)}\nFile Hash: {entry.file_hash}\nUploaded: {entry.upload_timestamp}\nNote: {entry.site_note}\nCreated: {entry.created}\nModified: {entry.modified}")
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
    
    def _download_document(self):
        """Download and decrypt document."""
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        
        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, DocumentEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            
            attachment_storage = self.vault_manager.get_attachment_storage()
            if not attachment_storage:
                messagebox.showerror("Error", "Attachment storage not available (vault may be locked)")
                return
            
            # Retrieve and decrypt file
            file_data = attachment_storage.retrieve_file(entry.file_reference)
            
            # Verify hash
            computed_hash = attachment_storage.compute_file_hash(file_data)
            if computed_hash != entry.file_hash:
                messagebox.showerror("Error", "File integrity check failed - file may be corrupted")
                return
            
            # Save file
            save_path = filedialog.asksaveasfilename(
                title="Save Document",
                defaultextension=os.path.splitext(entry.filename)[1],
                initialfile=entry.filename
            )
            if save_path:
                with open(save_path, 'wb') as f:
                    f.write(file_data)
                messagebox.showinfo("Success", f"Document saved to:\n{save_path}")
        except FileNotFoundError:
            messagebox.showerror("Error", "Document file not found")
        except Exception as e:
            messagebox.showerror("Download Failed", f"Unable to download document:\n{e}")
    
    def _delete_selected(self):
        """Delete selected entry."""
        entry_id = self._get_selected_id()
        if not entry_id:
            messagebox.showwarning("Warning", "No entry selected")
            return
        if not messagebox.askyesno("Confirm", "Delete this entry and its encrypted file?"):
            return
        try:
            if self.vault_manager.delete_entry(entry_id):
                self._refresh_list()
                messagebox.showinfo("Success", "Entry and file deleted")
            else:
                messagebox.showerror("Error", "Entry not found")
        except Exception as e:
            messagebox.showerror("Deletion Failed", f"Unable to delete entry:\n{e}")

