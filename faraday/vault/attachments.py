"""
Document attachment storage with encrypted file handling.
Uses HKDF for per-file key derivation from vault master key.
"""

import os
import uuid
import hashlib
from typing import Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag

from .security import secure_delete_file

NONCE_LENGTH = 12  # 96 bits for AES-GCM


class AttachmentStorage:
    """Storage for encrypted document attachments."""
    
    def __init__(self, attachments_dir: str, master_key: bytes):
        """Initialize attachment storage.
        
        Args:
            attachments_dir: Directory path for storing encrypted attachments
            master_key: Vault master key for deriving file keys
        """
        self.attachments_dir = attachments_dir
        self.master_key = master_key
        os.makedirs(attachments_dir, exist_ok=True)
    
    def _derive_file_key(self, file_uuid: str) -> bytes:
        """Derive per-file key using HKDF.
        
        Args:
            file_uuid: UUID string for the file (used as HKDF info parameter)
            
        Returns:
            Derived 32-byte key for file encryption
        """
        info = f"faraday_attachment_{file_uuid}".encode('utf-8')
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=info,
            backend=default_backend()
        )
        return hkdf.derive(self.master_key)
    
    def compute_file_hash(self, file_data: bytes) -> str:
        """Compute SHA-256 hash of file data.
        
        Args:
            file_data: File data bytes
            
        Returns:
            Hex-encoded SHA-256 hash
        """
        return hashlib.sha256(file_data).hexdigest()
    
    def encrypt_file(self, file_data: bytes, file_uuid: str) -> Tuple[bytes, bytes]:
        """Encrypt file data using derived key.
        
        Args:
            file_data: Plaintext file data
            file_uuid: UUID string for the file
            
        Returns:
            Tuple of (nonce, ciphertext)
        """
        file_key = self._derive_file_key(file_uuid)
        nonce = os.urandom(NONCE_LENGTH)
        ciphertext = AESGCM(file_key).encrypt(nonce, file_data, None)
        return nonce, ciphertext
    
    def decrypt_file(self, nonce: bytes, ciphertext: bytes, file_uuid: str) -> bytes:
        """Decrypt file data using derived key.
        
        Args:
            nonce: Encryption nonce
            ciphertext: Encrypted file data
            file_uuid: UUID string for the file
            
        Returns:
            Decrypted file data
            
        Raises:
            InvalidTag: If authentication fails
        """
        file_key = self._derive_file_key(file_uuid)
        return AESGCM(file_key).decrypt(nonce, ciphertext, None)
    
    def store_file(self, file_data: bytes) -> Tuple[str, str]:
        """Store encrypted file.
        
        Args:
            file_data: Plaintext file data to encrypt and store
            
        Returns:
            Tuple of (file_uuid, file_hash)
            file_uuid: UUID string for the file reference
            file_hash: SHA-256 hash of plaintext data
        """
        file_uuid = str(uuid.uuid4())
        file_hash = self.compute_file_hash(file_data)
        nonce, ciphertext = self.encrypt_file(file_data, file_uuid)
        
        # Store encrypted file (nonce + ciphertext)
        file_path = os.path.join(self.attachments_dir, f"{file_uuid}.enc")
        with open(file_path, 'wb') as f:
            f.write(nonce)
            f.write(ciphertext)
        
        return file_uuid, file_hash
    
    def retrieve_file(self, file_uuid: str) -> bytes:
        """Retrieve and decrypt file.
        
        Args:
            file_uuid: UUID string for the file reference
            
        Returns:
            Decrypted file data
            
        Raises:
            FileNotFoundError: If file doesn't exist
            InvalidTag: If decryption/authentication fails
        """
        file_path = os.path.join(self.attachments_dir, f"{file_uuid}.enc")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Attachment file not found: {file_uuid}")
        
        with open(file_path, 'rb') as f:
            nonce = f.read(NONCE_LENGTH)
            if len(nonce) != NONCE_LENGTH:
                raise ValueError(f"Invalid attachment file: {file_uuid}")
            ciphertext = f.read()
        
        return self.decrypt_file(nonce, ciphertext, file_uuid)
    
    def delete_file(self, file_uuid: str) -> bool:
        """Delete encrypted file with secure deletion.
        
        Args:
            file_uuid: UUID string for the file reference
            
        Returns:
            True if file was deleted, False if not found
        """
        file_path = os.path.join(self.attachments_dir, f"{file_uuid}.enc")
        if not os.path.exists(file_path):
            return False
        
        secure_delete_file(file_path, passes=3)
        return True

