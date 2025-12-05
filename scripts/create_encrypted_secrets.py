#!/usr/bin/env python3
"""Create encrypted secrets for production services deployment.

This script generates encrypted Kubernetes secrets for:
- Cloudflare API token (for cert-manager)
- PostgreSQL credentials
- Redis credentials
- Authentik credentials

All secrets are encrypted using SOPS with age encryption.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import cluster_manager
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml  # noqa: E402

from cluster_manager.secrets import (  # noqa: E402
    create_authentik_credentials,
    create_cloudflare_config,
    create_postgresql_credentials,
    create_redis_credentials,
    encrypt_secret_with_sops,
    generate_age_key,
)


def main():
    """Main entry point for creating encrypted secrets."""
    parser = argparse.ArgumentParser(description="Create encrypted secrets for production services")
    parser.add_argument(
        "--age-public-key",
        type=str,
        help="Age public key for encryption (will generate if not provided)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("gitops/apps"),
        help="Directory to write encrypted secrets (default: gitops/apps)",
    )
    parser.add_argument(
        "--cloudflare-token", type=str, help="Cloudflare API token (required for cert-manager)"
    )
    parser.add_argument("--cloudflare-email", type=str, help="Cloudflare account email")
    parser.add_argument("--cloudflare-zone-id", type=str, help="Cloudflare zone ID for almckay.io")
    parser.add_argument(
        "--skip-encryption", action="store_true", help="Skip SOPS encryption (for testing)"
    )

    args = parser.parse_args()

    # Get or generate age key
    if args.age_public_key:
        age_public_key = args.age_public_key
        print(f"📝 Using provided age public key: {age_public_key}")
    else:
        print("🔐 Generating age key pair...")
        key_pair = generate_age_key()
        age_public_key = key_pair.public_key
        print(f"✅ Generated age public key: {age_public_key}")
        print(f"⚠️  Private key: {key_pair.private_key}")
        print("   Save this private key securely!")
        print()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("📝 Creating service credentials...")
    print()

    # Create PostgreSQL credentials
    print("1. Creating PostgreSQL credentials...")
    pg_creds = create_postgresql_credentials(database="authentik", username="authentik")
    pg_manifest = pg_creds.to_secret_manifest()

    pg_dir = output_dir / "postgresql"
    pg_dir.mkdir(parents=True, exist_ok=True)

    if args.skip_encryption:
        pg_file = pg_dir / "secret.yaml"
        with open(pg_file, "w") as f:
            yaml.dump(pg_manifest, f, default_flow_style=False)
        print(f"   ✅ Created {pg_file}")
    else:
        encrypted_pg = encrypt_secret_with_sops(pg_manifest, age_public_key)
        pg_file = pg_dir / "secret.enc.yaml"
        with open(pg_file, "w") as f:
            yaml.dump(encrypted_pg, f, default_flow_style=False)
        print(f"   ✅ Created encrypted secret at {pg_file}")

    print(f"   Database: {pg_creds.database}")
    print(f"   Username: {pg_creds.username}")
    print(f"   Password: {pg_creds.password[:8]}... (truncated)")
    print()

    # Create Redis credentials
    print("2. Creating Redis credentials...")
    redis_creds = create_redis_credentials()
    redis_manifest = redis_creds.to_secret_manifest()

    redis_dir = output_dir / "redis"
    redis_dir.mkdir(parents=True, exist_ok=True)

    if args.skip_encryption:
        redis_file = redis_dir / "secret.yaml"
        with open(redis_file, "w") as f:
            yaml.dump(redis_manifest, f, default_flow_style=False)
        print(f"   ✅ Created {redis_file}")
    else:
        encrypted_redis = encrypt_secret_with_sops(redis_manifest, age_public_key)
        redis_file = redis_dir / "secret.enc.yaml"
        with open(redis_file, "w") as f:
            yaml.dump(encrypted_redis, f, default_flow_style=False)
        print(f"   ✅ Created encrypted secret at {redis_file}")

    print(f"   Password: {redis_creds.password[:8]}... (truncated)")
    print()

    # Create Authentik credentials
    print("3. Creating Authentik credentials...")
    authentik_creds = create_authentik_credentials(
        postgres_password=pg_creds.password  # Use same password as PostgreSQL
    )
    authentik_manifest = authentik_creds.to_secret_manifest()

    authentik_dir = output_dir / "authentik"
    authentik_dir.mkdir(parents=True, exist_ok=True)

    if args.skip_encryption:
        authentik_file = authentik_dir / "secret.yaml"
        with open(authentik_file, "w") as f:
            yaml.dump(authentik_manifest, f, default_flow_style=False)
        print(f"   ✅ Created {authentik_file}")
    else:
        encrypted_authentik = encrypt_secret_with_sops(authentik_manifest, age_public_key)
        authentik_file = authentik_dir / "secret.enc.yaml"
        with open(authentik_file, "w") as f:
            yaml.dump(encrypted_authentik, f, default_flow_style=False)
        print(f"   ✅ Created encrypted secret at {authentik_file}")

    print(f"   Secret key: {authentik_creds.secret_key[:10]}... (truncated)")
    print(f"   Bootstrap password: {authentik_creds.bootstrap_password[:8]}... (truncated)")
    print(f"   Bootstrap token: {authentik_creds.bootstrap_token[:16]}... (truncated)")
    print()

    # Create Cloudflare config (if provided)
    if args.cloudflare_token and args.cloudflare_email and args.cloudflare_zone_id:
        print("4. Creating Cloudflare API token secret...")
        cf_config = create_cloudflare_config(
            api_token=args.cloudflare_token,
            email=args.cloudflare_email,
            zone_id=args.cloudflare_zone_id,
        )
        cf_manifest = cf_config.to_secret_manifest()

        cf_dir = Path("gitops/infrastructure/cert-manager")
        cf_dir.mkdir(parents=True, exist_ok=True)

        if args.skip_encryption:
            cf_file = cf_dir / "cloudflare-secret.yaml"
            with open(cf_file, "w") as f:
                yaml.dump(cf_manifest, f, default_flow_style=False)
            print(f"   ✅ Created {cf_file}")
        else:
            encrypted_cf = encrypt_secret_with_sops(cf_manifest, age_public_key)
            cf_file = cf_dir / "cloudflare-secret.enc.yaml"
            with open(cf_file, "w") as f:
                yaml.dump(encrypted_cf, f, default_flow_style=False)
            print(f"   ✅ Created encrypted secret at {cf_file}")

        print(f"   Email: {cf_config.email}")
        print(f"   Zone ID: {cf_config.zone_id}")
        print()
    else:
        print("4. Skipping Cloudflare secret (credentials not provided)")
        print("   Use --cloudflare-token, --cloudflare-email, and --cloudflare-zone-id to create")
        print()

    print("✅ All secrets created successfully!")
    print()
    print("📋 Next Steps:")
    print("1. Review the generated secrets")
    print("2. Commit encrypted secrets to Git:")
    print(f"   git add {output_dir}")
    print("   git commit -m 'Add encrypted production secrets'")
    print("3. Apply secrets to cluster (Flux will decrypt automatically)")
    print()

    if not args.age_public_key:
        print("⚠️  IMPORTANT: Save the age private key shown above!")
        print("   You'll need it to decrypt these secrets.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
