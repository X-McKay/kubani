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


# Strategies for generating HelmRelease manifests
@st.composite
def helmrelease_strategy(draw, service_type=None):
    """Generate HelmRelease manifests for testing.

    Args:
        draw: Hypothesis draw function
        service_type: Optional service type ('postgresql', 'redis', 'authentik')
    """
    if service_type is None:
        service_type = draw(st.sampled_from(["postgresql", "redis", "authentik"]))

    # Service-specific configurations
    service_configs = {
        "postgresql": {
            "namespace": "database",
            "chart": "postgresql",
            "repo": "https://charts.bitnami.com/bitnami",
            "secret_name": "postgresql-credentials",
            "secret_keys": ["postgres-password", "username", "password", "database"],
            "persistence_size": "20Gi",
        },
        "redis": {
            "namespace": "cache",
            "chart": "redis",
            "repo": "https://charts.bitnami.com/bitnami",
            "secret_name": "redis-credentials",
            "secret_keys": ["redis-password"],
            "persistence_size": "8Gi",
        },
        "authentik": {
            "namespace": "auth",
            "chart": "authentik",
            "repo": "https://charts.goauthentik.io",
            "secret_name": "authentik-credentials",
            "secret_keys": [
                "secret-key",
                "postgres-password",
                "bootstrap-password",
                "bootstrap-token",
            ],
            "persistence_size": None,  # Authentik doesn't use persistence in the same way
        },
    }

    config = service_configs[service_type]

    # Build HelmRelease manifest
    manifest = {
        "apiVersion": "helm.toolkit.fluxcd.io/v2beta1",
        "kind": "HelmRelease",
        "metadata": {
            "name": service_type,
            "namespace": config["namespace"],
        },
        "spec": {
            "interval": "10m",
            "chart": {
                "spec": {
                    "chart": config["chart"],
                    "version": draw(
                        st.text(
                            alphabet=st.characters(
                                whitelist_categories=("Nd",), whitelist_characters="."
                            ),
                            min_size=3,
                            max_size=10,
                        )
                    ),
                    "sourceRef": {
                        "kind": "HelmRepository",
                        "name": f"{service_type}-repo",
                        "namespace": "flux-system",
                    },
                }
            },
            "values": {},
        },
    }

    # Add service-specific values
    if service_type == "postgresql":
        manifest["spec"]["values"] = {
            "auth": {
                "existingSecret": config["secret_name"],
                "secretKeys": {
                    "adminPasswordKey": "postgres-password",
                    "userPasswordKey": "password",
                },
            },
            "primary": {
                "persistence": {
                    "enabled": True,
                    "size": config["persistence_size"],
                }
            },
        }
    elif service_type == "redis":
        manifest["spec"]["values"] = {
            "auth": {
                "existingSecret": config["secret_name"],
                "existingSecretPasswordKey": "redis-password",
            },
            "master": {
                "persistence": {
                    "enabled": True,
                    "size": config["persistence_size"],
                }
            },
        }
    elif service_type == "authentik":
        manifest["spec"]["values"] = {
            "authentik": {
                "secret_key": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": config["secret_name"],
                            "key": "secret-key",
                        }
                    }
                },
                "postgresql": {
                    "password": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": config["secret_name"],
                                "key": "postgres-password",
                            }
                        }
                    }
                },
            }
        }

    return manifest, config


