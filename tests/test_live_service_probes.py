from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "infrastructure/scripts/live_service_probes.py"
SPEC = importlib.util.spec_from_file_location("live_service_probes", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
PROBES = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROBES
SPEC.loader.exec_module(PROBES)


def endpoint(namespace: str, name: str, addresses: list[str] | None = None) -> dict:
    subsets = []
    if addresses:
        subsets = [{"addresses": [{"ip": address} for address in addresses]}]
    return {
        "metadata": {"namespace": namespace, "name": name},
        "subsets": subsets,
    }


def deployment(namespace: str, name: str, replicas: int) -> dict:
    return {
        "metadata": {"namespace": namespace, "name": name},
        "spec": {"replicas": replicas},
    }


class RequiredServiceEndpointTests(unittest.TestCase):
    def test_known_services_are_exempt_only_while_owner_declares_zero_replicas(
        self,
    ) -> None:
        endpoint_payload = {
            "items": [
                endpoint("vllm", "embeddings-api"),
            ]
        }
        deployment_payload = {
            "items": [
                deployment("vllm", "vllm-embeddings", 0),
            ]
        }

        with patch.object(
            PROBES,
            "kubectl_json",
            side_effect=[endpoint_payload, deployment_payload],
        ):
            result = PROBES.probe_required_service_endpoints()

        self.assertEqual(
            result,
            "all non-exempt services have ready endpoints; "
            "1 services are intentionally inactive",
        )

    def test_zero_replica_exemption_stops_when_owner_is_activated(self) -> None:
        endpoint_payload = {
            "items": [endpoint("vllm", "embeddings-api")]
        }
        deployment_payload = {
            "items": [deployment("vllm", "vllm-embeddings", 1)]
        }

        with patch.object(
            PROBES,
            "kubectl_json",
            side_effect=[endpoint_payload, deployment_payload],
        ):
            with self.assertRaisesRegex(
                PROBES.ProbeError,
                r"services without ready endpoints: vllm/embeddings-api$",
            ):
                PROBES.probe_required_service_endpoints()

    def test_unmapped_empty_service_is_never_exempt(self) -> None:
        endpoint_payload = {"items": [endpoint("example", "unexpected")]}
        deployment_payload = {"items": []}

        with patch.object(
            PROBES,
            "kubectl_json",
            side_effect=[endpoint_payload, deployment_payload],
        ):
            with self.assertRaisesRegex(
                PROBES.ProbeError,
                r"services without ready endpoints: example/unexpected$",
            ):
                PROBES.probe_required_service_endpoints()


class AuthentikOutpostProbeTests(unittest.TestCase):
    def test_probe_uses_python_runtime_and_keeps_token_on_stdin(self) -> None:
        payload = {
            "results": [
                {
                    "name": "authentik Embedded Outpost",
                    "providers_obj": [
                        {"name": "Kubani FalkorDB Browser"},
                        {"name": "Kubani Qdrant"},
                    ],
                }
            ]
        }

        with (
            patch.object(
                PROBES,
                "get_secret_value",
                return_value="synthetic-bootstrap-token",
            ),
            patch.object(
                PROBES,
                "run_command",
                return_value=json.dumps(payload),
            ) as command,
        ):
            result = PROBES.probe_authentik_proxy_outpost_assignments()

        args = command.call_args.args[0]
        self.assertIn("python", args)
        self.assertFalse(any("curl" in argument for argument in args))
        self.assertFalse(
            any("synthetic-bootstrap-token" in argument for argument in args)
        )
        self.assertEqual(
            command.call_args.kwargs["input_text"],
            "synthetic-bootstrap-token\n",
        )
        self.assertEqual(
            result,
            "Authentik embedded outpost has FalkorDB and Qdrant proxy providers",
        )


class OptionalModelProbeTests(unittest.TestCase):
    def test_embeddings_probe_skips_only_while_deployment_is_scaled_to_zero(
        self,
    ) -> None:
        with patch.object(
            PROBES,
            "kubectl_json",
            return_value=deployment("vllm", "vllm-embeddings", 0),
        ):
            with self.assertRaisesRegex(
                PROBES.ProbeSkip,
                "vllm/vllm-embeddings is intentionally inactive",
            ):
                PROBES.probe_embeddings_models()

    def test_embeddings_probe_runs_when_deployment_is_active(self) -> None:
        with (
            patch.object(
                PROBES,
                "kubectl_json",
                return_value=deployment("vllm", "vllm-embeddings", 1),
            ),
            patch.object(
                PROBES,
                "probe_vllm_models",
                return_value="embeddings.almckay.io returned model list",
            ) as model_probe,
        ):
            result = PROBES.probe_embeddings_models()

        model_probe.assert_called_once_with("embeddings.almckay.io")
        self.assertEqual(result, "embeddings.almckay.io returned model list")


if __name__ == "__main__":
    unittest.main()
