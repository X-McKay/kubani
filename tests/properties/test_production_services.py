"""Property-based tests for production services deployment.

This module contains property-based tests for the production services
deployment system, including SOPS encryption, age key management,
and service manifest generation.
"""

import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from cluster_manager.secrets import (
    AgeKeyPair,
    generate_age_key,
    is_valid_age_private_key,
    is_valid_age_public_key,
)


@settings(max_examples=100, deadline=None)
@given(st.data())
def test_property_1_age_key_generation_produces_valid_format(data):
    """
    Feature: production-services-deployment, Property 1: Age key generation produces valid format

    For any generated age key pair, the public key should start with "age1" and the private key
    should start with "AGE-SECRET-KEY-1", and both should be valid base64-encoded strings of the
    correct length.

    Validates: Requirements 2.1
    """
    # Generate an age key pair
    key_pair = generate_age_key()

    # Verify the key pair is an AgeKeyPair instance
    assert isinstance(key_pair, AgeKeyPair)

    # Verify public key format
    assert key_pair.public_key.startswith(
        "age1"
    ), f"Public key should start with 'age1', got: {key_pair.public_key[:10]}"
    assert is_valid_age_public_key(
        key_pair.public_key
    ), f"Public key has invalid format: {key_pair.public_key}"

    # Verify private key format
    assert key_pair.private_key.startswith(
        "AGE-SECRET-KEY-1"
    ), f"Private key should start with 'AGE-SECRET-KEY-1', got: {key_pair.private_key[:20]}"
    assert is_valid_age_private_key(
        key_pair.private_key
    ), f"Private key has invalid format: {key_pair.private_key}"

    # Verify keys are not empty after prefix
    assert len(key_pair.public_key) > 4, "Public key should have data after 'age1' prefix"
    assert (
        len(key_pair.private_key) > 16
    ), "Private key should have data after 'AGE-SECRET-KEY-1' prefix"

    # Verify created_at timestamp exists
    assert key_pair.created_at is not None

    # Verify the key pair can be converted to Kubernetes secret format
    k8s_secret = key_pair.to_kubernetes_secret()
    assert k8s_secret["apiVersion"] == "v1"
    assert k8s_secret["kind"] == "Secret"
    assert k8s_secret["metadata"]["name"] == "sops-age"
    assert k8s_secret["metadata"]["namespace"] == "flux-system"
    assert k8s_secret["type"] == "Opaque"
    assert "age.agekey" in k8s_secret["stringData"]
    assert k8s_secret["stringData"]["age.agekey"] == key_pair.private_key

    # Verify the Kubernetes secret is valid YAML
    yaml_output = yaml.dump(k8s_secret)
    parsed = yaml.safe_load(yaml_output)
    assert parsed["kind"] == "Secret"


# Test with known valid age key formats
@st.composite
def valid_age_public_key_strategy(draw):
    """Generate valid age public key strings for testing."""
    # Age public keys use bech32 encoding (specific character set)
    bech32_chars = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    # Age public keys are typically 59 characters after the "age1" prefix
    key_length = draw(st.integers(min_value=50, max_value=70))
    key_data = "".join(
        draw(st.lists(st.sampled_from(bech32_chars), min_size=key_length, max_size=key_length))
    )
    return f"age1{key_data}"


@st.composite
def valid_age_private_key_strategy(draw):
    """Generate valid age private key strings for testing."""
    # Age private keys use bech32 encoding (uppercase)
    bech32_chars = "QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L"
    # Age private keys are typically 58 characters after the "AGE-SECRET-KEY-1" prefix
    key_length = draw(st.integers(min_value=50, max_value=70))
    key_data = "".join(
        draw(st.lists(st.sampled_from(bech32_chars), min_size=key_length, max_size=key_length))
    )
    return f"AGE-SECRET-KEY-1{key_data}"


@given(public_key=valid_age_public_key_strategy())
def test_valid_age_public_key_format(public_key):
    """Valid age public keys should pass validation."""
    assert is_valid_age_public_key(public_key)


@given(private_key=valid_age_private_key_strategy())
def test_valid_age_private_key_format(private_key):
    """Valid age private keys should pass validation."""
    assert is_valid_age_private_key(private_key)


@given(key=st.text().filter(lambda x: not x.startswith("age1")))
def test_invalid_public_key_prefix_rejected(key):
    """Public keys without 'age1' prefix should be rejected."""
    assert not is_valid_age_public_key(key)


@given(key=st.text().filter(lambda x: not x.startswith("AGE-SECRET-KEY-1")))
def test_invalid_private_key_prefix_rejected(key):
    """Private keys without 'AGE-SECRET-KEY-1' prefix should be rejected."""
    assert not is_valid_age_private_key(key)


