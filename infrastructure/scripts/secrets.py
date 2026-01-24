"""Secrets management utilities for SOPS and age encryption.

This module provides utilities for generating age encryption keys,
creating SOPS configuration files, and managing encrypted secrets
for Kubernetes deployments.
"""

import os
import re
import secrets as secrets_module
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class AgeKeyPair:
    """Represents an age encryption key pair for SOPS.

    Attributes:
        public_key: Age public key (format: age1...)
        private_key: Age private key (format: AGE-SECRET-KEY-1...)
        created_at: Timestamp when the key pair was generated
    """

    public_key: str
    private_key: str
    created_at: datetime

    def to_kubernetes_secret(self) -> dict[str, Any]:
        """Convert to Kubernetes secret format for Flux.

        Returns:
            Dictionary representing a Kubernetes Secret manifest
        """
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "sops-age", "namespace": "flux-system"},
            "type": "Opaque",
            "stringData": {"age.agekey": self.private_key},
        }


def generate_age_key() -> AgeKeyPair:
    """Generate a new age encryption key pair.

    Uses the age-keygen command to generate a new key pair.

    Returns:
        AgeKeyPair containing the public and private keys

    Raises:
        RuntimeError: If age-keygen is not installed or fails
        ValueError: If the generated keys don't match expected format
    """
    try:
        result = subprocess.run(["age-keygen"], capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise RuntimeError("age-keygen not found. Install age: https://github.com/FiloSottile/age")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"age-keygen failed: {e.stderr}")

    # Parse output to extract keys
    output = result.stdout

    # Extract public key (format: "# public key: age1...")
    public_match = re.search(r"# public key: (age1\w+)", output)
    if not public_match:
        raise ValueError("Could not extract public key from age-keygen output")
    public_key = public_match.group(1)

    # Extract private key (format: "AGE-SECRET-KEY-1...")
    private_match = re.search(r"(AGE-SECRET-KEY-1\w+)", output)
    if not private_match:
        raise ValueError("Could not extract private key from age-keygen output")
    private_key = private_match.group(1)

    # Validate key formats
    if not is_valid_age_public_key(public_key):
        raise ValueError(f"Generated public key has invalid format: {public_key}")
    if not is_valid_age_private_key(private_key):
        raise ValueError(f"Generated private key has invalid format: {private_key}")

    return AgeKeyPair(public_key=public_key, private_key=private_key, created_at=datetime.now())


def is_valid_age_public_key(key: str) -> bool:
    """Validate age public key format.

    Age public keys start with "age1" followed by base64-encoded data.

    Args:
        key: The public key string to validate

    Returns:
        True if the key has valid format, False otherwise
    """
    if not key.startswith("age1"):
        return False

    # Check if the rest is valid base64 (bech32 encoding for age)
    # Age uses bech32 encoding, which uses lowercase alphanumeric except 'b', 'i', 'o'
    key_data = key[4:]  # Remove "age1" prefix
    if not key_data:
        return False

    # Bech32 character set
    valid_chars = set("qpzry9x8gf2tvdw0s3jn54khce6mua7l")
    return all(c in valid_chars for c in key_data.lower())


def is_valid_age_private_key(key: str) -> bool:
    """Validate age private key format.

    Age private keys start with "AGE-SECRET-KEY-1" followed by base64-encoded data.

    Args:
        key: The private key string to validate

    Returns:
        True if the key has valid format, False otherwise
    """
    if not key.startswith("AGE-SECRET-KEY-1"):
        return False

    # Check if the rest is valid base64 (bech32 encoding for age)
    key_data = key[16:]  # Remove "AGE-SECRET-KEY-1" prefix
    if not key_data:
        return False

    # Bech32 character set
    valid_chars = set("QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L")
    return all(c in valid_chars for c in key_data.upper())


def create_sops_config(age_public_key: str, output_path: Path | None = None) -> str:
    """Create .sops.yaml configuration file.

    Args:
        age_public_key: The age public key to use for encryption
        output_path: Optional path where to write the config file

    Returns:
        The SOPS configuration as a YAML string

    Raises:
        ValueError: If the public key format is invalid
    """
    if not is_valid_age_public_key(age_public_key):
        raise ValueError(f"Invalid age public key format: {age_public_key}")

    config = f"""# SOPS configuration for age encryption
creation_rules:
  - path_regex: \\.enc\\.yaml$
    encrypted_regex: ^(data|stringData)$
    age: {age_public_key}
"""

    if output_path:
        output_path.write_text(config)

    return config


