"""
Password generator dialog for GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from ..generator.password import PasswordGenerator
from .icon_helper import set_window_icon


class PasswordGeneratorDialog:
    """Dialog for generating passwords."""
    
    def __init__(self, parent, callback=None):
        """Initialize password generator dialog."""
        self.parent = parent
        self.callback = callback
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Password Generator")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        set_window_icon(self.dialog)
        self.dialog.option_add('*TkEntry*show', '')
        self._create_widgets()
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.dialog.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
        self._generate()
    
    def _create_widgets(self):
        """Create dialog widgets."""
        length_frame = ttk.Frame(self.dialog, padding=10)
        length_frame.pack(fill=tk.X)
        ttk.Label(length_frame, text="Length:").pack(side=tk.LEFT)
        self.length_var = tk.IntVar(value=16)
        ttk.Spinbox(length_frame, from_=8, to=128, textvariable=self.length_var, width=10).pack(side=tk.LEFT, padx=5)
        charset_frame = ttk.LabelFrame(self.dialog, text="Character Sets", padding=10)
        charset_frame.pack(fill=tk.X, padx=10, pady=5)
        self.use_letters = tk.BooleanVar(value=True)
        ttk.Checkbutton(charset_frame, text="Letters (a-z, A-Z)", variable=self.use_letters).pack(anchor=tk.W)
        self.use_numbers = tk.BooleanVar(value=True)
        ttk.Checkbutton(charset_frame, text="Numbers (0-9)", variable=self.use_numbers).pack(anchor=tk.W)
        self.use_symbols = tk.BooleanVar(value=True)
        ttk.Checkbutton(charset_frame, text="Symbols (!@#$...)", variable=self.use_symbols).pack(anchor=tk.W)
        exclude_frame = ttk.Frame(self.dialog, padding=10)
        exclude_frame.pack(fill=tk.X)
        ttk.Label(exclude_frame, text="Exclude:").pack(side=tk.LEFT)
        self.exclude_var = tk.StringVar()
        exclude_entry = ttk.Entry(exclude_frame, textvariable=self.exclude_var, width=20)
        exclude_entry.pack(side=tk.LEFT, padx=5)
        exclude_entry.configure(show="")
        result_frame = ttk.LabelFrame(self.dialog, text="Generated Password", padding=10)
        result_frame.pack(fill=tk.X, padx=10, pady=5)
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(result_frame, textvariable=self.password_var, width=40, font=("Courier", 10))
        password_entry.pack(fill=tk.X)
        password_entry.configure(show="")
        button_frame = ttk.Frame(self.dialog, padding=10)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Generate", command=self._generate).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Copy", command=self._copy).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Use", command=self._use).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close", command=self._close).pack(side=tk.RIGHT, padx=5)
    
    def _generate(self):
        """Generate password."""
        try:
            use_letters = self.use_letters.get()
            generator = PasswordGenerator(length=self.length_var.get(), use_lowercase=use_letters, use_uppercase=use_letters, use_digits=self.use_numbers.get(), use_symbols=self.use_symbols.get(), exclude_chars=self.exclude_var.get())
            self.password_var.set(generator.generate())
        except ValueError as e:
            messagebox.showerror("Error", str(e))
    
    def _copy(self):
        """Copy password to clipboard."""
        password = self.password_var.get()
        if password:
            self.dialog.clipboard_clear()
            self.dialog.clipboard_append(password)
            self.dialog.after(30000, self._clear_clipboard)
            messagebox.showinfo("Copied", "Password copied to clipboard (will clear in 30 seconds)")
    
    def _clear_clipboard(self):
        """Clear clipboard."""
        self.dialog.clipboard_clear()
    
    def _use(self):
        """Use password (call callback and close)."""
        password = self.password_var.get()
        if password:
            self.result = password
            if self.callback:
                self.callback(password)
            self._close()
    
    def _close(self):
        """Close dialog."""
        self._clear_clipboard()
        self.dialog.destroy()
