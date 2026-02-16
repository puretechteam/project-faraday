"""
Password input dialog for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from .icon_helper import set_window_icon
from .password_generator import PasswordGeneratorDialog


class PasswordDialog:
    """Dialog for entering password."""
    
    def __init__(self, parent, title="Enter Password", prompt="Password:", confirm=False):
        """Initialize password dialog."""
        self.parent = parent
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        set_window_icon(self.dialog)
        self.dialog.option_add('*TkEntry*show', '*')
        self._create_widgets(prompt, confirm)
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.dialog.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
        self.password_entry.focus_set()
        self.password_entry.bind('<Return>', lambda e: self._ok())
        if confirm:
            self.confirm_entry.bind('<Return>', lambda e: self._ok())
    
    def _create_widgets(self, prompt, confirm):
        """Create dialog widgets."""
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text=prompt).pack(anchor=tk.W, pady=(0, 5))
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(main_frame, textvariable=self.password_var, width=30, show="*")
        self.password_entry.pack(fill=tk.X, pady=(0, 10))
        self.confirm_var = None
        self.confirm_entry = None
        if confirm:
            ttk.Label(main_frame, text="Confirm Password:").pack(anchor=tk.W, pady=(0, 5))
            self.confirm_var = tk.StringVar()
            self.confirm_entry = ttk.Entry(main_frame, textvariable=self.confirm_var, width=30, show="*")
            self.confirm_entry.pack(fill=tk.X, pady=(0, 10))
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Generate Password", command=self._generate_password).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="Cancel", command=self._cancel).pack(side=tk.RIGHT)
    
    def _ok(self):
        """OK button clicked."""
        password = self.password_var.get()
        if self.confirm_var:
            if password != self.confirm_var.get():
                messagebox.showerror("Error", "Passwords do not match")
                return
        if not password:
            messagebox.showerror("Error", "Password cannot be empty")
            return
        self.result = password
        self.dialog.destroy()
    
    def _cancel(self):
        """Cancel button clicked."""
        self.result = None
        self.dialog.destroy()
    
    def _generate_password(self):
        """Open password generator and fill password field(s)."""
        def use_password(password):
            """Callback to use generated password."""
            self.password_var.set(password)
            if self.confirm_var:
                self.confirm_var.set(password)
            self.password_entry.focus_set()
        
        PasswordGeneratorDialog(self.dialog, callback=use_password)
    
    def get_password(self):
        """Get password result (blocks until dialog closes)."""
        self.dialog.wait_window()
        return self.result
