"""Native credential/isolated-workspace control; not a Temporal execution test."""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import grpc
from openshell import SandboxClient, TlsConfig
from openshell._proto import datamodel_pb2 as d
from openshell._proto import openshell_pb2 as o
from zetra._runtime.openshell import vllm_policy
from zetra.manifest import load_release

WARM = r"""
import asyncio,json,os,pathlib
from kubani_investigator.agents.investigator.dependencies import KubernetesMcp
p=pathlib.Path('/sandbox/credential-check.json')
async def main():
 token=os.environ.get('MCP_ACCESS_TOKEN','')
 assert token.startswith('openshell:resolve:env:'), 'Expected native opaque placeholder'
 first=await KubernetesMcp().call('pods_list_in_namespace',{'namespace':'zetra-poc-fixtures','labelSelector':'app=investigator-demo'})
 assert 'investigator-demo-healthy' in first['text'] and 'investigator-demo-broken' in first['text']
 pathlib.Path('/sandbox/private-sentinel').write_text('session A only')
 result={'phase':'ready','pid':os.getpid(),'pid_namespace':os.readlink('/proc/self/ns/pid'),'opaque_placeholder':True,'before_read':True}
 p.write_text(json.dumps(result))
 while not pathlib.Path('/sandbox/continue-after-rotation').exists():await asyncio.sleep(.1)
 second=await KubernetesMcp().call('pods_list_in_namespace',{'namespace':'zetra-poc-fixtures','labelSelector':'app=investigator-demo'})
 assert 'investigator-demo-healthy' in second['text']
 result.update(phase='complete',after_read=True,same_environment_reference=token==os.environ['MCP_ACCESS_TOKEN'])
 p.write_text(json.dumps(result))
 await asyncio.sleep(300)
try:asyncio.run(main())
except Exception as error:p.write_text(json.dumps({'phase':'error','error_type':type(error).__name__}));raise
"""

CONTROL = r"""
import asyncio,json,os,pathlib,socket,httpx2
from kubani_investigator.agents.investigator.dependencies import KubernetesMcp
async def main():
 token=os.environ.get('MCP_ACCESS_TOKEN','')
 assert token.startswith('openshell:resolve:env:')
 r={'sentinel_from_a':pathlib.Path('/sandbox/private-sentinel').exists(),'pid_namespace':os.readlink('/proc/self/ns/pid')}
 observed=await KubernetesMcp().call('pods_list_in_namespace',{'namespace':'zetra-poc-fixtures'})
 r['positive_mcp']='investigator-demo-healthy' in observed['text']
 for name,path in [('unlisted_write','/var/tmp/zetra-unlisted'),('app_write','/app/zetra-unlisted')]:
  try:pathlib.Path(path).write_text('denied');r[name]='ALLOWED'
  except OSError as e:r[name]=type(e).__name__
 try:pathlib.Path('/var/lib/dpkg/status').read_bytes();r['unlisted_read']='ALLOWED'
 except OSError as e:r['unlisted_read']=type(e).__name__
 async with httpx2.AsyncClient(headers={'Authorization':'Bearer '+token},timeout=5) as c:
  for name,url,method in [('wrong_method','https://mcp.almckay.io/kubernetes/mcp','PUT'),('other_backend','https://mcp.almckay.io/github/mcp','GET')]:
   response=await c.request(method,url);r[name]=response.status_code
 try:socket.create_connection(('temporal-frontend.temporal.svc.cluster.local',7233),timeout=3).close();r['temporal_access']='ALLOWED'
 except OSError as e:r['temporal_access']=type(e).__name__
 print(json.dumps(r))
asyncio.run(main())
"""


def cleanup_refs(client, refs):
    """Attempt every immutable instance; never convert an RPC error to deletion."""
    results = []
    for ref in refs:
        entry = {"sandbox_id": ref.id, "cleanup": "NOT_CONFIRMED"}
        try:
            try:
                current = client.get(ref.name, workspace="default")
            except grpc.RpcError as error:
                if error.code() != grpc.StatusCode.NOT_FOUND:
                    raise
            else:
                assert current.id == ref.id
                client.stop(ref.name, workspace="default")
                client.delete(ref.name, workspace="default", allow_missing=True)
            client.wait_deleted(ref.name, workspace="default", expected_sandbox_id=ref.id)
            entry["cleanup"] = "DELETED"
        except Exception:  # noqa: BLE001 -- record failure, still attempt every other instance
            entry["cleanup"] = "NOT_CONFIRMED"
        results.append(entry)
    return results


