# Changelog

All entries are newest-first. Project Faraday is developed and maintained by Pure Tech (MIT licensed).

## Version 3.0.0 - October 29, 2026

The first public 3.0 release: a new desktop app on a hardened vault core. It replaces the July 2026 Tkinter redesign described further down, which was never published.

### New desktop app (PySide6)
- `faraday gui` now opens a new Qt desktop app. The old Tkinter GUI has been removed.
- Live two-factor codes: two-factor items with an authenticator secret (base32 or `otpauth://`) show the current code with a countdown.
- Import from Bitwarden (.json, .csv), KeePass 2 (.xml, .csv), KeePassXC (.csv), another Faraday vault, or a `.faraday` archive, with preview, duplicate detection and an offer to securely delete the plain-text export afterwards.
- Encrypted export: one password-protected `.faraday` archive holding every item and document. There is no plain-text export.
- Logins gain optional Website and Notes fields (only written when set, so existing entries are unchanged on disk).
- Windows app: `packaging\build.ps1` builds a standalone `Faraday.exe`; `packaging\install.ps1` installs it per user with a Start Menu shortcut.
- One list and detail view for every entry type, plus **All items**. Every field can be copied, and every secret can be revealed (it masks itself again after a configurable delay).
- Forms are built from a single field schema (`faraday/models/schema.py`), with inline validation and warnings. Edits keep the entry's id, created time and any fields this version does not know about.
- Command palette (Ctrl+K) searches items and commands. Shift+Enter copies an item's main secret.
- A standalone password and passphrase generator (8 to 128 characters, or 3 to 12 words from the EFF large wordlist) that also works while the vault is locked.
- New Overview dashboard with vault health checks: weak and reused passwords, expiring cards, and snapshot age.
- Themes: all 11 classic themes are back as full themes (Classic dark and light, Twilight, Graphite, Poly, Forest, New Vegas, Spiral, Sunset, High contrast, Paper), plus Faraday dark and light and Match Windows, chosen from a visual gallery in Settings or the command palette. Your 3.0 theme and text size carry over automatically.
- New Settings page: auto-lock delay, clipboard clear delay, reveal delay, action PIN, theme, accent colour, text size, tray, lock on minimize, lock when Windows locks, and hiding the window from screen capture.
- New pages: Backups (restore snapshots, export a verified full backup), Access log and Threat model.
- Auto-lock now clears the screen. Locking closes dialogs, destroys every page, and clears the clipboard if it still holds a copied secret.
- Copied secrets are kept out of Windows clipboard history and cloud clipboard.
- One consistent PIN policy for every sensitive action. After 5 wrong PINs only the master password is accepted until the next unlock.
- Key derivation and disk writes run in the background, so the window never freezes.
- Single instance: launching Faraday again brings the open window to the front.

### Vault safety (core)
- Saves are crash-safe: temp file, fsync, then an atomic replace, with retries when antivirus briefly holds the file.
- Every save first keeps an encrypted snapshot of the previous version in `<vault>.backups/` (the 10 newest, plus one per day for 14 days).
- Saves use the salt and key settings captured at unlock. A vault file changed by another program is no longer silently overwritten.
- A lock file stops two Faraday windows, or a window and the CLI, from writing the same vault at once.
- A failed save rolls the in-memory changes back. Deleting a document wipes its file only after the vault has saved.
- Unknown fields and entry types written by newer versions are preserved instead of dropped.
- `upgrade-vault` re-keys safely and refuses when document attachments exist (previously it made them unreadable).
- New CLI commands: `backup`, `list-backups`, `restore`, and `generate --words`. `delete-vault --secure` now asks you to type the file name.
- The default vault folder is now `Documents\Faraday` instead of `vaults` in the launch folder. A bare `--vault name.vault` on the command line means a file there.
- Recent vaults, settings, PIN and access log all live in `%LOCALAPPDATA%\FaradayVault`. The old recent-vaults file is imported once.
- The file format is unchanged (version 1). Vaults stay fully compatible with 3.0 in both directions.
- New automated test suite (`python -m pytest`), including compatibility checks against a vault written by 3.0.

## 3.0 development: Tkinter redesign - July 11, 2026 (superseded, not released)