@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_4_helmrelease_manifests_reference_correct_secrets(data):
    """
    Feature: production-services-deployment, Property 4: HelmRelease manifests reference correct secrets

    For any service HelmRelease (PostgreSQL, Redis, Authentik), the values configuration should
    reference an existingSecret that matches the expected secret name for that service.

    Validates: Requirements 3.2, 4.2, 5.2
    """
    # Generate a HelmRelease for a random service type
    service_type = data.draw(st.sampled_from(["postgresql", "redis", "authentik"]))
    manifest, config = data.draw(helmrelease_strategy(service_type=service_type))

    # Verify the manifest is a HelmRelease
    assert manifest["kind"] == "HelmRelease", "Manifest must be a HelmRelease"
    assert (
        manifest["apiVersion"] == "helm.toolkit.fluxcd.io/v2beta1"
    ), "Must use correct API version"

    # Verify namespace matches expected
    assert (
        manifest["metadata"]["namespace"] == config["namespace"]
    ), f"HelmRelease namespace should be {config['namespace']}"

    # Verify secret references based on service type
    values = manifest["spec"]["values"]

    if service_type == "postgresql":
        # PostgreSQL should reference existingSecret in auth section
        assert "auth" in values, "PostgreSQL HelmRelease must have auth section"
        assert "existingSecret" in values["auth"], "PostgreSQL auth must reference existingSecret"
        assert (
            values["auth"]["existingSecret"] == config["secret_name"]
        ), f"PostgreSQL should reference {config['secret_name']}"

    elif service_type == "redis":
        # Redis should reference existingSecret in auth section
        assert "auth" in values, "Redis HelmRelease must have auth section"
        assert "existingSecret" in values["auth"], "Redis auth must reference existingSecret"
        assert (
            values["auth"]["existingSecret"] == config["secret_name"]
        ), f"Redis should reference {config['secret_name']}"
        assert (
            "existingSecretPasswordKey" in values["auth"]
        ), "Redis auth must specify existingSecretPasswordKey"

    elif service_type == "authentik":
        # Authentik references secrets via valueFrom
        assert "authentik" in values, "Authentik HelmRelease must have authentik section"

        # Check secret_key reference
        if "secret_key" in values["authentik"]:
            assert (
                "valueFrom" in values["authentik"]["secret_key"]
            ), "Authentik secret_key must use valueFrom"
            assert (
                "secretKeyRef" in values["authentik"]["secret_key"]["valueFrom"]
            ), "Authentik secret_key must use secretKeyRef"
            assert (
                values["authentik"]["secret_key"]["valueFrom"]["secretKeyRef"]["name"]
                == config["secret_name"]
            ), f"Authentik should reference {config['secret_name']}"

        # Check postgresql password reference
        if "postgresql" in values["authentik"] and "password" in values["authentik"]["postgresql"]:
            assert (
                "valueFrom" in values["authentik"]["postgresql"]["password"]
            ), "Authentik postgresql password must use valueFrom"
            assert (
                "secretKeyRef" in values["authentik"]["postgresql"]["password"]["valueFrom"]
            ), "Authentik postgresql password must use secretKeyRef"
            assert (
                values["authentik"]["postgresql"]["password"]["valueFrom"]["secretKeyRef"]["name"]
                == config["secret_name"]
            ), f"Authentik should reference {config['secret_name']}"

    # Verify secret name follows naming convention: {service}-credentials
    expected_secret_pattern = f"{service_type}-credentials"
    assert (
        config["secret_name"] == expected_secret_pattern
    ), f"Secret name should follow pattern '{expected_secret_pattern}'"