def main(args):
    release = load_release(args.release)
    client = SandboxClient(
        args.address,
        tls=TlsConfig(
            ca_path=args.tls_dir / "ca.crt",
            cert_path=args.tls_dir / "tls.crt",
            key_path=args.tls_dir / "tls.key",
        ),
    )
    refs = []
    result = {"scope": "native credential and workspace control", "image": release.image}
    try:
        for command in (WARM, "import time; time.sleep(300)"):
            ref = client.create(
                workspace="default",
                name="p-" + uuid4().hex[:16],
                spec=o.SandboxSpec(
                    template=o.SandboxTemplate(image=release.image),
                    policy=vllm_policy(),
                    providers=["kubani-k8s-read"],
                    command=["/app/.venv/bin/python", "-c", command],
                ),
            )
            refs.append(ref)
            client.wait_ready(ref.name, workspace="default", timeout_seconds=180)
        deadline = time.monotonic() + 60
        while True:
            response = client.exec(
                refs[0].name,
                [
                    "/app/.venv/bin/python",
                    "-c",
                    "import pathlib; p=pathlib.Path('/sandbox/credential-check.json'); print(p.read_text() if p.exists() else '{}')",
                ],
                workspace="default",
                timeout_seconds=10,
                no_login_shell=True,
            )
            before = json.loads(response.stdout)
            if before.get("phase") == "ready":
                break
            assert before.get("phase") != "error", before
            if time.monotonic() > deadline:
                raise TimeoutError("First MCP call did not complete")
            time.sleep(0.2)
        response = client.exec(
            refs[1].name,
            ["/app/.venv/bin/python", "-c", CONTROL],
            workspace="default",
            timeout_seconds=30,
            no_login_shell=True,
        )
        assert response.exit_code == 0, "Native credential control failed"
        control = json.loads(response.stdout)
        assert (
            not control["sentinel_from_a"] and control["pid_namespace"] != before["pid_namespace"]
        )
        assert control["positive_mcp"]
        assert all(
            control[k] == "PermissionError"
            for k in ("unlisted_write", "app_write", "unlisted_read")
        )
        assert control["wrong_method"] == control["other_backend"] == 403
        assert control["temporal_access"] == "PermissionError"
        rotation = client._stub.RotateProviderCredential(
            o.RotateProviderCredentialRequest(
                workspace_scope=d.WorkspaceSelector(workspace="default"),
                provider="kubani-k8s-read",
                credential_key="MCP_ACCESS_TOKEN",
                request_id=str(uuid4()),
            ),
            timeout=45,
        )
        assert rotation.status.status == "refreshed"
        client.exec(
            refs[0].name,
            [
                "/app/.venv/bin/python",
                "-c",
                "import pathlib; pathlib.Path('/sandbox/continue-after-rotation').touch()",
            ],
            workspace="default",
        )
        deadline = time.monotonic() + 45
        while True:
            response = client.exec(
                refs[0].name,
                [
                    "/app/.venv/bin/python",
                    "-c",
                    "import pathlib; print(pathlib.Path('/sandbox/credential-check.json').read_text())",
                ],
                workspace="default",
                timeout_seconds=10,
                no_login_shell=True,
            )
            after = json.loads(response.stdout)
            if after.get("phase") == "complete":
                break
            assert after.get("phase") != "error", after
            if time.monotonic() > deadline:
                raise TimeoutError("MCP call after rotation did not complete")
            time.sleep(0.2)
        assert after["pid"] == before["pid"] and after["same_environment_reference"]
        result.update(
            control=control,
            warm_process=after,
            native_rotation="refreshed",
            probe_assertions="PASSED",
        )
    finally:
        try:
            result["instances"] = cleanup_refs(client, refs)
            result["cleanup"] = (
                "DELETED"
                if all(r["cleanup"] == "DELETED" for r in result["instances"])
                else "NOT_CONFIRMED"
            )
        finally:
            result["qualification"] = (
                "PASSED"
                if result.get("probe_assertions") == "PASSED" and result.get("cleanup") == "DELETED"
                else "FAILED"
            )
            try:
                client.close()
            finally:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2) + "\n")
    assert result["cleanup"] == "DELETED", "Native probe cleanup not confirmed"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True)
    parser.add_argument("--tls-dir", type=Path, required=True)
    parser.add_argument("--release", type=Path, default=Path(".tools/release.json"))
    parser.add_argument("--output", type=Path, default=Path(".tools/credential-control.json"))
    main(parser.parse_args())