This release is a **presentation-only GUI redesign**. There are no changes to
vault cryptography, the data model, the password generator, or the CLI. The
backend (`faraday/vault/`, `faraday/models/`, `faraday/generator/`,
`faraday/cli.py`) is untouched.

### Bug fixes
- Fixed a critical lockup on the locked screen: clicking a recent vault (or
  opening a vault via the file picker) froze the entire application because the
  master-password dialog never appeared.
  - **Root cause:** in `faraday/gui/widgets/dialogs.py`, `Dialog.__init__`
    called `transient()` and then `overrideredirect(True)`. On Windows, Tk
    rebuilds the wrapper HWND as an unowned `WS_CHILD` child-of-desktop, so the
    modal password dialog was created with no owner, could not be activated,
    never received focus, and sank behind the main window while holding a modal
    grab; every click was swallowed. Diagnostics showed window style
    `0x56000008` (`WS_CHILD`), owner `0x0`, z-order far behind the main window,
    and CPU at ~0.5% (the app was deaf, not hung). The access log recorded 17
    sessions with 20 `unlock_cancelled` and 0 `unlock_succeeded`.
  - **Fix:** skip `transient()` on Windows and instead (re)establish a real
    `GWLP_HWNDPARENT` owner link after `overrideredirect(True)`, re-asserted in
    `__init__`, `fit()`, and `show()`; moved `grab_set()` to the end of
    construction (wrapped so a half-built dialog can never leak a grab); clamped
    `_center_over` to the work area (a minimized parent previously spawned an
    off-screen dialog; the same freeze); wrapped `_prompt_password` in
    `try/finally`; fixed the `native_dialog` topmost-restore; and re-applied the
    taskbar style after `overrideredirect` toggles.
  - Added `scripts/check_dialog_stacking.py`, a Win32 z-order +
    `WindowFromPoint` regression guard, because Tk-level checks
    (`winfo_viewable`) could not detect this class of bug.

### Design system
- Introduced a new calm, minimalist token system built on top of the existing
  merged theme palette:
  - **Spacing scale:** a consistent 4 / 8 / 12 / 16 / 20 / 24 px grid used
    throughout the interface.
  - **Radii:** `sm = 6`, `md = 10`, `lg = 14` px for surfaces, cards, and
    inputs.
  - **Typography roles:** a system font stack (`Segoe UI` / `.SF NS Text` /
    `Cantarell`/`DejaVu Sans`) with named roles; `display` (20 bold),
    `title` (15 semibold), `body` (13), `caption` (11 muted), and `mono` for
    secrets; all hooked into the existing `font_scale` (90–130).
  - **Semantic tokens** derived from the merged palette (`surface`, `hover`,
    `on_accent`, etc.) provide a single source of truth for every widget.

### App shell
- Replaced the old `ttk.Notebook` tab strip with a new layout:
  - **Collapsible left sidebar** navigation (icon + label items, collapses to
    icons) with active-state accent and a branded header.
  - **Topbar** with a `SearchBar` (filters the active section), section title,
    vault name, lock control, and a theme quick-control button.
  - **Centered Unlock screen** (replaces the old modal password dialog) with a
    recent-vaults list and Open/New Vault actions.
  - **Scrollable content area** plus a **status bar** showing the active vault.

### Shared component library (`faraday/gui/widgets/`)
- **Surfaces**: `RoundedSurface` (recolorable canvas-backed rounded card),
  `Panel`.
- **Inputs**: `SearchBar`, `PrimaryButton`, `GhostButton`, `DangerButton`,
  `IconButton`, `LabeledEntry`, `SecretField` (reveal toggle + copy), and
  `LabeledText`.
- **Feedback**: `EmptyState`, inline `Toast`/status, and `ConfirmDialog`.
- **Lists**: `CardList`, `EntryCard` (title/subtitle/meta with
  copy/edit/delete actions), and `SectionHeader` (title + item count + "Add").
- **Themed dialogs**: `Dialog` base, `UnlockScreen`, `ThemedPasswordDialog`
  (reveal + generate), `AboutDialog`, and the restyled `ThemeSettingsDialog`.
- All widgets read tokens from the design system and recolor live via
  `apply_theme`, registered through the themed-widget registry.