# Strategy for generating Kubernetes secret manifests
@st.composite
def kubernetes_secret_strategy(draw):
    """Generate valid Kubernetes secret manifests for testing."""
    # Generate random secret name
    name = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
            min_size=3,
            max_size=20,
        ).filter(lambda x: x[0].isalnum() and x[-1].isalnum())
    )

    # Generate random namespace
    namespace = draw(
        st.sampled_from(["default", "kube-system", "flux-system", "database", "cache", "auth"])
    )

    # Generate random secret data
    num_keys = draw(st.integers(min_value=1, max_value=5))
    secret_data = {}
    for _ in range(num_keys):
        key = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_."
                ),
                min_size=1,
                max_size=20,
            ).filter(lambda x: x[0].isalnum())
        )
        value = draw(st.text(min_size=1, max_size=50))
        secret_data[key] = value

    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name, "namespace": namespace},
        "type": "Opaque",
        "stringData": secret_data,
    }


@settings(max_examples=100, deadline=None)
@given(secret=kubernetes_secret_strategy())
def test_property_3_sops_encryption_preserves_metadata_readability(secret):
    """
    Feature: production-services-deployment, Property 3: SOPS encryption preserves metadata readability

    For any Kubernetes secret manifest, after SOPS encryption, the metadata fields
    (apiVersion, kind, metadata.name, metadata.namespace) should remain unencrypted and readable,
    while data/stringData fields should be encrypted.

    Validates: Requirements 2.4
    """
    from cluster_manager.secrets import decrypt_secret_with_sops, encrypt_secret_with_sops

    # Generate an age key pair for testing
    key_pair = generate_age_key()

    # Encrypt the secret
    encrypted = encrypt_secret_with_sops(secret, key_pair.public_key)

    # Verify metadata fields remain unencrypted and readable
    assert encrypted["apiVersion"] == secret["apiVersion"], "apiVersion should remain unencrypted"
    assert encrypted["kind"] == secret["kind"], "kind should remain unencrypted"
    assert (
        encrypted["metadata"]["name"] == secret["metadata"]["name"]
    ), "metadata.name should remain unencrypted"
    assert (
        encrypted["metadata"]["namespace"] == secret["metadata"]["namespace"]
    ), "metadata.namespace should remain unencrypted"

    # Verify SOPS metadata is present
    assert "sops" in encrypted, "Encrypted manifest should contain SOPS metadata"
    assert "age" in encrypted["sops"], "SOPS metadata should contain age information"

    # Verify stringData is encrypted (should be converted to data and encrypted)
    # SOPS converts stringData to data during encryption
    if "data" in encrypted:
        # Check that at least one value is encrypted (contains "ENC[" marker or is not plain text)
        for key, value in encrypted["data"].items():
            # Encrypted values should be different from original
            if key in secret["stringData"]:
                assert value != secret["stringData"][key], f"Data field '{key}' should be encrypted"

    # Verify round-trip: decrypt and compare with original
    decrypted = decrypt_secret_with_sops(encrypted, key_pair.private_key)

    # After decryption, metadata should still match
    assert decrypted["apiVersion"] == secret["apiVersion"]
    assert decrypted["kind"] == secret["kind"]
    assert decrypted["metadata"]["name"] == secret["metadata"]["name"]
    assert decrypted["metadata"]["namespace"] == secret["metadata"]["namespace"]

    # Decrypted data should match original stringData
    # SOPS may convert stringData to data, so check both
    if "stringData" in decrypted:
        for key, value in secret["stringData"].items():
            assert (
                decrypted["stringData"][key] == value
            ), f"Decrypted stringData['{key}'] should match original"
    elif "data" in decrypted:
        # Data is base64 encoded, decode and compare
        import base64

        for key, value in secret["stringData"].items():
            decoded = base64.b64decode(decrypted["data"][key]).decode("utf-8")
            assert decoded == value, f"Decrypted data['{key}'] should match original"


# Strategies for generating service credentials
@st.composite
def postgresql_credentials_strategy(draw):
    """Generate random PostgreSQL credentials for testing."""
    from cluster_manager.secrets import PostgreSQLCredentials

    # Generate random database name (lowercase alphanumeric)
    database = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Nd")), min_size=3, max_size=20
        ).filter(lambda x: x and x[0].isalpha())
    )

    # Generate random username (lowercase alphanumeric)
    username = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Nd")), min_size=3, max_size=20
        ).filter(lambda x: x and x[0].isalpha())
    )

    # Generate random passwords
    postgres_password = draw(st.text(min_size=8, max_size=64))
    password = draw(st.text(min_size=8, max_size=64))

    return PostgreSQLCredentials(
        postgres_password=postgres_password, username=username, password=password, database=database
    )


