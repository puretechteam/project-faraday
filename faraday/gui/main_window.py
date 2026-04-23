"""
Main GUI window for Project Faraday.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import shutil
from datetime import datetime

from cryptography.exceptions import InvalidTag

from ..vault.manager import VaultManager
from .crypto_section import CryptoSection
from .credential_section import CredentialSection
from .secure_note_section import SecureNoteSection
from .card_section import CardSection
from .identity_section import IdentitySection
from .emergency_contact_section import EmergencyContactSection
from .two_factor_section import TwoFactorSection
from .api_key_section import ApiKeySection
from .wifi_section import WifiSection
from .document_section import DocumentSection
from .threat_panel import ThreatModelPanel
from .password_dialog import PasswordDialog
from .tray_icon import TrayIcon, is_tray_available
from .console_toggle import toggle_console
from .icon_helper import set_window_icon
from .vault_history import load_recent_vaults, save_recent_vault
from .action_guard import menu_change_action_pin, menu_disable_action_pin, menu_enable_or_change_action_pin
from .ui_theme import (
    PRESET_LABELS,
    ThemeSettingsDialog,
    apply_saved_theme,
    apply_theme_to_popup_menus,
    merge_theme,
    normalize_preset_id,
    quick_apply_preset,
)


def get_vaults_directory():
    """Get the vaults directory path, creating it if it doesn't exist."""
    vaults_dir = os.path.join(os.getcwd(), "vaults")
    os.makedirs(vaults_dir, exist_ok=True)
    return vaults_dir


