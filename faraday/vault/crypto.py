"""
Cryptographic operations for vault encryption/decryption.
Uses Argon2id for key derivation and authenticated encryption (AES-256-GCM or XChaCha20-Poly1305).
"""

import os
from typing import Tuple, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend
import argon2


VAULT_FORMAT_VERSION = 1
ARGON2_TIME_COST = 5  # Increased from 3 for better security
ARGON2_MEMORY_COST = 131072  # 128 MB, increased from 64 MB
ARGON2_PARALLELISM = 4
ARGON2_SALT_LENGTH = 16
ARGON2_HASH_LENGTH = 32
NONCE_LENGTH = 12  # 96 bits for GCM
XCHACHA20_NONCE_LENGTH = 24  # 192 bits for XChaCha20


def get_argon2_params(security_level: str = "standard") -> dict:
    """Get Argon2 parameters based on security level.
    
    Args:
        security_level: One of "low", "standard", "high", "maximum"
        
    Returns:
        Dictionary with time_cost, memory_cost, and parallelism
    """
    levels = {
        "low": {"time_cost": 3, "memory_cost": 65536, "parallelism": 4},
        "standard": {"time_cost": 5, "memory_cost": 131072, "parallelism": 4},
        "high": {"time_cost": 10, "memory_cost": 262144, "parallelism": 4},
        "maximum": {"time_cost": 15, "memory_cost": 524288, "parallelism": 4}
    }
    return levels.get(security_level, levels["standard"])


def validate_argon2_params(time_cost: int, memory_cost: int, parallelism: int) -> bool:
    """Validate Argon2 parameters meet minimum security thresholds.
    
    Args:
        time_cost: Argon2 time cost parameter
        memory_cost: Argon2 memory cost parameter (in KB)
        parallelism: Argon2 parallelism parameter
        
    Returns:
        True if parameters meet minimum security requirements
    """
    if time_cost < 3:
        return False
    if memory_cost < 65536:  # Minimum 64 MB
        return False
    if parallelism < 1 or parallelism > 16:
        return False
    return True


class VaultCrypto:
    """Handles cryptographic operations for the vault."""
    
    def __init__(self, password: bytes):
        """Initialize crypto with master password."""
        self._password = bytearray(password)
        self._master_key: Optional[bytearray] = None
    
    def derive_master_key(self, salt: bytes, time_cost: int = None, memory_cost: int = None, parallelism: int = None) -> bytes:
        """Derive master key from password using Argon2id.
        
        Args:
            salt: Salt for key derivation (must be ARGON2_SALT_LENGTH bytes)
            time_cost: Argon2 time cost (defaults to ARGON2_TIME_COST)
            memory_cost: Argon2 memory cost in KB (defaults to ARGON2_MEMORY_COST)
            parallelism: Argon2 parallelism (defaults to ARGON2_PARALLELISM)
            
        Returns:
            Derived master key (32 bytes)
        """
        if len(salt) != ARGON2_SALT_LENGTH:
            raise ValueError(f"Salt must be {ARGON2_SALT_LENGTH} bytes")
        time_cost = time_cost if time_cost is not None else ARGON2_TIME_COST
        memory_cost = memory_cost if memory_cost is not None else ARGON2_MEMORY_COST
        parallelism = parallelism if parallelism is not None else ARGON2_PARALLELISM
        if not validate_argon2_params(time_cost, memory_cost, parallelism):
            raise ValueError("Argon2 parameters do not meet minimum security requirements")
        raw_hash = argon2.low_level.hash_secret_raw(secret=bytes(self._password), salt=salt, time_cost=time_cost, memory_cost=memory_cost, parallelism=parallelism, hash_len=ARGON2_HASH_LENGTH, type=argon2.low_level.Type.ID)
        return bytes(raw_hash)
    
    def derive_subkey(self, master_key: bytes, info: bytes, length: int = 32) -> bytes:
        """Derive subkey from master key using HKDF."""
        return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info, backend=default_backend()).derive(master_key)
    
    def encrypt_aes_gcm(self, plaintext: bytes, master_key: bytes) -> Tuple[bytes, bytes]:
        """Encrypt data using AES-256-GCM."""
        enc_key = self.derive_subkey(master_key, b"faraday_encryption", 32)
        nonce = os.urandom(NONCE_LENGTH)
        return nonce, AESGCM(enc_key).encrypt(nonce, plaintext, None)
    
    def decrypt_aes_gcm(self, nonce: bytes, ciphertext: bytes, master_key: bytes) -> bytes:
        """Decrypt data using AES-256-GCM. Raises InvalidTag if authentication fails."""
        return AESGCM(self.derive_subkey(master_key, b"faraday_encryption", 32)).decrypt(nonce, ciphertext, None)
    
    def encrypt_xchacha20(self, plaintext: bytes, master_key: bytes) -> Tuple[bytes, bytes]:
        """Encrypt data using XChaCha20-Poly1305."""
        enc_key = self.derive_subkey(master_key, b"faraday_encryption", 32)
        nonce = os.urandom(XCHACHA20_NONCE_LENGTH)
        return nonce, ChaCha20Poly1305(enc_key).encrypt(nonce, plaintext, None)
    
    def decrypt_xchacha20(self, nonce: bytes, ciphertext: bytes, master_key: bytes) -> bytes:
        """Decrypt data using XChaCha20-Poly1305. Raises InvalidTag if authentication fails."""
        return ChaCha20Poly1305(self.derive_subkey(master_key, b"faraday_encryption", 32)).decrypt(nonce, ciphertext, None)
    
    def generate_salt(self) -> bytes:
        """Generate a random salt for key derivation."""
        return os.urandom(ARGON2_SALT_LENGTH)
    
    def clear_memory(self, passes: int = 3):
        """Attempt to clear sensitive data from memory with multiple overwrite passes.
        
        Args:
            passes: Number of overwrite passes (default 3)
        """
        if self._password:
            for _ in range(passes):
                for i in range(len(self._password)):
                    self._password[i] = 0
            self._password = bytearray()
        if self._master_key:
            for _ in range(passes):
                for i in range(len(self._master_key)):
                    self._master_key[i] = 0
            self._master_key = None