@st.composite
def redis_credentials_strategy(draw):
    """Generate random Redis credentials for testing."""
    from cluster_manager.secrets import RedisCredentials

    password = draw(st.text(min_size=8, max_size=64))
    return RedisCredentials(password=password)


@st.composite
def authentik_credentials_strategy(draw):
    """Generate random Authentik credentials for testing."""
    from cluster_manager.secrets import AuthentikCredentials

    secret_key = draw(st.text(min_size=20, max_size=100))
    postgres_password = draw(st.text(min_size=8, max_size=64))
    bootstrap_password = draw(st.text(min_size=8, max_size=64))
    bootstrap_token = draw(st.text(min_size=16, max_size=128))

    return AuthentikCredentials(
        secret_key=secret_key,
        postgres_password=postgres_password,
        bootstrap_password=bootstrap_password,
        bootstrap_token=bootstrap_token,
    )


@st.composite
def cloudflare_config_strategy(draw):
    """Generate random Cloudflare configuration for testing."""
    from cluster_manager.secrets import CloudflareConfig

    # Generate random API token (hex string)
    api_token = draw(
        st.text(alphabet=st.characters(whitelist_categories=("Ll", "Nd")), min_size=32, max_size=64)
    )

    # Generate random email
    email_local = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Nd")), min_size=3, max_size=20
        ).filter(lambda x: x and x[0].isalpha())
    )
    email = f"{email_local}@example.com"

    # Generate random zone ID
    zone_id = draw(
        st.text(alphabet=st.characters(whitelist_categories=("Ll", "Nd")), min_size=32, max_size=32)
    )

    return CloudflareConfig(api_token=api_token, email=email, zone_id=zone_id)


@settings(max_examples=100, deadline=None)
@given(
    credentials=st.one_of(
        postgresql_credentials_strategy(),
        redis_credentials_strategy(),
        authentik_credentials_strategy(),
        cloudflare_config_strategy(),
    )
)
def test_property_2_secret_templates_produce_valid_kubernetes_manifests(credentials):
    """
    Feature: production-services-deployment, Property 2: Secret templates produce valid Kubernetes manifests

    For any valid credentials (PostgreSQL, Redis, Authentik, Cloudflare), the corresponding template
    function should produce a Kubernetes Secret manifest that passes kubectl validation and contains
    all required fields (apiVersion, kind, metadata, type, stringData).

    Validates: Requirements 2.3
    """
    from cluster_manager.secrets import (
        AuthentikCredentials,
        CloudflareConfig,
        PostgreSQLCredentials,
        RedisCredentials,
    )

    # Generate the secret manifest
    manifest = credentials.to_secret_manifest()

    # Verify all required Kubernetes Secret fields are present
    assert "apiVersion" in manifest, "Manifest must have apiVersion field"
    assert manifest["apiVersion"] == "v1", "apiVersion must be 'v1' for Secret"

    assert "kind" in manifest, "Manifest must have kind field"
    assert manifest["kind"] == "Secret", "kind must be 'Secret'"

    assert "metadata" in manifest, "Manifest must have metadata field"
    assert isinstance(manifest["metadata"], dict), "metadata must be a dictionary"

    assert "name" in manifest["metadata"], "metadata must have name field"
    assert isinstance(manifest["metadata"]["name"], str), "metadata.name must be a string"
    assert len(manifest["metadata"]["name"]) > 0, "metadata.name cannot be empty"

    assert "namespace" in manifest["metadata"], "metadata must have namespace field"
    assert isinstance(manifest["metadata"]["namespace"], str), "metadata.namespace must be a string"
    assert len(manifest["metadata"]["namespace"]) > 0, "metadata.namespace cannot be empty"

    assert "type" in manifest, "Manifest must have type field"
    assert manifest["type"] == "Opaque", "type must be 'Opaque' for generic secrets"

    assert "stringData" in manifest, "Manifest must have stringData field"
    assert isinstance(manifest["stringData"], dict), "stringData must be a dictionary"
    assert len(manifest["stringData"]) > 0, "stringData cannot be empty"

    # Verify stringData values are all strings
    for key, value in manifest["stringData"].items():
        assert isinstance(key, str), f"stringData key must be string, got {type(key)}"
        assert isinstance(
            value, str
        ), f"stringData value for '{key}' must be string, got {type(value)}"
        assert len(value) > 0, f"stringData value for '{key}' cannot be empty"

    # Verify the manifest can be serialized to YAML
    yaml_output = yaml.dump(manifest)
    assert yaml_output, "Manifest should be serializable to YAML"

    # Verify the YAML can be parsed back
    parsed = yaml.safe_load(yaml_output)
    assert parsed["kind"] == "Secret", "Parsed manifest should still be a Secret"
    assert parsed["apiVersion"] == "v1", "Parsed manifest should have correct apiVersion"

    # Verify service-specific requirements
    if isinstance(credentials, PostgreSQLCredentials):
        assert manifest["metadata"]["name"] == "postgresql-credentials"
        assert manifest["metadata"]["namespace"] == "database"
        assert "postgres-password" in manifest["stringData"]
        assert "username" in manifest["stringData"]
        assert "password" in manifest["stringData"]
        assert "database" in manifest["stringData"]
        # Verify the values match the credentials
        assert manifest["stringData"]["postgres-password"] == credentials.postgres_password
        assert manifest["stringData"]["username"] == credentials.username
        assert manifest["stringData"]["password"] == credentials.password
        assert manifest["stringData"]["database"] == credentials.database

    elif isinstance(credentials, RedisCredentials):
        assert manifest["metadata"]["name"] == "redis-credentials"
        assert manifest["metadata"]["namespace"] == "cache"
        assert "redis-password" in manifest["stringData"]
        # Verify the value matches the credentials
        assert manifest["stringData"]["redis-password"] == credentials.password

    elif isinstance(credentials, AuthentikCredentials):
        assert manifest["metadata"]["name"] == "authentik-credentials"
        assert manifest["metadata"]["namespace"] == "auth"
        assert "secret-key" in manifest["stringData"]
        assert "postgres-password" in manifest["stringData"]
        assert "bootstrap-password" in manifest["stringData"]
        assert "bootstrap-token" in manifest["stringData"]
        # Verify the values match the credentials
        assert manifest["stringData"]["secret-key"] == credentials.secret_key
        assert manifest["stringData"]["postgres-password"] == credentials.postgres_password
        assert manifest["stringData"]["bootstrap-password"] == credentials.bootstrap_password
        assert manifest["stringData"]["bootstrap-token"] == credentials.bootstrap_token

    elif isinstance(credentials, CloudflareConfig):
        assert manifest["metadata"]["name"] == "cloudflare-api-token"
        assert manifest["metadata"]["namespace"] == "cert-manager"
        assert "api-token" in manifest["stringData"]
        # Verify the value matches the credentials
        assert manifest["stringData"]["api-token"] == credentials.api_token