### Section reskin
- Every section was rebuilt on the shared components while preserving all
  `VaultManager` read/write logic: credentials, crypto, secure notes, cards,
  identities, emergency contacts, 2FA, API keys, Wi-Fi, documents, and the
  threat model. Each view exposes a `filter(query)` method wired to the topbar
  search.

### Theme system preserved
- All 11 presets, per-color overrides, and the live font-scale control continue
  to apply across the new interface. The `ui_theme` public API is unchanged and
  the themed-widget registry keeps custom/canvas surfaces live-updating on
  preset and override changes.

### Follow-up UI fixes
A presentation-only fix pass applied after the 3.0.0 release. **No version
change** (product remains 3.0.0) and **no cryptography or behavior changes**:
`VaultManager`, models, generator, and CLI are untouched.
- Fixed invisible/unreadable labels (black-on-dark text) in dialogs and inputs
  by theming `tk` widget backgrounds to the active palette.
- `RoundedSurface` now sizes to its content so cards are correctly visible.
- `CardList` inner-frame width now syncs to the scroll region, with a corrected
  scroll-region calculation and a localized mousewheel binding.
- Sidebar width and collapse state are now honored on layout.
- Restored the configurable password generator: new `PasswordGeneratorDialog`
  (length 8–64, uppercase/lowercase/digits/symbols, exclude-similar, exclude
  field, live preview, copy/use) wired into the Credentials section (and Wi-Fi
  section) so users can generate and insert passwords.
- Compacted the unlock/password dialog (`ThemedPasswordDialog` ~380×190) with
  proportionally sized buttons; added a `show_generate` flag so the generator
  appears only when creating a NEW vault, not when unlocking an existing one.
- Content area now fills the entire window (both width and height); sections
  standardized to an 8px spacing grid with consistent margins.
- Reworked the sidebar/content boundary: removed the hard gap and added a subtle
  1px themed separator; sidebar given a distinct elevated surface.
- Removed the out-of-place native top menu bar (File/Security/Theme/Help) and
  relocated those actions into a Topbar "More" menu (IconButton + themed popup),
  matching the minimalist design.
- Fixed unthemed gray widgets in the Threat Model panel and standardized section
  spacing/padding.

## Version 2.0.0 - April 23, 2026
- UI and theming overhaul
  - Replaced the native Windows menubar with an in-window themed strip (File, Security, Theme, Help) so it follows the selected theme.
  - Added theme settings, quick presets, and persistent local theme save/load via `%LOCALAPPDATA%\FaradayVault\gui_theme.json`.
  - **User impact:** consistent theming across navigation and dialogs, including on Windows.

- Security actions and access guard improvements
  - Added optional Action PIN workflow from the Security menu (set up / change / disable).
  - Added guard checks for sensitive actions (copy, reveal, delete, export-style flows) across sections.
  - Improved protected dialogs for long secret content with better scrolling/readability.
  - **User impact:** sensitive actions can require an extra unlock step without changing master-password flow.

- Vault operations, safety, and reliability updates
  - Added `Backup Vault` flow from the File menu.
  - Updated open-vault prompt to remove generator access in that path (`show_generate_password=False`).
  - Fixed auto-lock worker crash (`RuntimeError: cannot join current thread`) by preventing self-join in the lock path.
  - Added offline structure audit script (`scripts/audit_vault_structure.py`) for envelope/header sanity checks.
  - **User impact:** safer backup/lock flow, cleaner open-vault UX, and improved auto-lock stability.

- Data model and section capability expansion
  - Identity: added optional SSN support, made email validation conditional when email is present, and guarded SSN copy behavior.
  - Documents: added category support in model/UI (including ID/Driver License-style categories).
  - Two-factor: improved scrollable presentation and safer reveal/copy UX for codes.
  - Completed guard wiring across credentials, secure notes, and Wi-Fi sensitive actions.
  - **User impact:** broader real-world record support with stronger consistency on protected actions.

- Threat model and educational analysis panel
  - Added a dedicated `Threat model` tab with honest scope/disclaimers, vault KDF metadata, local Argon2 timing benchmarks, and clearer quantum wording.
  - Added metadata-only credential/Wi-Fi analysis cards (length + naive entropy context; no plaintext password display).
  - Updated scenario table with clearer labels, 200/300-bit rows, improved resizing/scrolling, unified duration wording, and hundredths precision.
  - **User impact:** clearer security context and strength guidance without exposing stored secrets.
