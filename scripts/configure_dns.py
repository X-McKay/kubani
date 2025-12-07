#!/usr/bin/env python3
"""Configure DNS records in Cloudflare for production services.

This script creates A records for PostgreSQL, Redis, and Authentik services
pointing to the Traefik LoadBalancer IP.
"""

import argparse
import subprocess
import sys

import requests


def get_cloudflare_token():
    """Get Cloudflare API token from Kubernetes secret."""
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "secret",
                "cloudflare-api-token",
                "-n",
                "cert-manager",
                "-o",
                "jsonpath={.data.api-token}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        import base64

        token = base64.b64decode(result.stdout).decode("utf-8")
        return token
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to get Cloudflare token from Kubernetes: {e.stderr}")
        return None


def get_traefik_ip():
    """Get Traefik LoadBalancer IP from Kubernetes."""
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "svc",
                "-n",
                "kube-system",
                "traefik",
                "-o",
                "jsonpath={.status.loadBalancer.ingress[0].ip}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to get Traefik IP: {e.stderr}")
        return None


def get_zone_id(api_token, domain, email=None):
    """Get Cloudflare zone ID for the domain."""
    # Try API Token first (Bearer auth)
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}

    response = requests.get(
        f"https://api.cloudflare.com/client/v4/zones?name={domain}", headers=headers
    )

    # If Bearer auth fails and we have an email, try Global API Key
    if response.status_code != 200 and email:
        print(f"⚠️  Bearer token failed, trying Global API Key with email {email}...")
        headers = {
            "X-Auth-Email": email,
            "X-Auth-Key": api_token,
            "Content-Type": "application/json",
        }
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones?name={domain}", headers=headers
        )

    if response.status_code != 200:
        print(f"❌ Failed to get zone ID: {response.text}")
        return None, None

    data = response.json()
    if not data["success"] or not data["result"]:
        print(f"❌ Zone not found for domain: {domain}")
        return None, None

    # Return zone_id and headers for subsequent requests
    return data["result"][0]["id"], headers


def list_dns_records(zone_id, headers, name=None):
    """List DNS records in the zone."""

    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    if name:
        url += f"?name={name}"

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"❌ Failed to list DNS records: {response.text}")
        return []

    data = response.json()
    if not data["success"]:
        print(f"❌ Failed to list DNS records: {data.get('errors', [])}")
        return []

    return data["result"]


def create_dns_record(zone_id, headers, name, ip_address, record_type="A", proxied=False):
    """Create a DNS record in Cloudflare."""
    # Check if record already exists
    existing_records = list_dns_records(zone_id, headers, name)
    for record in existing_records:
        if record["type"] == record_type and record["name"] == name:
            if record["content"] == ip_address:
                print(f"✓ DNS record {name} already exists with correct IP {ip_address}")
                return True
            else:
                print(
                    f"⚠️  DNS record {name} exists but with different IP: {record['content']} (expected: {ip_address})"
                )
                # Update the record
                return update_dns_record(
                    zone_id, headers, record["id"], name, ip_address, record_type, proxied
                )

    # Create new record
    payload = {
        "type": record_type,
        "name": name,
        "content": ip_address,
        "ttl": 1,  # Auto
        "proxied": proxied,
    }

    response = requests.post(
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
        headers=headers,
        json=payload,
    )

    if response.status_code != 200:
        print(f"❌ Failed to create DNS record {name}: {response.text}")
        return False

    data = response.json()
    if not data["success"]:
        print(f"❌ Failed to create DNS record {name}: {data.get('errors', [])}")
        return False

    print(f"✅ Created DNS record: {name} → {ip_address}")
    return True


def update_dns_record(
    zone_id, headers, record_id, name, ip_address, record_type="A", proxied=False
):
    """Update an existing DNS record in Cloudflare."""

    payload = {
        "type": record_type,
        "name": name,
        "content": ip_address,
        "ttl": 1,  # Auto
        "proxied": proxied,
    }

    response = requests.put(
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}",
        headers=headers,
        json=payload,
    )

    if response.status_code != 200:
        print(f"❌ Failed to update DNS record {name}: {response.text}")
        return False

    data = response.json()
    if not data["success"]:
        print(f"❌ Failed to update DNS record {name}: {data.get('errors', [])}")
        return False

    print(f"✅ Updated DNS record: {name} → {ip_address}")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Configure DNS records for production services")
    parser.add_argument(
        "--domain", type=str, default="almckay.io", help="Domain name (default: almckay.io)"
    )
    parser.add_argument(
        "--api-token", type=str, help="Cloudflare API token (will fetch from k8s if not provided)"
    )
    parser.add_argument(
        "--traefik-ip",
        type=str,
        help="Traefik LoadBalancer IP (will fetch from k8s if not provided)",
    )
    parser.add_argument(
        "--services",
        type=str,
        nargs="+",
        default=["postgres", "redis", "auth"],
        help="Services to configure DNS for (default: postgres redis auth)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    print("🔧 Configuring DNS records for production services...")
    print()

    # Get Cloudflare API token
    if args.api_token:
        api_token = args.api_token
        print("📝 Using provided API token")
    else:
        print("🔐 Fetching Cloudflare API token from Kubernetes...")
        api_token = get_cloudflare_token()
        if not api_token:
            print("❌ Failed to get Cloudflare API token")
            return 1

    # Get Traefik IP
    if args.traefik_ip:
        traefik_ip = args.traefik_ip
        print(f"📝 Using provided Traefik IP: {traefik_ip}")
    else:
        print("🔍 Fetching Traefik LoadBalancer IP from Kubernetes...")
        traefik_ip = get_traefik_ip()
        if not traefik_ip:
            print("❌ Failed to get Traefik IP")
            return 1
        print(f"✓ Traefik IP: {traefik_ip}")

    print()

    # Get zone ID
    print(f"🔍 Getting zone ID for {args.domain}...")
    zone_id, headers = get_zone_id(api_token, args.domain, email="admin@almckay.io")
    if not zone_id:
        return 1
    print(f"✓ Zone ID: {zone_id}")
    print()

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()

    # Create DNS records for each service
    success = True
    for service in args.services:
        fqdn = f"{service}.{args.domain}"
        print(f"📝 Configuring DNS record for {fqdn}...")

        if args.dry_run:
            print(f"   Would create: {fqdn} → {traefik_ip}")
        else:
            if not create_dns_record(zone_id, headers, fqdn, traefik_ip, proxied=False):
                success = False

        print()

    if success:
        print("✅ All DNS records configured successfully!")
        print()
        print("📋 Verification:")
        print("   Wait 1-2 minutes for DNS propagation, then test:")
        for service in args.services:
            fqdn = f"{service}.{args.domain}"
            print(f"   nslookup {fqdn}")
        print()
        print("🔗 Service endpoints:")
        for service in args.services:
            fqdn = f"{service}.{args.domain}"
            if service == "postgres":
                print(f"   PostgreSQL: psql -h {fqdn} -p 5432 -U authentik -d authentik")
            elif service == "redis":
                print(f"   Redis: redis-cli -h {fqdn} -p 6379")
            elif service == "auth":
                print(f"   Authentik: https://{fqdn}")
        return 0
    else:
        print("❌ Some DNS records failed to configure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