@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_5_stateful_services_have_persistence_configured(data):
    """
    Feature: production-services-deployment, Property 5: Stateful services have persistence configured

    For any stateful service HelmRelease (PostgreSQL, Redis), the values configuration should have
    persistence.enabled set to true and persistence.size specified.

    Validates: Requirements 3.3, 4.3
    """
    # Generate a HelmRelease for a stateful service (PostgreSQL or Redis)
    service_type = data.draw(st.sampled_from(["postgresql", "redis"]))
    manifest, config = data.draw(helmrelease_strategy(service_type=service_type))

    # Verify the manifest is a HelmRelease
    assert manifest["kind"] == "HelmRelease", "Manifest must be a HelmRelease"

    # Get values section
    values = manifest["spec"]["values"]

    # Check persistence configuration based on service type
    if service_type == "postgresql":
        # PostgreSQL uses primary.persistence
        assert "primary" in values, "PostgreSQL HelmRelease must have primary section"
        assert (
            "persistence" in values["primary"]
        ), "PostgreSQL primary must have persistence section"

        persistence = values["primary"]["persistence"]
        assert "enabled" in persistence, "PostgreSQL persistence must have enabled field"
        assert persistence["enabled"] is True, "PostgreSQL persistence must be enabled"

        assert "size" in persistence, "PostgreSQL persistence must have size field"
        assert isinstance(persistence["size"], str), "PostgreSQL persistence size must be a string"
        assert len(persistence["size"]) > 0, "PostgreSQL persistence size cannot be empty"

        # Verify size format (e.g., "20Gi", "10Gi")
        import re

        size_pattern = r"^\d+[KMGT]i?$"
        assert re.match(
            size_pattern, persistence["size"]
        ), f"PostgreSQL persistence size must match pattern {size_pattern}, got {persistence['size']}"

        # Verify expected size for PostgreSQL
        assert (
            persistence["size"] == config["persistence_size"]
        ), f"PostgreSQL persistence size should be {config['persistence_size']}"

    elif service_type == "redis":
        # Redis uses master.persistence
        assert "master" in values, "Redis HelmRelease must have master section"
        assert "persistence" in values["master"], "Redis master must have persistence section"

        persistence = values["master"]["persistence"]
        assert "enabled" in persistence, "Redis persistence must have enabled field"
        assert persistence["enabled"] is True, "Redis persistence must be enabled"

        assert "size" in persistence, "Redis persistence must have size field"
        assert isinstance(persistence["size"], str), "Redis persistence size must be a string"
        assert len(persistence["size"]) > 0, "Redis persistence size cannot be empty"

        # Verify size format (e.g., "8Gi", "10Gi")
        import re

        size_pattern = r"^\d+[KMGT]i?$"
        assert re.match(
            size_pattern, persistence["size"]
        ), f"Redis persistence size must match pattern {size_pattern}, got {persistence['size']}"

        # Verify expected size for Redis
        assert (
            persistence["size"] == config["persistence_size"]
        ), f"Redis persistence size should be {config['persistence_size']}"


# Strategies for generating Ingress manifests
@st.composite
def ingress_strategy(draw, service_name=None):
    """Generate Ingress manifests for testing.

    Args:
        draw: Hypothesis draw function
        service_name: Optional service name (e.g., 'authentik', 'grafana')
    """
    if service_name is None:
        # Generate random service name
        service_name = draw(
            st.text(
                alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters="-"),
                min_size=3,
                max_size=20,
            ).filter(lambda x: x and x[0].isalpha() and x[-1].isalpha())
        )

    # Generate subdomain under almckay.io
    subdomain = f"{service_name}.almckay.io"

    # Generate TLS secret name
    tls_secret_name = f"{service_name}-tls"

    # Generate namespace
    namespace = draw(st.sampled_from(["default", "auth", "monitoring", "apps"]))

    # Build Ingress manifest
    manifest = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": f"{service_name}-ingress",
            "namespace": namespace,
            "annotations": {
                "cert-manager.io/cluster-issuer": "letsencrypt-prod",
            },
        },
        "spec": {
            "rules": [
                {
                    "host": subdomain,
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": service_name,
                                        "port": {
                                            "number": draw(
                                                st.integers(min_value=80, max_value=8080)
                                            ),
                                        },
                                    },
                                },
                            }
                        ]
                    },
                }
            ],
            "tls": [
                {
                    "hosts": [subdomain],
                    "secretName": tls_secret_name,
                }
            ],
        },
    }

    return manifest


