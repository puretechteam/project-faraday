"""
Vault error types. Every class subclasses a builtin so older callers that
catch RuntimeError / OSError keep working.
"""


class VaultLockedError(RuntimeError):
    """The vault is locked; unlock it before reading or writing entries."""


class VaultReadOnlyError(RuntimeError):
    """The vault was opened read-only and cannot be saved."""


class VaultInUseError(OSError):
    """Another Faraday window or CLI process has this vault open."""


class VaultChangedOnDiskError(RuntimeError):
    """The vault file changed on disk since it was unlocked; refusing to overwrite it."""


class AttachmentsPresentError(RuntimeError):
    """The operation would make existing document attachments undecryptable."""


class AttachmentIntegrityError(ValueError):
    """A decrypted attachment does not match its recorded SHA-256 hash."""
