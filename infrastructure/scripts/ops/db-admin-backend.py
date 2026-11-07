#!/usr/bin/env python3
"""Compatibility entry point for the exact postgres-admin identity bootstrap."""
from pathlib import Path
import sys
import json
import argparse
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_registry import identity


def descriptor():
    return json.loads((Path(__file__).resolve().parents[2] / 'gitops/apps/keycloak/db-admin-backend.json').read_text())

_backend = identity.Identity(descriptor())
RESOURCE = _backend.RESOURCE
SCOPE = _backend.SCOPE
REQUESTER = _backend.REQUESTER
ROLE = _backend.ROLE
resource_body = _backend.resource_body
scope_body = _backend.scope_body
role_body = _backend.role_body
inspect = _backend.inspect
verify_resource = _backend.verify_resource
verify_scope = _backend.verify_scope
find_role = _backend.find_role
find_client = identity.find_client
rows = identity.rows
object_id = identity.object_id
admin = identity.admin


def configure(api, *, apply=False):
    return identity.configure(api, descriptor(), apply=apply)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="explicitly create/attach exact missing backend objects",
    )
    args = parser.parse_args()
    try:
        result = configure(admin(), apply=args.apply)
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "error_type": type(error).__name__,
                    "note": "No conflicting object is overwritten; reconcile any ambiguous partial write before retry.",
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
