from __future__ import annotations

import json
import re
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
GITOPS = ROOT / "infrastructure/gitops"
PLATFORM = GITOPS / "apps/agent-platform"
REGISTRY = PLATFORM / "workloads/agent-registry.yaml"
PROVISIONER = PLATFORM / "workloads/registry-provisioner.yaml"
RBAC = PLATFORM / "registry-rbac.yaml"
TENANT_RBAC = GITOPS / "apps/agents/tenant-test/registry-provisioner-rbac.yaml"
NETPOL = PLATFORM / "netpol-registry.yaml"
INIT_JOB = PLATFORM / "registry-db-init-job.yaml"
KEYCLOAK = GITOPS / "apps/keycloak"
REALM = KEYCLOAK / "realm-agents.json"
NEW_FILES = [REGISTRY, PROVISIONER, RBAC, TENANT_RBAC, NETPOL, INIT_JOB]
IMAGE = r"registry\.almckay\.io/platform/{name}:[0-9a-f]{{7,}}@sha256:[0-9a-f]{{64}}"
NAME = "app.kubernetes.io/name"


def load(path: Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def find(docs: list[dict], kind: str, name: str) -> dict:
    return next(
        d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name
    )


def template_digest(job: dict) -> str:
    canonical = json.dumps(
        job["spec"]["template"], sort_keys=True, separators=(",", ":")
    )
    return sha256(canonical.encode()).hexdigest()


def container(deployment: dict) -> dict:
    return deployment["spec"]["template"]["spec"]["containers"][0]


def peer_names(peer: dict) -> set[str]:
    selector = peer.get("podSelector", {})
    names = set()
    if NAME in selector.get("matchLabels", {}):
        names.add(selector["matchLabels"][NAME])
    for expr in selector.get("matchExpressions", []):
        if expr["key"] == NAME and expr["operator"] == "In":
            names.update(expr["values"])
    return names


def ports_for(rules: list[dict], side: str, peer_name: str) -> set[int]:
    ports: set[int] = set()
    for rule in rules:
        if any(peer_name in peer_names(peer) for peer in rule.get(side, [])):
            ports.update(p["port"] for p in rule["ports"])
    return ports


class RegistryManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load(REGISTRY)
        cls.provisioner = load(PROVISIONER)
        cls.rbac = load(RBAC) + load(TENANT_RBAC)
        cls.netpol = load(NETPOL)
        cls.job = load(INIT_JOB)[0]
        cls.realm = json.loads(REALM.read_text())

    def test_new_files_parse_and_hold_no_secret(self) -> None:
        for path in NEW_FILES:
            docs = load(path)
            self.assertTrue(docs, path)
            for doc in docs:
                self.assertNotEqual(doc["kind"], "Secret", path)

    def test_init_job_name_digest_and_password_handling(self) -> None:
        digest = template_digest(self.job)
        self.assertEqual(
            self.job["metadata"]["name"],
            f"agent-registry-db-init-v1-{digest[:12]}",
            "pod template changed: rename the Job and update its digest annotation",
        )
        self.assertEqual(
            self.job["metadata"]["annotations"]["kubani.io/db-init-digest"],
            f"sha256:{digest}",
        )
        self.assertNotIn("ttlSecondsAfterFinished", self.job["spec"])
        script = container(self.job)["command"][2]
        self.assertLess(script.index("pg_isready"), script.index("psql"))
        for line in script.splitlines():
            if "echo" in line:
                self.assertNotIn("AGENT_REGISTRY_DB_PASSWORD", line)

    def test_deployments_are_hardened_and_wired(self) -> None:
        for docs, name in ((self.registry, "agent-registry"), (self.provisioner, "registry-provisioner")):
            deployment = find(docs, "Deployment", name)
            pod = deployment["spec"]["template"]["spec"]
            main = container(deployment)
            context = main["securityContext"]
            self.assertTrue(pod["securityContext"]["runAsNonRoot"])
            self.assertTrue(context["runAsNonRoot"])
            self.assertTrue(context["readOnlyRootFilesystem"])
            self.assertEqual(context["capabilities"]["drop"], ["ALL"])
            self.assertRegex(main["image"], IMAGE.format(name=name))

        main = container(find(self.registry, "Deployment", "agent-registry"))
        env = {e["name"]: e for e in main["env"]}
        dsn = env["REGISTRY_DSN"]["value"]
        self.assertNotIn(":", dsn.split("@")[0].removeprefix("postgresql://"))
        self.assertIn(
            "secretKeyRef", env["PGPASSWORD"]["valueFrom"],
        )

        deployment = find(self.provisioner, "Deployment", "registry-provisioner")
        self.assertEqual(deployment["spec"]["strategy"]["type"], "Recreate")
        volumes = deployment["spec"]["template"]["spec"]["volumes"]
        audiences = [
            source["serviceAccountToken"]["audience"]
            for volume in volumes
            for source in volume.get("projected", {}).get("sources", [])
        ]
        self.assertEqual(audiences, ["https://idp.almckay.io/realms/agents"])

    def test_rbac_is_least_privilege(self) -> None:
        rules = []
        for doc in self.rbac:
            self.assertNotEqual(doc["kind"], "ClusterRoleBinding")
            rules.extend(doc.get("rules", []))
            if doc["kind"] == "RoleBinding":
                for subject in doc["subjects"]:
                    self.assertNotEqual(subject["name"], "agent-registry")
        self.assertTrue(rules)
        for rule in rules:
            for key in ("verbs", "resources", "apiGroups"):
                self.assertNotIn("*", rule[key])
            for verb in ("delete", "deletecollection", "update"):
                self.assertNotIn(verb, rule["verbs"])
        agent_rules = [r for r in rules if "agents" in r["resources"]]
        self.assertEqual(len(agent_rules), 1)
        self.assertEqual(
            sorted(agent_rules[0]["verbs"]), ["create", "get", "list", "patch"]
        )

    def test_network_paths_have_both_sides(self) -> None:
        database = load(GITOPS / "infrastructure/networking/netpol-database.yaml")
        keycloak = load(KEYCLOAK / "netpol.yaml")
        registry_in = find(self.netpol, "NetworkPolicy", "agent-registry-ingress")
        registry_out = find(self.netpol, "NetworkPolicy", "agent-registry-egress")
        prov_out = find(self.netpol, "NetworkPolicy", "registry-provisioner-egress")
        eval_out = find(self.netpol, "NetworkPolicy", "registry-evaluator-egress")
        session_in = find(self.netpol, "NetworkPolicy", "session-api-ingress")
        into_postgres = find(database, "NetworkPolicy", "allow-agent-registry-postgresql")
        into_keycloak = find(keycloak, "NetworkPolicy", "allow-keycloak-from-agent-platform")
        pairs = (
            (registry_out, "postgresql", into_postgres, "agent-registry", 5432),
            (registry_out, "keycloak", into_keycloak, "agent-registry", 8080),
            (prov_out, "keycloak", into_keycloak, "registry-provisioner", 8080),
            (prov_out, "agent-registry", registry_in, "registry-provisioner", 8080),
            (eval_out, "agent-registry", registry_in, "registry-evaluator", 8080),
            (eval_out, "keycloak", into_keycloak, "registry-evaluator", 8080),
            (eval_out, "session-api", session_in, "registry-evaluator", 8080),
        )
        for egress, target, ingress, source, port in pairs:
            with self.subTest(source=source, target=target):
                self.assertIn(
                    port, ports_for(egress["spec"]["egress"], "to", target)
                )
                self.assertIn(
                    port, ports_for(ingress["spec"]["ingress"], "from", source)
                )

    def test_realm_declares_the_registry(self) -> None:
        realm = self.realm
        role_names = {r["name"] for r in realm["roles"]["realm"]}
        three = ["registry-reader", "registry-operator", "registry-provisioner"]
        self.assertTrue(set(three) <= role_names)
        mapping = next(
            m for m in realm["scopeMappings"] if m.get("clientScope") == "agent-registry"
        )
        self.assertEqual(mapping["roles"], three)

        # The registry tells a service from a person by client_id. Its clients have no
        # `profile` scope, so without this mapper a provisioner's token reads as a person's.
        scope = next(s for s in realm["clientScopes"] if s["name"] == "agent-registry")
        claims = {
            m["config"].get("claim.name"): m["config"].get("user.session.note")
            for m in scope["protocolMappers"]
            if m["protocolMapper"] == "oidc-usersessionmodel-note-mapper"
        }
        self.assertEqual(claims, {"client_id": "client_id"})

        clients = {c["clientId"]: c for c in realm["clients"]}
        # Keycloak generates the reader's secret. A placeholder here would become
        # the secret itself whenever its variable is unset at import.
        self.assertNotIn("secret", clients["registry-reader"])
        known = set(clients["registry-controller"]) | set(
            clients["agent-tenant-test-conformance"]
        )
        for client_id in ("registry-reader", "registry-provisioner-kubani"):
            self.assertLessEqual(set(clients[client_id]), known, client_id)
        provisioner = clients["registry-provisioner-kubani"]
        self.assertEqual(
            provisioner["attributes"]["jwt.credential.sub"],
            "system:serviceaccount:agent-platform:registry-provisioner",
        )

        cli = clients["agent-cli"]
        self.assertIn("agent-registry", cli["optionalClientScopes"])
        self.assertTrue(cli["publicClient"])
        self.assertFalse(cli["fullScopeAllowed"])
        self.assertTrue(cli["consentRequired"])

        users = {u["username"]: u for u in realm["users"]}
        self.assertEqual(
            users["service-account-registry-reader"]["realmRoles"], ["registry-reader"]
        )
        self.assertEqual(
            users["service-account-registry-provisioner-kubani"]["realmRoles"],
            ["registry-provisioner"],
        )
        for user in users.values():
            self.assertNotIn("registry-operator", user.get("realmRoles", []))

    def test_no_realm_description_is_longer_than_keycloak_stores(self) -> None:
        # Keycloak keeps a description in 255 characters. A longer one makes the import
        # into an empty database fail, which is found only on the day the realm is rebuilt.
        realm = self.realm
        described = [
            *((f"client {c['clientId']}", c) for c in realm["clients"]),
            *((f"scope {s['name']}", s) for s in realm["clientScopes"]),
            *((f"role {r['name']}", r) for r in realm["roles"]["realm"]),
        ]
        for label, item in described:
            with self.subTest(item=label):
                self.assertLessEqual(len(item.get("description", "")), 255)

    def test_every_secret_placeholder_in_the_realm_has_a_required_variable(self) -> None:
        deployment = next(
            d for d in load(KEYCLOAK / "deployment.yaml") if d["kind"] == "Deployment"
        )
        env = {e["name"]: e for e in container(deployment)["env"]}
        placeholders = set(re.findall(r"\$\{(KC_[A-Z0-9_]+)\}", REALM.read_text()))
        self.assertTrue(placeholders)
        for name in sorted(placeholders):
            with self.subTest(variable=name):
                self.assertIn(name, env)
                ref = env[name].get("valueFrom", {}).get("secretKeyRef", {})
                self.assertIsNot(ref.get("optional"), True)


if __name__ == "__main__":
    unittest.main()
