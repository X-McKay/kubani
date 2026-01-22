#!/usr/bin/env python3
"""Setup SOPS and age encryption infrastructure for the cluster.

This script:
1. Generates an age key pair for the cluster
2. Creates .sops.yaml configuration file with age public key
3. Creates Kubernetes secret in flux-system namespace with age private key
4. Provides instructions for configuring Flux Kustomization to enable SOPS decryption
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import cluster_manager
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml  # noqa: E402

from cluster_manager.secrets import (  # noqa: E402
    create_sops_config,
    generate_age_key,
)


def main():
    """Main entry point for SOPS setup script."""
    parser = argparse.ArgumentParser(description="Setup SOPS and age encryption infrastructure")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory to write configuration files (default: current directory)",
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        help="Path to save the age private key (default: age.key in output dir)",
    )
    parser.add_argument(
        "--sops-config",
        type=Path,
        help="Path to save .sops.yaml config (default: .sops.yaml in output dir)",
    )
    parser.add_argument(
        "--k8s-secret",
        type=Path,
        help="Path to save Kubernetes secret manifest (default: sops-age-secret.yaml in output dir)",
    )

    args = parser.parse_args()

    # Set default paths
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    key_file = args.key_file or output_dir / "age.key"
    sops_config_file = args.sops_config or output_dir / ".sops.yaml"
    k8s_secret_file = args.k8s_secret or output_dir / "sops-age-secret.yaml"

    print("🔐 Setting up SOPS and age encryption infrastructure...")
    print()

    # Step 1: Generate age key pair
    print("📝 Step 1: Generating age key pair...")
    try:
        key_pair = generate_age_key()
        print("✅ Age key pair generated successfully")
        print(f"   Public key: {key_pair.public_key}")
        print()
    except Exception as e:
        print(f"❌ Failed to generate age key pair: {e}")
        return 1

    # Step 2: Save private key to file
    print(f"📝 Step 2: Saving age private key to {key_file}...")
    try:
        key_file.write_text(key_pair.private_key + "\n")
        key_file.chmod(0o600)  # Restrict permissions
        print(f"✅ Private key saved to {key_file}")
        print("   ⚠️  Keep this file secure! It's needed to decrypt secrets.")
        print()
    except Exception as e:
        print(f"❌ Failed to save private key: {e}")
        return 1

    # Step 3: Create .sops.yaml configuration
    print(f"📝 Step 3: Creating SOPS configuration at {sops_config_file}...")
    try:
        create_sops_config(key_pair.public_key, sops_config_file)
        print(f"✅ SOPS configuration created at {sops_config_file}")
        print()
    except Exception as e:
        print(f"❌ Failed to create SOPS configuration: {e}")
        return 1

    # Step 4: Create Kubernetes secret manifest
    print(f"📝 Step 4: Creating Kubernetes secret manifest at {k8s_secret_file}...")
    try:
        k8s_secret = key_pair.to_kubernetes_secret()
        with open(k8s_secret_file, "w") as f:
            yaml.dump(k8s_secret, f, default_flow_style=False)
        print(f"✅ Kubernetes secret manifest created at {k8s_secret_file}")
        print()
    except Exception as e:
        print(f"❌ Failed to create Kubernetes secret manifest: {e}")
        return 1

    # Step 5: Provide instructions
    print("📋 Next Steps:")
    print()
    print("1. Apply the Kubernetes secret to your cluster:")
    print(f"   kubectl apply -f {k8s_secret_file}")
    print()
    print("2. Configure Flux Kustomization to enable SOPS decryption:")
    print("   Add the following to your Kustomization resource:")
    print()
    print("   spec:")
    print("     decryption:")
    print("       provider: sops")
    print("       secretRef:")
    print("         name: sops-age")
    print()
    print("3. Encrypt secrets using SOPS:")
    print(f"   sops --encrypt --age {key_pair.public_key} secret.yaml > secret.enc.yaml")
    print()
    print("4. Commit encrypted secrets to Git:")
    print("   git add secret.enc.yaml .sops.yaml")
    print("   git commit -m 'Add encrypted secrets'")
    print()
    print("✅ SOPS and age encryption infrastructure setup complete!")
    print()
    print("⚠️  IMPORTANT: Keep age.key secure and backed up!")
    print("   Without it, you cannot decrypt your secrets.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