def encrypt_secret_with_sops(
    secret_manifest: dict[str, Any], age_public_key: str, sops_config_path: Path | None = None
) -> dict[str, Any]:
    """Encrypt a Kubernetes secret manifest using SOPS.

    Args:
        secret_manifest: The Kubernetes secret manifest to encrypt
        age_public_key: The age public key to use for encryption
        sops_config_path: Optional path to .sops.yaml config file

    Returns:
        The encrypted secret manifest

    Raises:
        RuntimeError: If SOPS is not installed or encryption fails
        ValueError: If the manifest is invalid
    """
    import tempfile

    import yaml

    # Validate the secret manifest
    if not isinstance(secret_manifest, dict):
        raise ValueError("Secret manifest must be a dictionary")
    if secret_manifest.get("kind") != "Secret":
        raise ValueError("Manifest must be a Kubernetes Secret")

    # Create a temporary file for the secret (use .enc.yaml suffix to match SOPS config)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".enc.yaml", delete=False) as f:
        yaml.dump(secret_manifest, f)
        temp_path = Path(f.name)

    try:
        # Create temporary .sops.yaml if not provided
        if sops_config_path is None:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(create_sops_config(age_public_key))
                sops_config_path = Path(f.name)
            temp_sops_config = True
        else:
            temp_sops_config = False

        # Run SOPS encryption
        # Set environment variables for SOPS
        env = os.environ.copy()
        env["SOPS_AGE_RECIPIENTS"] = age_public_key
        # Point SOPS to the config file
        env["SOPS_CONFIG"] = str(sops_config_path)

        try:
            result = subprocess.run(
                [
                    "sops",
                    "--encrypt",
                    "--encrypted-regex",
                    "^(data|stringData)$",
                    temp_path,
                ],
                capture_output=True,
                text=True,
                check=True,
                env=env,
            )
        except FileNotFoundError:
            raise RuntimeError("sops not found. Install SOPS: https://github.com/getsops/sops")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"SOPS encryption failed: {e.stderr}")

        # Parse the encrypted output
        encrypted_manifest = yaml.safe_load(result.stdout)
        return encrypted_manifest

    finally:
        # Clean up temporary files
        temp_path.unlink(missing_ok=True)
        if temp_sops_config:
            sops_config_path.unlink(missing_ok=True)


def decrypt_secret_with_sops(
    encrypted_manifest: dict[str, Any], age_private_key: str
) -> dict[str, Any]:
    """Decrypt a SOPS-encrypted Kubernetes secret manifest.

    Args:
        encrypted_manifest: The encrypted secret manifest
        age_private_key: The age private key to use for decryption

    Returns:
        The decrypted secret manifest

    Raises:
        RuntimeError: If SOPS is not installed or decryption fails
        ValueError: If the manifest is invalid
    """
    import tempfile

    import yaml

    # Validate the encrypted manifest
    if not isinstance(encrypted_manifest, dict):
        raise ValueError("Encrypted manifest must be a dictionary")
    if "sops" not in encrypted_manifest:
        raise ValueError("Manifest does not appear to be SOPS-encrypted")

    # Create temporary files
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(encrypted_manifest, f)
        temp_encrypted_path = Path(f.name)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(age_private_key)
        temp_key_path = Path(f.name)

    try:
        # Run SOPS decryption
        try:
            result = subprocess.run(
                ["sops", "--decrypt", "--age", age_private_key, temp_encrypted_path],
                capture_output=True,
                text=True,
                check=True,
                env={**subprocess.os.environ, "SOPS_AGE_KEY": age_private_key},
            )
        except FileNotFoundError:
            raise RuntimeError("sops not found. Install SOPS: https://github.com/getsops/sops")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"SOPS decryption failed: {e.stderr}")

        # Parse the decrypted output
        decrypted_manifest = yaml.safe_load(result.stdout)
        return decrypted_manifest

    finally:
        # Clean up temporary files
        temp_encrypted_path.unlink(missing_ok=True)
        temp_key_path.unlink(missing_ok=True)


# Service Credential Dataclasses


@dataclass
class PostgreSQLCredentials:
    """PostgreSQL database credentials.

    Attributes:
        postgres_password: Admin password for postgres user
        username: Application user name
        password: Application user password
        database: Database name
    """

    postgres_password: str
    username: str
    password: str
    database: str

    def to_secret_manifest(self, namespace: str = "database") -> dict[str, Any]:
        """Convert to Kubernetes secret manifest (to be encrypted with SOPS).

        Args:
            namespace: Kubernetes namespace for the secret (default: database)

        Returns:
            Dictionary representing a Kubernetes Secret manifest
        """
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "postgresql-credentials", "namespace": namespace},
            "type": "Opaque",
            "stringData": {
                "postgres-password": self.postgres_password,
                "username": self.username,
                "password": self.password,
                "database": self.database,
            },
        }


@dataclass
class RedisCredentials:
    """Redis authentication credentials.

    Attributes:
        password: Redis authentication password
    """

    password: str

    def to_secret_manifest(self, namespace: str = "cache") -> dict[str, Any]:
        """Convert to Kubernetes secret manifest (to be encrypted with SOPS).

        Args:
            namespace: Kubernetes namespace for the secret (default: cache)

        Returns:
            Dictionary representing a Kubernetes Secret manifest
        """
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "redis-credentials", "namespace": namespace},
            "type": "Opaque",
            "stringData": {"redis-password": self.password},
        }


