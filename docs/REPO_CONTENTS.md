# Repository Contents Guide

This document defines what should be committed for Faraday releases.

## Include in the repository

Commit the application source directory `faraday/` (including the vendored Lucide icons and EFF wordlist), the tests in `tests/` (including the throwaway `tests/fixtures/v1_sample.vault`, whose password is published in the tests), the build files in `packaging/`, the docs (`README.md`, `SECURITY.md`, `vault_format.md`, `AGENTS.md`, and `docs/`, including `docs/screenshots/`), the asset directory `assets/`, and the project files `setup.py`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `dependencies.bat`, and `faraday.ps1`.

## Do not include in the repository

Do not commit generated or local-only content such as `__pycache__/`, `*.pyc`, `*.pyo`, `*.egg-info/`, `build/`, `dist/`, `vaults/`, `*.vault`, `*.vault.tmp`, `*.vault.attachments/`, `*.vault.backups/`, `*.vault.lock`, `*.faraday` archives, `.faraday_vault_history.json`, `.pytest_cache/`, `promo/`, `.vscode/`, `.idea/`, `.DS_Store`, and `Thumbs.db`.

`docs/ideas.md` is private planning content and should remain local unless intentionally shared.

## Pre-release check

Before publishing, verify that only source code, release docs, scripts, and required assets are staged, and that local vault data or build artifacts are excluded.

