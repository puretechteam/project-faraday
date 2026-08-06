"""
Document storage section (Faraday 3.0.0 redesign).

Rebuilt on the shared widget kit (``faraday.gui.widgets``) while preserving the
exact :class:`VaultManager` read/write and attachment-storage calls from the
previous implementation.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
import mimetypes

from ..models.document_entry import DocumentEntry
from ..vault.manager import VaultManager
from ..vault.validation import validate_required_field
from .action_guard import require_action_unlock, show_scrollable_secret_dialog
from .design_system import SPACING, build_tokens, get_active_merged
from .native_dialog import ask_open_filename, ask_save_as_filename
from .widgets import (
    CardList,
    Dialog,
    EmptyState,
    EntryCard,
    GhostButton,
    LabeledEntry,
    PrimaryButton,
    SectionHeader,
    show_status,
)


class DocumentSection:
    """Section for managing document entries (view contract)."""

    MAX_FILE_SIZE_MB = 100  # Maximum file size in MB

    DOCUMENT_CATEGORIES = (
        "General",
        "ID / Driver License",
        "Legal",
        "Financial",
        "Medical",
        "Tax",
        "Other",
    )

    def __init__(self, parent, vault_manager: VaultManager, vault_path=None):
        """Initialize document section."""
        self.vault_manager = vault_manager
        self.frame = ttk.Frame(parent)
        self._create_widgets()
        self.refresh()

    def _muted_fg(self) -> str:
        """Themed muted foreground (never a hardcoded low-contrast gray)."""
        try:
            return build_tokens(get_active_merged())["muted"]
        except Exception:
            return "gray"

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
        self.header = SectionHeader(
            self.frame,
            title="Documents",
            count=0,
            on_add=self._upload_dialog,
        )
        self.header.pack(side=tk.TOP, fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))

        self.list_container = ttk.Frame(self.frame)
        self.list_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=SPACING["md"], pady=(0, SPACING["md"]))

        self.card_list = CardList(self.list_container)
        self.card_list.pack(fill=tk.BOTH, expand=True)

        self.empty_state = EmptyState(
            self.list_container,
            message="No documents stored yet. Add one to get started.",
            icon_name="file",
            action_label="Add Document",
            on_action=self._upload_dialog,
        )

    def refresh(self):
        """Refresh the card list from the vault manager."""
        self.card_list.clear()
        entries = []
        try:
            entries = list(self.vault_manager.list_entries(entry_type="document"))
        except Exception as e:
            messagebox.showerror("Refresh Failed", f"Unable to refresh entry list:\n{e}")
            return

        for entry in entries:
            card = EntryCard(
                self.card_list,
                on_copy=lambda eid=entry.entry_id: self._download_document(eid),
                on_edit=lambda eid=entry.entry_id: self._edit_dialog(eid),
                on_delete=lambda eid=entry.entry_id: self._delete_selected(eid),
            )
            cat = getattr(entry, "category", "General")
            meta = (
                f"{cat} · {self._format_file_size(entry.file_size)} · {entry.mime_type}\n"
                f"Modified {entry.modified:%Y-%m-%d %H:%M}"
            )
            # Category is already shown in ``meta``; the subtitle carries the note.
            subtitle = (getattr(entry, "site_note", "") or "").strip() or "(no note)"
            card.set_data(title=entry.filename, subtitle=subtitle, meta=meta)
            self.card_list.add(card)

        self.header.set_count(len(entries))
        if entries:
            self.empty_state.pack_forget()
            self.card_list.pack(fill=tk.BOTH, expand=True)
        else:
            self.card_list.pack_forget()
            self.empty_state.pack(fill=tk.BOTH, expand=True)

    def filter(self, query: str) -> None:
        """Filter visible entries by *query* (empty -> show all)."""
        if not query:
            self.card_list.filter("")
        else:
            self.card_list.filter(query)

    # ------------------------------------------------------------------ forms
    def _upload_dialog(self):
        """Open the upload document dialog."""
        dlg = Dialog(self.frame, title="Add Document", width=460, height=300)

        file_label_var = tk.StringVar(value="(No file selected)")
        file_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        file_row.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))

        selected_path = {"path": None}

        def _select():
            # Owned + temporarily topmost, so the native picker cannot open
            # behind the borderless dialog/app window (looks like a freeze).
            path = ask_open_filename(
                dlg,
                title="Select Document to Upload",
                filetypes=[("All files", "*.*")],
            )
            if path:
                selected_path["path"] = path
                size_mb = os.path.getsize(path) / (1024 * 1024)
                base = os.path.basename(path)
                name = (base[:28] + "…") if len(base) > 29 else base
                file_label_var.set(f"{name} ({size_mb:.2f} MB)")

        # Packed FIRST so a long filename can never push the button out of view.
        GhostButton(file_row, text="Select File", command=_select).pack(side=tk.RIGHT)
        ttk.Label(file_row, text="Selected File:").pack(side=tk.LEFT)
        ttk.Label(
            file_row, textvariable=file_label_var, foreground=self._muted_fg(),
            width=34, anchor=tk.W,
        ).pack(side=tk.LEFT, padx=(SPACING["sm"], 0))

        ttk.Label(dlg.content, text="Category:").pack(
            anchor=tk.W, padx=SPACING["md"], pady=(0, SPACING["xs"])
        )
        cat_var = tk.StringVar(value=self.DOCUMENT_CATEGORIES[0])
        cat_combo = ttk.Combobox(
            dlg.content, textvariable=cat_var, state="readonly",
            values=self.DOCUMENT_CATEGORIES, width=40,
        )
        cat_combo.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))

        note_field = LabeledEntry(dlg.content, label="Note:", value="")
        note_field.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))

        btn_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        btn_row.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["md"]))

        PrimaryButton(
            btn_row,
            text="Upload Document",
            command=lambda: self._upload_document(dlg, selected_path["path"], cat_var, note_field),
        ).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)

    def _upload_document(self, dlg, selected_file_path, cat_var, note_field):
        """Upload document to vault (identical storage logic to prior version)."""
        if not selected_file_path or not os.path.exists(selected_file_path):
            messagebox.showerror("Error", "Please select a file first")
            return

        file_size = os.path.getsize(selected_file_path)
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
            with open(selected_file_path, 'rb') as f:
                file_data = f.read()

            # Store encrypted file
            file_uuid, file_hash = attachment_storage.store_file(file_data)

            # Get file info
            filename = os.path.basename(selected_file_path)
            mime_type, _ = mimetypes.guess_type(selected_file_path)
            mime_type = mime_type or "application/octet-stream"

            # Create document entry
            cat = cat_var.get().strip() or "General"
            if cat not in self.DOCUMENT_CATEGORIES:
                cat = "General"
            self.vault_manager.add_entry(DocumentEntry(
                filename=filename,
                mime_type=mime_type,
                file_reference=file_uuid,
                file_size=file_size,
                file_hash=file_hash,
                category=cat,
                site_note=note_field.get().strip()
            ))

            dlg.destroy()
            self.refresh()
            messagebox.showinfo("Success", "Document uploaded and encrypted successfully")
        except Exception as e:
            messagebox.showerror("Upload Failed", f"Unable to upload document:\n{e}")

    def _edit_dialog(self, entry_id):
        """Edit a document's metadata (same layout as upload, minus the file picker)."""
        if not require_action_unlock(self.frame):
            return
        try:
            entry = self.vault_manager.get_entry(entry_id)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")
            return
        if not entry or not isinstance(entry, DocumentEntry):
            messagebox.showerror("Error", "Entry not found or invalid type")
            return

        dlg = Dialog(self.frame, title="Edit Document", width=460, height=300)

        name_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        name_row.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["sm"]))
        ttk.Label(name_row, text="File:").pack(side=tk.LEFT)
        base = entry.filename or ""
        name = (base[:28] + "…") if len(base) > 29 else base
        ttk.Label(
            name_row, text=f"{name} ({self._format_file_size(entry.file_size)})",
            foreground=self._muted_fg(), width=34, anchor=tk.W,
        ).pack(side=tk.LEFT, padx=(SPACING["sm"], 0))

        ttk.Label(dlg.content, text="Category:").pack(
            anchor=tk.W, padx=SPACING["md"], pady=(0, SPACING["xs"])
        )
        current_cat = getattr(entry, "category", "General") or "General"
        if current_cat not in self.DOCUMENT_CATEGORIES:
            current_cat = "General"
        cat_var = tk.StringVar(value=current_cat)
        ttk.Combobox(
            dlg.content, textvariable=cat_var, state="readonly",
            values=self.DOCUMENT_CATEGORIES, width=40,
        ).pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))

        note_field = LabeledEntry(dlg.content, label="Note:", value=entry.site_note or "")
        note_field.pack(fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["sm"]))

        btn_row = tk.Frame(dlg.content, bd=0, highlightthickness=0)
        btn_row.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["md"]))

        PrimaryButton(
            btn_row,
            text="Save",
            command=lambda: self._save_edit(dlg, entry, cat_var, note_field),
        ).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        GhostButton(btn_row, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        GhostButton(
            btn_row, text="Details",
            command=lambda eid=entry.entry_id: self._view_selected(eid),
        ).pack(side=tk.LEFT)

    def _save_edit(self, dlg, entry, cat_var, note_field):
        """Persist edited metadata, keeping file_reference / file_hash intact."""
        cat = cat_var.get().strip() or "General"
        if cat not in self.DOCUMENT_CATEGORIES:
            cat = "General"
        try:
            # NOTE: ``delete_entry`` also deletes the encrypted attachment for
            # document entries, so the replacement is written as an in-place
            # upsert (same entry_id) to avoid destroying the stored file.
            self.vault_manager.add_entry(DocumentEntry(
                filename=entry.filename,
                mime_type=entry.mime_type,
                file_reference=entry.file_reference,
                file_size=entry.file_size,
                file_hash=entry.file_hash,
                category=cat,
                upload_timestamp=entry.upload_timestamp,
                entry_id=entry.entry_id,
                site_note=note_field.get().strip(),
                created=entry.created,
            ))
            dlg.destroy()
            self.refresh()
            show_status(self.frame, "Document details updated", "success")
        except Exception as e:
            messagebox.showerror("Entry Update Failed", f"Unable to save document details:\n{e}")

    # ------------------------------------------------------------- operations
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} MB"

    def _view_selected(self, entry_id):
        """View selected entry details."""
        entry = self.vault_manager.get_entry(entry_id)
        if entry and hasattr(entry, 'sensitivity_level') and entry.sensitivity_level == "critical":
            if not self._show_sensitivity_warning(entry.file_size / (1024 * 1024)):
                return

        try:
            entry = self.vault_manager.get_entry(entry_id)
            if not entry or not isinstance(entry, DocumentEntry):
                messagebox.showerror("Error", "Entry not found or invalid type")
                return
            body = (
                f"Entry ID: {entry.entry_id}\nCategory: {getattr(entry, 'category', 'General')}\nFilename: {entry.filename}\n"
                f"MIME Type: {entry.mime_type}\nFile Size: {self._format_file_size(entry.file_size)}\n"
                f"File Hash: {entry.file_hash}\nUploaded: {entry.upload_timestamp}\nNote: {entry.site_note}\n"
                f"Created: {entry.created}\nModified: {entry.modified}"
            )
            show_scrollable_secret_dialog(self.frame, f"Document - {entry.filename}", body)
        except Exception as e:
            messagebox.showerror("Entry Access Failed", f"Unable to retrieve entry details:\n{e}")

    def _download_document(self, entry_id):
        """Download and decrypt document (gated by action PIN)."""
        if not require_action_unlock(self.frame):
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
            save_path = ask_save_as_filename(
                self.frame,
                title="Save Document",
                defaultextension=os.path.splitext(entry.filename)[1],
                initialfile=entry.filename
            )
            if save_path:
                with open(save_path, 'wb') as f:
                    f.write(file_data)
                show_status(self.frame, "Document decrypted and saved", "success")
        except FileNotFoundError:
            messagebox.showerror("Error", "Document file not found")
        except Exception as e:
            messagebox.showerror("Download Failed", f"Unable to download document:\n{e}")

    def _delete_selected(self, entry_id):
        """Delete selected entry (gated by action PIN)."""
        if not require_action_unlock(self.frame):
            return
        if not messagebox.askyesno("Confirm", "Delete this entry and its encrypted file?"):
            return
        try:
            if self.vault_manager.delete_entry(entry_id):
                self.refresh()
                messagebox.showinfo("Success", "Entry and file deleted")
            else:
                messagebox.showerror("Error", "Entry not found")
        except Exception as e:
            messagebox.showerror("Deletion Failed", f"Unable to delete entry:\n{e}")
