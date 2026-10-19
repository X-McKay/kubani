"""Stage only the public gateway CA for native shared-mode supervisor pods."""

import json
import subprocess

ca = subprocess.check_output(
    [
        "kubectl",
        "--context",
        "default",
        "-n",
        "zetra-poc",
        "get",
        "secret",
        "openshell-client-tls",
        "-o",
        r"jsonpath={.data.ca\.crt}",
    ],
    text=True,
)
if not ca.strip():
    raise ValueError("Generated gateway CA is missing")
secret = {
    "apiVersion": "v1",
    "kind": "Secret",
    "metadata": {"name": "openshell-client-tls", "namespace": "zetra-poc-sandboxes"},
    "type": "Opaque",
    "data": {"ca.crt": ca},
}
subprocess.run(
    ["kubectl", "--context", "default", "apply", "-f", "-"],
    input=json.dumps(secret),
    text=True,
    check=True,
)
print("Staged only the public CA certificate; no client certificate or key")