class MainWindow:
    """Main application window."""
    
    def __init__(self):
        """Initialize main window."""
        self.root = tk.Tk()
        self.root.title("Faraday 2.0.0")
        self.root.geometry("800x600")
        set_window_icon(self.root)
        self.root.option_add('*TkEntry*show', '')
        self._ui_style = ttk.Style(self.root)
        self._themed_menus: list = []
        self._theme_merged = apply_saved_theme(self.root, self._ui_style)
        self.vault_manager: VaultManager = None
        self.vault_path = None
        self.tray_icon = None
        self._create_menu()
        apply_theme_to_popup_menus(self._themed_menus, self._theme_merged, root=self.root)
        self._create_widgets()
        if is_tray_available():
            self.tray_icon = TrayIcon(on_show=self._show_window, on_lock=self._lock_vault, on_exit=self._on_closing, on_toggle_console=toggle_console)
            self.tray_icon.run()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _create_menu(self):
        """In-window menu strip (ttk). Native winfo menubar ignores theme colors on Windows."""
        self._themed_menus = []
        bar = ttk.Frame(self.root)
        bar.pack(side=tk.TOP, fill=tk.X)
        self._menubar_frame = bar

        def reg(m: tk.Menu) -> tk.Menu:
            self._themed_menus.append(m)
            return m

        file_mb = ttk.Menubutton(bar, text="File")
        self.file_menu = reg(tk.Menu(file_mb, tearoff=0))
        file_mb.configure(menu=self.file_menu)
        file_mb.pack(side=tk.LEFT, padx=(8, 0), pady=2)
        self.file_menu.add_command(label="New Vault", command=self._new_vault)
        self.file_menu.add_command(label="Open Vault", command=self._open_vault)
        self.recent_menu = reg(tk.Menu(self.file_menu, tearoff=0))
        self.file_menu.add_cascade(label="Recent Vaults", menu=self.recent_menu)
        self._update_recent_menu()
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Backup Vault", command=self._backup_vault, state=tk.DISABLED)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Lock Vault", command=self._lock_vault, state=tk.DISABLED)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self._on_closing)

        sec_mb = ttk.Menubutton(bar, text="Security")
        security_menu = reg(tk.Menu(sec_mb, tearoff=0))
        sec_mb.configure(menu=security_menu)
        sec_mb.pack(side=tk.LEFT, padx=(4, 0), pady=2)
        security_menu.add_command(label="Set up action PIN", command=lambda: menu_enable_or_change_action_pin(self.root))
        security_menu.add_command(label="Change action PIN", command=lambda: menu_change_action_pin(self.root))
        security_menu.add_command(label="Disable action PIN", command=lambda: menu_disable_action_pin(self.root))

        theme_mb = ttk.Menubutton(bar, text="Theme")
        theme_menu = reg(tk.Menu(theme_mb, tearoff=0))
        theme_presets = reg(tk.Menu(theme_menu, tearoff=0))
        theme_mb.configure(menu=theme_menu)
        theme_mb.pack(side=tk.LEFT, padx=(4, 0), pady=2)
        theme_menu.add_command(label="Theme settings", command=self._theme_settings)
        theme_menu.add_cascade(label="Quick preset", menu=theme_presets)
        for preset_id, preset_label in PRESET_LABELS:
            theme_presets.add_command(
                label=preset_label,
                command=lambda p=preset_id: self._quick_theme_preset(p),
            )

        help_mb = ttk.Menubutton(bar, text="Help")
        help_menu = reg(tk.Menu(help_mb, tearoff=0))
        help_mb.configure(menu=help_menu)
        help_mb.pack(side=tk.LEFT, padx=(4, 0), pady=2)
        help_menu.add_command(label="About", command=self._show_about)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(side=tk.TOP, fill=tk.X)
    
    def _create_widgets(self):
        """Create main window widgets."""
        self.status_var = tk.StringVar(value="Vault not loaded")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.crypto_tab = None
        self.credential_tab = None
        self.welcome_frame = ttk.Frame(main_frame)
        self.welcome_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.welcome_frame, text="Please open or create a vault to begin").pack(expand=True)
    
    def _new_vault(self):
        """Create a new vault."""
        vault_path = filedialog.asksaveasfilename(title="Create New Vault", defaultextension=".vault", initialdir=get_vaults_directory(), filetypes=[("Vault files", "*.vault"), ("All files", "*.*")])
        if not vault_path:
            return
        if os.path.exists(vault_path) and not messagebox.askyesno("Confirm", "File exists. Overwrite?"):
            return
        password = PasswordDialog(self.root, title="Create New Vault", prompt="Enter master password for new vault:", confirm=True).get_password()
        if not password:
            return
        try:
            manager = VaultManager(vault_path, password.encode('utf-8'))
            manager.create_vault()
            self._set_vault(manager, vault_path)
            messagebox.showinfo("Success", "Vault created successfully")
        except Exception as e:
            messagebox.showerror("Vault Creation Failed", f"Unable to create vault:\n{e}")
    
    def _open_vault(self, vault_path: str = None):
        """Open existing vault."""
        if not vault_path:
            vault_path = filedialog.askopenfilename(title="Open Vault", initialdir=get_vaults_directory(), filetypes=[("Vault files", "*.vault"), ("All files", "*.*")])
            if not vault_path:
                return
        password = PasswordDialog(
            self.root,
            title="Open Vault",
            prompt="Enter master password:",
            confirm=False,
            show_generate_password=False,
        ).get_password()
        if not password:
            return
        try:
            manager = VaultManager(vault_path, password.encode('utf-8'))
            manager.unlock_vault()
            if self.vault_manager:
                self.vault_manager.lock_vault()
            self._set_vault(manager, vault_path)
        except Exception as e:
            hint = (
                "If you are sure the password is correct, the encrypted file may be damaged "
                "(for example from an interrupted save). Try restoring a copy from File History, "
                "a previous backup, or shadow copies if available."
            )
            if isinstance(e, InvalidTag):
                detail = (
                    "Decryption failed: wrong master password, or the vault file was altered or corrupted.\n\n"
                    + hint
                )
            else:
                detail = f"{e}\n\nPlease verify the password and vault file integrity."
            messagebox.showerror("Vault Access Failed", detail)
    
    def _set_vault(self, manager: VaultManager, vault_path: str):
        """Set vault and update UI."""
        self.vault_manager = manager
        self.vault_path = vault_path
        save_recent_vault(vault_path)
        self._update_recent_menu()
        self._update_menu_state()
        self._setup_vault_tabs()
        self.status_var.set(f"Vault: {os.path.basename(vault_path)}")
    
    def _setup_vault_tabs(self):
        """Setup tabs after vault is unlocked."""
        if hasattr(self, 'welcome_frame') and self.welcome_frame.winfo_exists():
            self.welcome_frame.destroy()
        for tab_id in self.notebook.tabs():
            self.notebook.forget(tab_id)
        
        # Credentials
        credential_frame = ttk.Frame(self.notebook)
        self.credential_section = CredentialSection(credential_frame, self.vault_manager)
        self.credential_section.frame.pack(fill=tk.BOTH, expand=True)
        self.notebook.add(credential_frame, text="Credentials")
        
        # Crypto Addresses
        crypto_frame = ttk.Frame(self.notebook)
        self.crypto_section = CryptoSection(crypto_frame, self.vault_manager)
        self.crypto_section.frame.pack(fill=tk.BOTH, expand=True)
        self.notebook.add(crypto_frame, text="Crypto Addresses")
        
        # Secure Notes
        secure_note_frame = ttk.Frame(self.notebook)
        self.secure_note_section = SecureNoteSection(secure_note_frame, self.vault_manager)
        self.secure_note_section.frame.pack(fill=tk.BOTH, expand=True)
        self.notebook.add(secure_note_frame, text="Secure Notes")
        
        # Financial (Cards)
        card_frame = ttk.Frame(self.notebook)
        self.card_section = CardSection(card_frame, self.vault_manager)
        self.card_section.frame.pack(fill=tk.BOTH, expand=True)
        self.notebook.add(card_frame, text="Financial")
        
        # Personal (Identity and Emergency Contacts)
        personal_frame = ttk.Frame(self.notebook)
        personal_notebook = ttk.Notebook(personal_frame)
        personal_notebook.pack(fill=tk.BOTH, expand=True)
        
        identity_subframe = ttk.Frame(personal_notebook)
        self.identity_section = IdentitySection(identity_subframe, self.vault_manager)
        self.identity_section.frame.pack(fill=tk.BOTH, expand=True)
        personal_notebook.add(identity_subframe, text="Identity Profiles")
        
        emergency_contact_subframe = ttk.Frame(personal_notebook)
        self.emergency_contact_section = EmergencyContactSection(emergency_contact_subframe, self.vault_manager)
        self.emergency_contact_section.frame.pack(fill=tk.BOTH, expand=True)
        personal_notebook.add(emergency_contact_subframe, text="Emergency Contacts")
        
        self.notebook.add(personal_frame, text="Personal")
        
        # Security (2FA and API Keys)
        security_frame = ttk.Frame(self.notebook)
        security_notebook = ttk.Notebook(security_frame)
        security_notebook.pack(fill=tk.BOTH, expand=True)
        
        two_factor_subframe = ttk.Frame(security_notebook)
        self.two_factor_section = TwoFactorSection(two_factor_subframe, self.vault_manager)
        self.two_factor_section.frame.pack(fill=tk.BOTH, expand=True)
        security_notebook.add(two_factor_subframe, text="2FA/Recovery Codes")
        
        api_key_subframe = ttk.Frame(security_notebook)
        self.api_key_section = ApiKeySection(api_key_subframe, self.vault_manager)
        self.api_key_section.frame.pack(fill=tk.BOTH, expand=True)
        security_notebook.add(api_key_subframe, text="API Keys")
        
        self.notebook.add(security_frame, text="Security")
        
        # Network (Wi-Fi)
        wifi_frame = ttk.Frame(self.notebook)
        self.wifi_section = WifiSection(wifi_frame, self.vault_manager)
        self.wifi_section.frame.pack(fill=tk.BOTH, expand=True)
        self.notebook.add(wifi_frame, text="Network")
        
        # Documents
        document_frame = ttk.Frame(self.notebook)
        self.document_section = DocumentSection(document_frame, self.vault_manager)
        self.document_section.frame.pack(fill=tk.BOTH, expand=True)
        self.notebook.add(document_frame, text="Documents")

        threat_frame = ttk.Frame(self.notebook)
        self.threat_panel = ThreatModelPanel(threat_frame, self.vault_manager, self.vault_path)
        self.threat_panel.frame.pack(fill=tk.BOTH, expand=True)
        self.notebook.add(threat_frame, text="Threat model")
    
    def _backup_vault(self):
        """Copy the encrypted vault file and attachment store to a user-chosen location."""
        if not self.vault_manager or self.vault_manager.is_locked:
            return
        try:
            self.vault_manager.save_vault()
        except Exception as e:
            messagebox.showerror("Backup Failed", f"Could not save the vault before backup:\n{e}")
            return
        base_name = os.path.basename(self.vault_path)
        root_name, ext = os.path.splitext(base_name)
        if not ext:
            ext = ".vault"
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        initial = f"{root_name}_backup_{stamp}{ext}"
        dest = filedialog.asksaveasfilename(
            title="Backup Vault (encrypted copy)",
            initialfile=initial,
            defaultextension=ext,
            filetypes=[("Vault files", "*.vault"), ("All files", "*.*")],
        )
        if not dest:
            return
        attachments_src = f"{self.vault_path}.attachments"
        attachments_dest = f"{dest}.attachments"
        try:
            shutil.copy2(self.vault_path, dest)
            if os.path.isdir(attachments_src):
                if os.path.exists(attachments_dest):
                    messagebox.showerror(
                        "Backup Failed",
                        "A file or folder with the attachment backup name already exists.\n"
                        "Choose a different backup filename.",
                    )
                    return
                shutil.copytree(attachments_src, attachments_dest)
        except OSError as e:
            messagebox.showerror("Backup Failed", str(e))
            return
        msg = f"Encrypted vault copied to:\n{dest}"
        if os.path.isdir(attachments_src):
            msg += f"\n\nAttachments copied to:\n{attachments_dest}"
        messagebox.showinfo("Backup Complete", msg)

    def _lock_vault(self):
        """Lock vault."""
        if not self.vault_manager:
            return
        self.vault_manager.lock_vault()
        self.vault_manager = None
        self.vault_path = None
        for tab_id in self.notebook.tabs():
            self.notebook.forget(tab_id)
        main_frame = self.notebook.master
        self.welcome_frame = ttk.Frame(main_frame)
        self.welcome_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.welcome_frame, text="Please open or create a vault to begin").pack(expand=True)
        self.status_var.set("Vault locked")
        self._update_menu_state()
        messagebox.showinfo("Locked", "Vault has been locked")
    
    def _update_recent_menu(self):
        """Update the recent vaults menu."""
        self.recent_menu.delete(0, tk.END)
        recent_vaults = load_recent_vaults(max_items=10)
        if not recent_vaults:
            self.recent_menu.add_command(label="(No recent vaults)", state=tk.DISABLED)
        else:
            for vault_path in recent_vaults:
                filename = os.path.basename(vault_path)
                if len(filename) > 50:
                    filename = filename[:47] + "..."
                self.recent_menu.add_command(label=filename, command=lambda path=vault_path: self._open_recent_vault(path))
    
    def _open_recent_vault(self, vault_path: str):
        """Open a vault from the recent vaults list."""
        if not os.path.exists(vault_path):
            messagebox.showerror("Error", f"Vault file not found: {vault_path}")
            self._update_recent_menu()
            return
        self._open_vault(vault_path)
    
    def _update_menu_state(self):
        """Update menu item states based on vault status."""
        unlocked = bool(self.vault_manager and not self.vault_manager.is_locked)
        self.file_menu.entryconfig("Lock Vault", state=tk.NORMAL if self.vault_manager else tk.DISABLED)
        self.file_menu.entryconfig("Backup Vault", state=tk.NORMAL if unlocked else tk.DISABLED)
    
    def _quick_theme_preset(self, preset_id: str) -> None:
        quick_apply_preset(self.root, self._ui_style, preset_id, menus=self._themed_menus)
        self._theme_merged = merge_theme(normalize_preset_id(preset_id), {})

    def _theme_settings(self):
        """Open theme dialog (same presets and colors as courier/FTP frontend)."""
        ThemeSettingsDialog(self.root, self.root, self._ui_style, menus=self._themed_menus)

    def _show_about(self):
        """Show about dialog."""
        messagebox.showinfo("About", "Project Faraday\nOffline Password Vault\n\nVersion 1.0.0\n\nA secure, offline-first password vault\nfor storing credentials and crypto addresses.")
    
    def _show_window(self):
        """Show main window (for tray icon)."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
    
    def _on_closing(self):
        """Handle window close."""
        if self.vault_manager:
            self.vault_manager.lock_vault()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.clipboard_clear()
        self.root.destroy()
    
    def run(self):
        """Run the GUI application."""
        self.root.mainloop()


def main():
    """Main entry point for GUI."""
    MainWindow().run()


if __name__ == "__main__":
    main()