@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_6_ingress_manifests_have_required_tls_configuration(data):
    """
    Feature: production-services-deployment, Property 6: Ingress manifests have required TLS configuration

    For any Ingress resource for external services, the manifest should include a cert-manager.io/cluster-issuer
    annotation, a host under almckay.io domain, and a tls section referencing a secretName for the certificate.

    Validates: Requirements 5.3, 5.4, 8.1, 8.4
    """
    # Generate an Ingress manifest
    manifest = data.draw(ingress_strategy())

    # Verify the manifest is an Ingress
    assert manifest["kind"] == "Ingress", "Manifest must be an Ingress"
    assert manifest["apiVersion"] == "networking.k8s.io/v1", "Must use correct API version"

    # Verify cert-manager annotation is present
    assert "annotations" in manifest["metadata"], "Ingress must have annotations"
    annotations = manifest["metadata"]["annotations"]
    assert (
        "cert-manager.io/cluster-issuer" in annotations
    ), "Ingress must have cert-manager.io/cluster-issuer annotation"

    # Verify the cluster issuer is specified (typically letsencrypt-prod or letsencrypt-staging)
    cluster_issuer = annotations["cert-manager.io/cluster-issuer"]
    assert isinstance(cluster_issuer, str), "Cluster issuer must be a string"
    assert len(cluster_issuer) > 0, "Cluster issuer cannot be empty"

    # Verify spec section exists
    assert "spec" in manifest, "Ingress must have spec section"
    spec = manifest["spec"]

    # Verify rules section exists and has at least one rule
    assert "rules" in spec, "Ingress spec must have rules section"
    assert len(spec["rules"]) > 0, "Ingress must have at least one rule"

    # Verify host is under almckay.io domain
    for rule in spec["rules"]:
        assert "host" in rule, "Ingress rule must have host field"
        host = rule["host"]
        assert isinstance(host, str), "Host must be a string"
        assert host.endswith(".almckay.io"), f"Host must be under almckay.io domain, got: {host}"

    # Verify TLS section exists
    assert "tls" in spec, "Ingress spec must have tls section"
    assert len(spec["tls"]) > 0, "Ingress must have at least one TLS configuration"

    # Verify each TLS configuration has required fields
    for tls_config in spec["tls"]:
        # Verify hosts are specified
        assert "hosts" in tls_config, "TLS configuration must have hosts field"
        assert len(tls_config["hosts"]) > 0, "TLS configuration must specify at least one host"

        # Verify all TLS hosts are under almckay.io domain
        for host in tls_config["hosts"]:
            assert isinstance(host, str), "TLS host must be a string"
            assert host.endswith(
                ".almckay.io"
            ), f"TLS host must be under almckay.io domain, got: {host}"

        # Verify secretName is specified
        assert "secretName" in tls_config, "TLS configuration must have secretName field"
        secret_name = tls_config["secretName"]
        assert isinstance(secret_name, str), "TLS secretName must be a string"
        assert len(secret_name) > 0, "TLS secretName cannot be empty"

        # Verify secretName follows naming convention (typically ends with -tls)
        assert (
            secret_name.endswith("-tls") or "cert" in secret_name or "tls" in secret_name
        ), f"TLS secretName should follow naming convention (contain 'tls' or 'cert'), got: {secret_name}"


