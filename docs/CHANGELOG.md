# Changelog - Faraday 3.0.0

All entries are newest-first. Project Faraday is developed and maintained by Pure Tech (MIT licensed).

## Version 3.0.0 - July 11, 2026

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
    grab — every click was swallowed. Diagnostics showed window style
    `0x56000008` (`WS_CHILD`), owner `0x0`, z-order far behind the main window,
    and CPU at ~0.5% (the app was deaf, not hung). The access log recorded 17
    sessions with 20 `unlock_cancelled` and 0 `unlock_succeeded`.
  - **Fix:** skip `transient()` on Windows and instead (re)establish a real
    `GWLP_HWNDPARENT` owner link after `overrideredirect(True)`, re-asserted in
    `__init__`, `fit()`, and `show()`; moved `grab_set()` to the end of
    construction (wrapped so a half-built dialog can never leak a grab); clamped
    `_center_over` to the work area (a minimized parent previously spawned an
    off-screen dialog — the same freeze); wrapped `_prompt_password` in
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
    `Cantarell`/`DejaVu Sans`) with named roles — `display` (20 bold),
    `title` (15 semibold), `body` (13), `caption` (11 muted), and `mono` for
    secrets — all hooked into the existing `font_scale` (90–130).
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
- **Surfaces** — `RoundedSurface` (recolorable canvas-backed rounded card),
  `Panel`.
- **Inputs** — `SearchBar`, `PrimaryButton`, `GhostButton`, `DangerButton`,
  `IconButton`, `LabeledEntry`, `SecretField` (reveal toggle + copy), and
  `LabeledText`.
- **Feedback** — `EmptyState`, inline `Toast`/status, and `ConfirmDialog`.
- **Lists** — `CardList`, `EntryCard` (title/subtitle/meta with
  copy/edit/delete actions), and `SectionHeader` (title + item count + "Add").
- **Themed dialogs** — `Dialog` base, `UnlockScreen`, `ThemedPasswordDialog`
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

### Post-release UI fixes
A presentation-only fix pass applied after the 3.0.0 release. **No version
change** (product remains 3.0.0) and **no cryptography or behavior changes** —
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
