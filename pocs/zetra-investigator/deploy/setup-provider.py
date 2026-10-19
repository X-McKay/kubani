"""One-time POC operator setup. Secrets stay in native encrypted OpenShell storage."""

import argparse
import base64
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import grpc
from google.protobuf.json_format import ParseDict
from google.protobuf.timestamp_pb2 import Timestamp
from openshell import SandboxClient, TlsConfig
from openshell._proto import datamodel_pb2 as d
from openshell._proto import openshell_pb2 as o

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--address", required=True)
parser.add_argument("--tls-dir", type=Path, required=True)
args = parser.parse_args()
scope = d.WorkspaceSelector(workspace="default")
profile = ParseDict(
    json.loads(Path(__file__).with_name("kubernetes-mcp-profile.json").read_text()),
    o.ProviderProfile(),
)
client = SandboxClient(
    args.address,
    tls=TlsConfig(
        ca_path=args.tls_dir / "ca.crt",
        cert_path=args.tls_dir / "tls.crt",
        key_path=args.tls_dir / "tls.key",
    ),
)


def get_or_create(get, create):
    try:
        return get()
    except grpc.RpcError as error:
        if error.code() != grpc.StatusCode.NOT_FOUND:
            raise
        return create()


def install_profile():
    result = client._stub.ImportProviderProfiles(
        o.ImportProviderProfilesRequest(
            workspace_scope=scope,
            profiles=[o.ProviderProfileImportItem(profile=profile, source="zetra-poc")],
            request_id=str(uuid4()),
        ),
        timeout=30,
    )
    if not result.imported:
        raise ValueError("Profile import rejected; inspect the public profile definition")
    return result.profiles[0]


def status():
    return client._stub.GetProviderRefreshStatus(
        o.GetProviderRefreshStatusRequest(
            workspace_scope=scope, provider=profile.id, credential_key="MCP_ACCESS_TOKEN"
        ),
        timeout=15,
    ).credentials


try:
    installed = get_or_create(
        lambda: (
            client._stub.GetProviderProfile(
                o.GetProviderProfileRequest(workspace_scope=scope, id=profile.id), timeout=30
            ).profile
        ),
        install_profile,
    )
    if any(
        list(getattr(installed, k)) != list(getattr(profile, k))
        for k in ("credentials", "endpoints", "binaries")
    ):
        raise ValueError("Existing profile differs; do not silently change active authorization")
    provider = get_or_create(
        lambda: client._stub.GetProvider(
            o.GetProviderRequest(workspace_scope=scope, name=profile.id), timeout=30
        ),
        lambda: client._stub.CreateProvider(
            o.CreateProviderRequest(
                workspace_scope=scope,
                request_id=str(uuid4()),
                provider=d.Provider(
                    metadata=d.ObjectMeta(name=profile.id),
                    type=profile.id,
                    profile_workspace="default",
                ),
            ),
            timeout=30,
        ),
    ).provider
    if provider.type != profile.id or provider.profile_workspace != "default":
        raise ValueError("Unexpected provider binding")
    current = status()
    if not current:
        if client.list(workspace="default").all():
            raise ValueError("Configure authorization only before sessions are running")
        # This is Kubani's explicitly approved POC test identity, not SDK onboarding.
        raw = subprocess.check_output(
            [
                "kubectl",
                "--context",
                "default",
                "-n",
                "auth",
                "exec",
                "deployment/authentik-worker",
                "--",
                "ak",
                "shell",
                "-c",
                (
                    "from authentik.core.models import Token; "
                    "print('POC_CREDENTIAL='+Token.objects.get("
                    "identifier='mcp-test-user-app-password').key)"
                ),
            ],
            text=True,
            stderr=subprocess.PIPE,
        )
        password = next(
            x.partition("=")[2] for x in raw.splitlines() if x.startswith("POC_CREDENTIAL=")
        )
        secret = base64.b64encode(("mcp-test-user:" + password).encode()).decode()
        client._stub.ConfigureProviderRefresh(
            o.ConfigureProviderRefreshRequest(
                workspace_scope=scope,
                provider=profile.id,
                credential_key="MCP_ACCESS_TOKEN",
                strategy=4,
                material={"client_id": "kubani-agentgateway-mcp", "client_secret": secret},
                secret_material_keys=["client_secret"],
                expiration_time=Timestamp(seconds=0),
                request_id=str(uuid4()),
            ),
            timeout=30,
        )
    deadline = time.monotonic() + 45
    while True:
        current = status()
        if current and all(
            x.status == "refreshed" and x.expiration_time.seconds > time.time() for x in current
        ):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Native refresh is not ready; inspect native structured status")
        time.sleep(1)
    print(json.dumps({"provider": profile.id, "refresh": "ready", "credentials_exported": False}))
except Exception as error:  # noqa: BLE001 -- Never expose secret-bearing exception details.
    print(
        json.dumps(
            {
                "error_type": type(error).__name__,
                "rpc_code": str(getattr(error, "code", lambda: None)()),
            }
        )
    )
    raise SystemExit(1) from None
finally:
    client.close()