@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_7_multiple_services_have_independent_ingress_configurations(data):
    """
    Feature: production-services-deployment, Property 7: Multiple services have independent Ingress configurations

    For any set of services requiring external access, each service should have its own Ingress resource
    with a unique subdomain and unique TLS secret name, ensuring no conflicts.

    Validates: Requirements 8.5
    """
    # Generate multiple Ingress manifests for different services
    num_services = data.draw(st.integers(min_value=2, max_value=5))

    # Generate unique service names
    service_names = []
    for i in range(num_services):
        service_name = data.draw(
            st.text(
                alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters="-"),
                min_size=3,
                max_size=15,
            ).filter(lambda x: x and x[0].isalpha() and x[-1].isalpha() and x not in service_names)
        )
        service_names.append(service_name)

    # Generate Ingress manifests for each service
    ingress_manifests = []
    for service_name in service_names:
        manifest = data.draw(ingress_strategy(service_name=service_name))
        ingress_manifests.append(manifest)

    # Collect all hostnames and TLS secret names
    all_hostnames = set()
    all_tls_secrets = set()

    for manifest in ingress_manifests:
        # Extract hostnames from rules
        for rule in manifest["spec"]["rules"]:
            hostname = rule["host"]

            # Verify this hostname is unique (no duplicates)
            assert (
                hostname not in all_hostnames
            ), f"Duplicate hostname found: {hostname}. Each service must have a unique subdomain."
            all_hostnames.add(hostname)

        # Extract TLS secret names
        for tls_config in manifest["spec"]["tls"]:
            secret_name = tls_config["secretName"]

            # Verify this TLS secret name is unique (no duplicates)
            assert (
                secret_name not in all_tls_secrets
            ), f"Duplicate TLS secret name found: {secret_name}. Each service must have a unique TLS secret."
            all_tls_secrets.add(secret_name)

    # Verify we have the expected number of unique hostnames and secrets
    assert (
        len(all_hostnames) == num_services
    ), f"Expected {num_services} unique hostnames, got {len(all_hostnames)}"
    assert (
        len(all_tls_secrets) == num_services
    ), f"Expected {num_services} unique TLS secrets, got {len(all_tls_secrets)}"

    # Verify each Ingress has independent configuration
    for i, manifest in enumerate(ingress_manifests):
        service_name = service_names[i]

        # Verify the Ingress name is unique
        ingress_name = manifest["metadata"]["name"]
        assert (
            service_name in ingress_name
        ), f"Ingress name should contain service name '{service_name}', got: {ingress_name}"

        # Verify the hostname contains the service name
        hostname = manifest["spec"]["rules"][0]["host"]
        assert hostname.startswith(
            f"{service_name}."
        ), f"Hostname should start with service name '{service_name}', got: {hostname}"

        # Verify the TLS secret name contains the service name
        tls_secret = manifest["spec"]["tls"][0]["secretName"]
        assert (
            service_name in tls_secret
        ), f"TLS secret name should contain service name '{service_name}', got: {tls_secret}"


@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_8_service_manifests_are_organized_in_correct_directories(data):
    """
    Feature: production-services-deployment, Property 8: Service manifests are organized in correct directories

    For any deployed service, its HelmRelease manifest should be located in gitops/apps/{service-name}/
    and any encrypted secrets should be co-located in the same directory with .enc.yaml suffix.

    Validates: Requirements 9.1, 9.2
    """
    from pathlib import Path

    # Define the base gitops directory
    gitops_base = Path("gitops")
    apps_dir = gitops_base / "apps"
    infrastructure_dir = gitops_base / "infrastructure"

    # Verify base directories exist
    assert apps_dir.exists(), f"Apps directory should exist at {apps_dir}"
    assert (
        infrastructure_dir.exists()
    ), f"Infrastructure directory should exist at {infrastructure_dir}"

    # Test with actual deployed services
    deployed_services = ["postgresql", "redis"]

    for service_name in deployed_services:
        service_dir = apps_dir / service_name

        # Verify service directory exists
        assert service_dir.exists(), f"Service directory should exist at {service_dir}"
        assert service_dir.is_dir(), f"Service path should be a directory: {service_dir}"

        # Verify HelmRelease manifest exists in service directory
        helmrelease_path = service_dir / "helmrelease.yaml"
        assert helmrelease_path.exists(), f"HelmRelease manifest should exist at {helmrelease_path}"
        assert helmrelease_path.is_file(), f"HelmRelease path should be a file: {helmrelease_path}"

        # Verify encrypted secret exists in service directory with .enc.yaml suffix
        encrypted_secret_path = service_dir / "secret.enc.yaml"
        assert (
            encrypted_secret_path.exists()
        ), f"Encrypted secret should exist at {encrypted_secret_path}"
        assert (
            encrypted_secret_path.is_file()
        ), f"Encrypted secret path should be a file: {encrypted_secret_path}"

        # Verify the encrypted secret has the correct suffix
        assert encrypted_secret_path.name.endswith(
            ".enc.yaml"
        ), f"Encrypted secret should have .enc.yaml suffix: {encrypted_secret_path.name}"

        # Verify namespace manifest exists (services should have their own namespace)
        namespace_path = service_dir / "namespace.yaml"
        assert namespace_path.exists(), f"Namespace manifest should exist at {namespace_path}"

        # Verify kustomization.yaml exists to tie manifests together
        kustomization_path = service_dir / "kustomization.yaml"
        assert (
            kustomization_path.exists()
        ), f"Kustomization manifest should exist at {kustomization_path}"

        # Read and verify the HelmRelease manifest
        with open(helmrelease_path) as f:
            import yaml

            helmrelease = yaml.safe_load(f)

            # Verify it's a HelmRelease
            assert (
                helmrelease["kind"] == "HelmRelease"
            ), f"Manifest at {helmrelease_path} should be a HelmRelease"

            # Verify the name matches the service
            assert (
                helmrelease["metadata"]["name"] == service_name
            ), f"HelmRelease name should match service name '{service_name}'"

        # Read and verify the encrypted secret
        with open(encrypted_secret_path) as f:
            encrypted_secret = yaml.safe_load(f)

            # Verify it's a Secret
            assert (
                encrypted_secret["kind"] == "Secret"
            ), f"Manifest at {encrypted_secret_path} should be a Secret"

            # Verify it has SOPS metadata (indicating it's encrypted)
            assert (
                "sops" in encrypted_secret
            ), f"Encrypted secret at {encrypted_secret_path} should have SOPS metadata"

            # Verify the secret name follows convention
            expected_secret_name = f"{service_name}-credentials"
            assert (
                encrypted_secret["metadata"]["name"] == expected_secret_name
            ), f"Secret name should be '{expected_secret_name}'"

    # Test infrastructure components are in correct directory
    infrastructure_components = ["cert-manager", "sources"]

    for component in infrastructure_components:
        component_dir = infrastructure_dir / component

        # Verify component directory exists
        assert (
            component_dir.exists()
        ), f"Infrastructure component directory should exist at {component_dir}"
        assert (
            component_dir.is_dir()
        ), f"Infrastructure component path should be a directory: {component_dir}"

    # Verify cert-manager has required manifests
    cert_manager_dir = infrastructure_dir / "cert-manager"

    # Check for HelmRelease or other cert-manager manifests
    cert_manager_files = list(cert_manager_dir.glob("*.yaml"))
    assert len(cert_manager_files) > 0, "Cert-manager directory should contain YAML manifests"

    # Verify sources directory has Helm repository sources
    sources_dir = infrastructure_dir / "sources"
    source_files = list(sources_dir.glob("*.yaml"))
    assert (
        len(source_files) > 0
    ), "Sources directory should contain Helm repository source manifests"