# Test credential generation utilities
def test_generated_postgresql_credentials_produce_valid_manifests():
    """Test that auto-generated PostgreSQL credentials produce valid manifests."""
    from cluster_manager.secrets import create_postgresql_credentials

    creds = create_postgresql_credentials(database="testdb", username="testuser")
    manifest = creds.to_secret_manifest()

    assert manifest["kind"] == "Secret"
    assert manifest["metadata"]["name"] == "postgresql-credentials"
    assert len(creds.postgres_password) >= 8
    assert len(creds.password) >= 8


def test_generated_redis_credentials_produce_valid_manifests():
    """Test that auto-generated Redis credentials produce valid manifests."""
    from cluster_manager.secrets import create_redis_credentials

    creds = create_redis_credentials()
    manifest = creds.to_secret_manifest()

    assert manifest["kind"] == "Secret"
    assert manifest["metadata"]["name"] == "redis-credentials"
    assert len(creds.password) >= 8


def test_generated_authentik_credentials_produce_valid_manifests():
    """Test that auto-generated Authentik credentials produce valid manifests."""
    from cluster_manager.secrets import create_authentik_credentials

    creds = create_authentik_credentials()
    manifest = creds.to_secret_manifest()

    assert manifest["kind"] == "Secret"
    assert manifest["metadata"]["name"] == "authentik-credentials"
    assert len(creds.secret_key) >= 20
    assert len(creds.postgres_password) >= 8
    assert len(creds.bootstrap_password) >= 8
    assert len(creds.bootstrap_token) >= 16


def test_cloudflare_config_produces_valid_manifest():
    """Test that Cloudflare config produces valid manifest."""
    from cluster_manager.secrets import create_cloudflare_config

    config = create_cloudflare_config(
        api_token="test_token_12345", email="test@example.com", zone_id="abc123def456"
    )
    manifest = config.to_secret_manifest()

    assert manifest["kind"] == "Secret"
    assert manifest["metadata"]["name"] == "cloudflare-api-token"
    assert manifest["stringData"]["api-token"] == "test_token_12345"
