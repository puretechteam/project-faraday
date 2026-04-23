# Repository Contents Guide

This document defines what should be committed for Faraday releases.

## Include in the repository

Commit the application source directory `faraday/`, the docs directory `docs/` (including `docs/README.md`, `docs/SECURITY.md`, `docs/vault_format.md`, and `docs/CHANGELOG.md`), the asset directory `assets/`, and the project files `setup.py`, `requirements.txt`, `dependencies.bat`, and `faraday.ps1`.

## Do not include in the repository

Do not commit generated or local-only content such as `__pycache__/`, `*.pyc`, `*.pyo`, `*.egg-info/`, `build/`, `dist/`, `vaults/`, `*.vault`, `*.vault.tmp`, `*.vault.attachments/`, `.faraday_vault_history.json`, `.cursor/`, `.vscode/`, `.idea/`, `.DS_Store`, and `Thumbs.db`.

`docs/ideas.md` is private planning content and should remain local unless intentionally shared.

## Pre-release check

Before publishing, verify that only source code, release docs, scripts, and required assets are staged, and that local vault data or build artifacts are excluded.