@dataclass
class AuthentikCredentials:
    """Authentik application credentials.

    Attributes:
        secret_key: Django secret key for Authentik
        postgres_password: Database password for Authentik's PostgreSQL connection
        bootstrap_password: Initial admin password
        bootstrap_token: Initial API token
    """

    secret_key: str
    postgres_password: str
    bootstrap_password: str
    bootstrap_token: str

    def to_secret_manifest(self, namespace: str = "auth") -> dict[str, Any]:
        """Convert to Kubernetes secret manifest (to be encrypted with SOPS).

        Args:
            namespace: Kubernetes namespace for the secret (default: auth)

        Returns:
            Dictionary representing a Kubernetes Secret manifest
        """
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "authentik-credentials", "namespace": namespace},
            "type": "Opaque",
            "stringData": {
                "secret-key": self.secret_key,
                "postgres-password": self.postgres_password,
                "bootstrap-password": self.bootstrap_password,
                "bootstrap-token": self.bootstrap_token,
            },
        }


@dataclass
class CloudflareConfig:
    """Cloudflare API configuration for cert-manager.

    Attributes:
        api_token: API token with DNS edit permissions
        email: Cloudflare account email
        zone_id: Zone ID for the domain
    """

    api_token: str
    email: str
    zone_id: str

    def to_secret_manifest(self, namespace: str = "cert-manager") -> dict[str, Any]:
        """Convert to Kubernetes secret manifest (to be encrypted with SOPS).

        Args:
            namespace: Kubernetes namespace for the secret (default: cert-manager)

        Returns:
            Dictionary representing a Kubernetes Secret manifest
        """
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "cloudflare-api-token", "namespace": namespace},
            "type": "Opaque",
            "stringData": {"api-token": self.api_token},
        }


# Credential Generation Utilities


def generate_secure_password(length: int = 32) -> str:
    """Generate a cryptographically secure random password.

    Args:
        length: Length of the password (default: 32)

    Returns:
        A secure random password string
    """
    import string

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"
    return "".join(secrets_module.choice(alphabet) for _ in range(length))


def generate_django_secret_key(length: int = 50) -> str:
    """Generate a Django-compatible secret key.

    Args:
        length: Length of the secret key (default: 50)

    Returns:
        A Django-compatible secret key string
    """
    import string

    # Django secret keys use a specific character set
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*(-_=+)"
    return "".join(secrets_module.choice(alphabet) for _ in range(length))


def generate_api_token(length: int = 64) -> str:
    """Generate a secure API token.

    Args:
        length: Length of the token (default: 64)

    Returns:
        A secure random token string (hex)
    """
    return secrets_module.token_hex(length // 2)


def create_postgresql_credentials(
    database: str = "app",
    username: str = "appuser",
    postgres_password: str | None = None,
    password: str | None = None,
) -> PostgreSQLCredentials:
    """Create PostgreSQL credentials with auto-generated passwords if not provided.

    Args:
        database: Database name (default: app)
        username: Application user name (default: appuser)
        postgres_password: Admin password (auto-generated if None)
        password: Application user password (auto-generated if None)

    Returns:
        PostgreSQLCredentials instance
    """
    return PostgreSQLCredentials(
        postgres_password=postgres_password or generate_secure_password(),
        username=username,
        password=password or generate_secure_password(),
        database=database,
    )


def create_redis_credentials(password: str | None = None) -> RedisCredentials:
    """Create Redis credentials with auto-generated password if not provided.

    Args:
        password: Redis password (auto-generated if None)

    Returns:
        RedisCredentials instance
    """
    return RedisCredentials(password=password or generate_secure_password())


def create_authentik_credentials(
    postgres_password: str | None = None,
    secret_key: str | None = None,
    bootstrap_password: str | None = None,
    bootstrap_token: str | None = None,
) -> AuthentikCredentials:
    """Create Authentik credentials with auto-generated values if not provided.

    Args:
        postgres_password: Database password (auto-generated if None)
        secret_key: Django secret key (auto-generated if None)
        bootstrap_password: Initial admin password (auto-generated if None)
        bootstrap_token: Initial API token (auto-generated if None)

    Returns:
        AuthentikCredentials instance
    """
    return AuthentikCredentials(
        secret_key=secret_key or generate_django_secret_key(),
        postgres_password=postgres_password or generate_secure_password(),
        bootstrap_password=bootstrap_password or generate_secure_password(),
        bootstrap_token=bootstrap_token or generate_api_token(),
    )


def create_cloudflare_config(api_token: str, email: str, zone_id: str) -> CloudflareConfig:
    """Create Cloudflare configuration.

    Args:
        api_token: Cloudflare API token with DNS edit permissions
        email: Cloudflare account email
        zone_id: Zone ID for the domain

    Returns:
        CloudflareConfig instance
    """
    return CloudflareConfig(api_token=api_token, email=email, zone_id=zone_id)
