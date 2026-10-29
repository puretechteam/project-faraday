# AGENTS.md: Project Faraday

Conventions for any coding agent working in this repo. Carried over from the
former shared KiloProjects conventions when the project moved to
`Desktop\ClaudeProjects`.

## The vault is precious
- The owner's real vault lives in `Documents\Faraday` (`Main.vault` + `Main.vault.attachments/`
  + `Main.vault.backups/`), outside this repo. **Never open, decrypt, copy, move or modify
  anything there** during development. Tests run against temp directories only;
  `tests/conftest.py` fails any test that touches `Documents\Faraday` or a repo `vaults/` folder.
- Manual app runs during development use scratch folders via
  `FARADAY_VAULTS_DIR` and `FARADAY_APPDATA`.
- Never weaken the save path (`faraday/vault/manager.py`, `faraday/vault/atomic.py`,
  `faraday/vault/backups.py`, `faraday/vault/filelock.py`) without tests proving
  the change is safe. The on-disk format is version 1; do not change it.

## Working location
- Operate only inside this project directory. Ask before reading or editing
  anything outside it.

## Git / GitHub: never touch unless explicitly asked
- Do not run any git or GitHub operation (commit, push, pull, branch, merge, tag,
  PR, issue, release) unless the owner explicitly asks. Even then, confirm the
  exact repo, files and branch first.
- Never `git push --force` or `--force-with-lease`.
- The owner commits via GitHub Desktop. GitHub org: `puretechteam` (brand: Pure Tech).
- Never run `git clean -x` without checking what it deletes (git-ignored local files live here).

## Versions
- Never bump or change version numbers. The current version is the source of truth.

## Tests and builds
- `python -m pytest -q` must pass before reporting work complete.
- Windows build: `packaging\build.ps1`, then `packaging\install.ps1` (per-user install).

## Copy
- No em-dashes in user-facing copy (UI strings, docs). Code and comments are unaffected.
  `tests/test_copy_style.py` enforces this for UI strings.

## .gitignore hygiene
- Keep `.gitignore` current whenever files are added or generated: secrets, vaults,
  backups, lock files, build output, caches, editor junk.
