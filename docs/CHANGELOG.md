# Changelog - Faraday 2.0.0

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