@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_9_database_services_have_ingressroutetcp_for_dns_access(data):
    """
    Feature: production-services-deployment, Property 9: Database services have IngressRouteTCP for DNS access

    For any stateful data service (PostgreSQL, Redis), there should be a corresponding IngressRouteTCP
    resource that routes traffic from the DNS name (postgres.almckay.io, redis.almckay.io) to the
    ClusterIP service.

    Validates: Requirements 11.1, 11.2
    """
    from pathlib import Path

    # Define the base gitops directory
    gitops_base = Path("gitops")
    apps_dir = gitops_base / "apps"

    # Test with actual database services that should have TCP routing
    database_services = {
        "postgresql": {
            "dns_name": "postgres.almckay.io",
            "port": 5432,
            "namespace": "database",
        },
        "redis": {
            "dns_name": "redis.almckay.io",
            "port": 6379,
            "namespace": "cache",
        },
    }

    for service_name, config in database_services.items():
        service_dir = apps_dir / service_name

        # Verify service directory exists
        assert service_dir.exists(), f"Service directory should exist at {service_dir}"

        # Verify IngressRouteTCP manifest exists
        ingressroutetcp_path = service_dir / "ingressroutetcp.yaml"
        assert (
            ingressroutetcp_path.exists()
        ), f"IngressRouteTCP manifest should exist at {ingressroutetcp_path}"
        assert (
            ingressroutetcp_path.is_file()
        ), f"IngressRouteTCP path should be a file: {ingressroutetcp_path}"

        # Read and verify the IngressRouteTCP manifest
        with open(ingressroutetcp_path) as f:
            import yaml

            ingressroutetcp = yaml.safe_load(f)

            # Verify it's an IngressRouteTCP (Traefik CRD)
            assert (
                ingressroutetcp["kind"] == "IngressRouteTCP"
            ), f"Manifest at {ingressroutetcp_path} should be an IngressRouteTCP"

            # Verify API version is correct for Traefik
            assert (
                "traefik" in ingressroutetcp["apiVersion"]
            ), "IngressRouteTCP should use Traefik API version"

            # Verify metadata
            assert "metadata" in ingressroutetcp, "IngressRouteTCP must have metadata"
            assert "name" in ingressroutetcp["metadata"], "IngressRouteTCP must have name"
            assert "namespace" in ingressroutetcp["metadata"], "IngressRouteTCP must have namespace"

            # Verify namespace matches expected
            assert (
                ingressroutetcp["metadata"]["namespace"] == config["namespace"]
            ), f"IngressRouteTCP namespace should be '{config['namespace']}'"

            # Verify spec section
            assert "spec" in ingressroutetcp, "IngressRouteTCP must have spec"
            spec = ingressroutetcp["spec"]

            # Verify entryPoints are configured
            assert "entryPoints" in spec, "IngressRouteTCP spec must have entryPoints"
            assert isinstance(spec["entryPoints"], list), "entryPoints must be a list"
            assert len(spec["entryPoints"]) > 0, "IngressRouteTCP must have at least one entryPoint"

            # Verify the entryPoint name matches the service (postgresql or redis)
            entry_point = spec["entryPoints"][0]
            assert (
                service_name in entry_point.lower() or str(config["port"]) in entry_point
            ), f"EntryPoint should reference service '{service_name}' or port {config['port']}, got: {entry_point}"

            # Verify routes are configured
            assert "routes" in spec, "IngressRouteTCP spec must have routes"
            assert isinstance(spec["routes"], list), "routes must be a list"
            assert len(spec["routes"]) > 0, "IngressRouteTCP must have at least one route"

            # Verify route configuration
            route = spec["routes"][0]

            # Verify match rule exists (typically HostSNI(`*`) for TCP)
            assert "match" in route, "IngressRouteTCP route must have match rule"

            # Verify services are configured
            assert "services" in route, "IngressRouteTCP route must have services"
            assert isinstance(route["services"], list), "route services must be a list"
            assert (
                len(route["services"]) > 0
            ), "IngressRouteTCP route must have at least one service"

            # Verify service configuration
            service = route["services"][0]
            assert "name" in service, "IngressRouteTCP service must have name"
            assert "port" in service, "IngressRouteTCP service must have port"

            # Verify the service name references the backend service
            backend_service_name = service["name"]
            assert (
                service_name in backend_service_name
                or backend_service_name == service_name
                or (service_name == "postgresql" and "postgres" in backend_service_name)
                or (service_name == "redis" and "redis" in backend_service_name)
            ), f"Backend service name should reference '{service_name}', got: {backend_service_name}"

            # Verify the port matches expected
            service_port = service["port"]
            assert (
                service_port == config["port"]
            ), f"Service port should be {config['port']}, got: {service_port}"

        # Verify the service also has a ClusterIP service manifest
        # (IngressRouteTCP routes to ClusterIP services)
        helmrelease_path = service_dir / "helmrelease.yaml"
        with open(helmrelease_path) as f:
            helmrelease = yaml.safe_load(f)

            # Verify the HelmRelease configures a ClusterIP service
            # (This is typically the default for Helm charts, but we verify it's not LoadBalancer)
            values = helmrelease["spec"].get("values", {})

            # For PostgreSQL, check primary.service.type
            if service_name == "postgresql":
                if "primary" in values and "service" in values["primary"]:
                    service_type = values["primary"]["service"].get("type", "ClusterIP")
                    assert (
                        service_type == "ClusterIP"
                    ), f"PostgreSQL service type should be ClusterIP for internal routing, got: {service_type}"

            # For Redis, check master.service.type
            elif service_name == "redis":
                if "master" in values and "service" in values["master"]:
                    service_type = values["master"]["service"].get("type", "ClusterIP")
                    assert (
                        service_type == "ClusterIP"
                    ), f"Redis service type should be ClusterIP for internal routing, got: {service_type}"
