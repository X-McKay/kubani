"""Exact descriptor-driven, create/attach-only Keycloak identity bootstrap."""
from __future__ import annotations
from copy import deepcopy
import importlib.util
from pathlib import Path
import re
from urllib.parse import quote


def validate_descriptor(value):
    """Accept only the supported bounded audience/role descriptor, never admin passthrough."""
    if not isinstance(value, dict) or set(value) != {'role','resource','scope','requester','attachment'}:
        raise ValueError('invalid identity descriptor')
    d = deepcopy(value)
    r, c, s = d['role'], d['resource'], d['scope']
    if not all(isinstance(v, dict) for v in (r,c,s)):
        raise ValueError('invalid identity descriptor bodies')
    scope = s.get('name', '')
    if not isinstance(scope, str) or not re.fullmatch(r'mcp:[a-z][a-z0-9-]{0,62}', scope):
        raise ValueError('invalid backend scope')
    backend = scope[4:]
    audience = 'https://mcp.almckay.io/' + backend + '/mcp'
    role = r.get('name', '')
    if not isinstance(role, str) or not re.fullmatch(r'agent-role-' + re.escape(backend) + r'-[a-z][a-z0-9-]{0,62}', role):
        raise ValueError('invalid backend role')
    def exact(actual, expected, descriptive=()):
        if set(actual) - set(expected) - set(descriptive) or any(actual.get(k) != v or type(actual.get(k)) is not type(v) for k,v in expected.items()):
            raise ValueError('unsupported identity semantics')
        if any(k in actual and (not isinstance(actual[k],str) or len(actual[k]) > 1024) for k in descriptive):
            raise ValueError('invalid identity description')
    exact(r, {'name':role,'composite':False,'clientRole':False,'attributes':{}}, ('description',))
    exact(c, {'clientId':audience,'enabled':True,'protocol':'openid-connect','bearerOnly':True,'publicClient':False,'standardFlowEnabled':False,'directAccessGrantsEnabled':False,'serviceAccountsEnabled':False}, ('name','description'))
    attrs=deepcopy(s.get('attributes'))
    if isinstance(attrs,dict) and attrs.get('display.on.consent.screen') == 'false':
        attrs.pop('display.on.consent.screen')
    mapper={'name':'aud-'+scope,'protocol':'openid-connect','protocolMapper':'oidc-audience-mapper','config':{'included.custom.audience':audience,'access.token.claim':'true','id.token.claim':'false','introspection.token.claim':'true'}}
    mappers=deepcopy(s.get('protocolMappers'))
    if isinstance(mappers,list) and len(mappers)==1 and isinstance(mappers[0],dict) and mappers[0].get('consentRequired') is False:
        mappers[0].pop('consentRequired')
    exact(s, {'name':scope,'protocol':'openid-connect','attributes':s.get('attributes'),'protocolMappers':s.get('protocolMappers')}, ('description',))
    if attrs != {'include.in.token.scope':'true'} or mappers != [mapper] or d['requester'] != 'agent-policy-service' or d['attachment'] != 'optional':
        raise ValueError('unsupported scope or requester semantics')
    # Canonical harmless Keycloak defaults match the historical helper payload.
    d['scope']={'name':scope,'protocol':'openid-connect','attributes':attrs,'protocolMappers':[mapper]}
    return d

def rows(value):
    if (
        not isinstance(value, list)
        or len(value) > 1000
        or any(not isinstance(v, dict) for v in value)
    ):
        raise ValueError("invalid bounded associated read")
    return value


def object_id(value):
    ident = value.get("id")
    if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ident):
        raise ValueError("invalid object identity")
    return ident


def find_client(api, client_id):
    found = rows(api.call("clients?clientId=" + quote(client_id, safe="")))
    if len(found) > 1 or any(v.get("clientId") != client_id for v in found):
        raise ValueError("client identity is ambiguous")
    if not found:
        return None
    ident = object_id(found[0])
    actual = api.call("clients/" + ident)
    if (
        not isinstance(actual, dict)
        or actual.get("clientId") != client_id
        or object_id(actual) != ident
    ):
        raise ValueError("associated client read differs")
    return actual


class Identity:
    def __init__(self, descriptor):
        self.descriptor = validate_descriptor(descriptor)
        self.RESOURCE = self.descriptor['resource']['clientId']
        self.SCOPE = self.descriptor['scope']['name']
        self.REQUESTER = self.descriptor['requester']
        self.ROLE = self.descriptor['role']['name']

    def resource_body(self):
        return deepcopy(self.descriptor['resource'])

    def scope_body(self):
        return deepcopy(self.descriptor['scope'])

    def role_body(self):
        return deepcopy(self.descriptor['role'])

    def verify_resource(self, api, actual):
        for key, value in self.resource_body().items():
            if key not in {"name", "description"} and (actual.get(key) != value or type(actual.get(key)) is not type(value)):
                raise ValueError("existing resource client conflicts")
        if actual.get("implicitFlowEnabled", False) is not False:
            raise ValueError("resource permits implicit flow")
        if rows(api.call("clients/" + object_id(actual) + "/protocol-mappers/models")):
            raise ValueError("resource has unexpected mappers")


    def verify_scope(self, api, summary):
        ident = object_id(summary)
        actual = api.call("client-scopes/" + ident)
        if (
            not isinstance(actual, dict)
            or object_id(actual) != ident
            or actual.get("name") != self.SCOPE
            or actual.get("protocol") != "openid-connect"
        ):
            raise ValueError("existing scope identity/protocol conflicts")
        attributes = deepcopy(actual.get("attributes", {}))
        # Keycloak's UI can materialize the false consent-screen default. It does
        # not broaden the scope or change the controller's audience semantics.
        if attributes.get("display.on.consent.screen") == "false":
            attributes.pop("display.on.consent.screen")
        if attributes != self.scope_body()["attributes"]:
            raise ValueError("existing scope attributes conflict")
        mappers = deepcopy(
            rows(api.call("client-scopes/" + ident + "/protocol-mappers/models"))
        )
        if len(mappers) != 1:
            raise ValueError("scope must contain exactly one mapper")
        mapper = mappers[0]
        mapper.pop("id", None)
        if mapper.get("consentRequired") is False:
            mapper.pop("consentRequired")
        config = mapper.get("config")
        if not isinstance(config, dict):
            raise ValueError("mapper config missing")
        # AbstractOIDCProtocolMapper may expose userinfo's id-token=false default;
        # an empty optional client audience is equivalent to it being absent.
        if config.get("userinfo.token.claim") == "false":
            config.pop("userinfo.token.claim")
        if config.get("included.client.audience") == "":
            config.pop("included.client.audience")
        if mapper != self.scope_body()["protocolMappers"][0]:
            raise ValueError("existing mapper conflicts with exact controller audience")
        return ident


    def find_role(self, api):
        # New realm roles cannot be created by the controller's current narrow admin
        # grants (Keycloak26.8.1 RoleContainerResource -> requireManage(RealmModel)).
        found = [
            role
            for role in rows(
                api.call("roles?search=" + self.ROLE + "&briefRepresentation=false")
            )
            if role.get("name") == self.ROLE
        ]
        if len(found) > 1:
            raise ValueError("realm role identity is ambiguous")
        if not found:
            return None
        ident = object_id(found[0])
        actual = api.call("roles/" + self.ROLE)
        if (
            not isinstance(actual, dict)
            or object_id(actual) != ident
            or actual.get("name") != self.ROLE
            or actual.get("clientRole") is not False
            or actual.get("composite") is not False
            or actual.get("attributes", {})
        ):
            raise ValueError(
                "existing realm role conflicts with exact noncomposite backend role"
            )
        if rows(api.call("roles-by-id/" + ident + "/composites")):
            raise ValueError("backend realm role has unexpected composites")
        return ident


    def inspect(self, api):
        role_id = self.find_role(api)
        resource = find_client(api, self.RESOURCE)
        if resource is not None:
            self.verify_resource(api, resource)
        found = [s for s in rows(api.call("client-scopes")) if s.get("name") == self.SCOPE]
        if len(found) > 1:
            raise ValueError("scope name is ambiguous")
        sid = self.verify_scope(api, found[0]) if found else None
        requester = find_client(api, self.REQUESTER)
        if (
            requester is None
            or any(
                requester.get(key) != value
                for key, value in {
                    "enabled": True,
                    "protocol": "openid-connect",
                    "publicClient": False,
                    "serviceAccountsEnabled": True,
                }.items()
            )
            or requester.get("attributes", {}).get("standard.token.exchange.enabled")
            != "true"
        ):
            raise ValueError("exact enabled APS exchange requester required")
        if any(
            requester.get(key, False) is not False
            for key in (
                "bearerOnly",
                "standardFlowEnabled",
                "implicitFlowEnabled",
                "directAccessGrantsEnabled",
            )
        ):
            raise ValueError("APS requester flow settings conflict")
        rid = object_id(requester)
        attachments = {}
        attachment_ids = {}
        attachment_names = {}
        for kind in ("default", "optional"):
            values = rows(api.call(f"clients/{rid}/{kind}-client-scopes"))
            if len({v.get("name") for v in values}) != len(values) or len(
                {object_id(v) for v in values}
            ) != len(values):
                raise ValueError("ambiguous scope attachments")
            matched = [
                v
                for v in values
                if v.get("name") == self.SCOPE or (sid is not None and v["id"] == sid)
            ]
            if any(v.get("name") != self.SCOPE or v["id"] != sid for v in matched):
                raise ValueError("scope attachment identity conflicts")
            attachments[kind] = matched
            attachment_ids[kind] = {v["id"] for v in values}
            attachment_names[kind] = {v["id"]: v.get("name") for v in values}
        if attachments["default"]:
            raise ValueError("backend scope must remain optional on APS")
        planned = []
        if role_id is None:
            planned.append("create_role")
        if resource is None:
            planned.append("create_resource")
        if sid is None:
            planned.append("create_scope")
        if not attachments["optional"]:
            planned.append("attach_aps_optional")
        return {
            "role_id": role_id,
            "resource_id": object_id(resource) if resource else None,
            "scope_id": sid,
            "requester_id": rid,
            "planned": planned,
            "attachment_ids": attachment_ids,
            "attachment_names": attachment_names,
        }


    def configure(self, api, *, apply=False):
        before = self.inspect(api)  # Validate ALL existing semantics before ANY mutation.
        changed = []
        current = before
        if apply:
            for operation in before["planned"]:
                if operation == "create_role":
                    api.call("roles", method="POST", payload=self.role_body())
                elif operation == "create_resource":
                    api.call("clients", method="POST", payload=self.resource_body())
                elif operation == "create_scope":
                    api.call("client-scopes", method="POST", payload=self.scope_body())
                else:
                    if current["scope_id"] is None:
                        raise ValueError("created scope identity not confirmed")
                    api.call(
                        f"clients/{current['requester_id']}/optional-client-scopes/{current['scope_id']}",
                        method="PUT",
                    )
                previous = current
                current = self.inspect(
                    api
                )  # Exact associated readbacks; never repair conflicts.
                expected_optional = previous["attachment_ids"]["optional"] | (
                    {previous["scope_id"]} if operation == "attach_aps_optional" else set()
                )
                if (
                    current["attachment_ids"]["default"]
                    != previous["attachment_ids"]["default"]
                    or current["attachment_ids"]["optional"] != expected_optional
                    or any(current["attachment_names"][kind].get(ident) != name
                           for kind in ("default", "optional")
                           for ident, name in previous["attachment_names"][kind].items())
                ):
                    raise ValueError(
                        "unrelated APS scope attachment changed during mutation"
                    )
                if operation in current["planned"]:
                    raise ValueError(
                        "mutation readback did not confirm requested operation"
                    )
                changed.append(operation)
            if current["planned"]:
                raise ValueError("backend bootstrap remains incomplete")
        return {
            "mode": "apply" if apply else "read-only-plan",
            "resource": self.RESOURCE,
            "scope": self.SCOPE,
            "requester": self.REQUESTER,
            "planned": before["planned"],
            "changed": changed,
            "role": self.ROLE,
            "role_id": current["role_id"],
            "resource_id": current["resource_id"],
            "scope_id": current["scope_id"],
        }


def configure(api, descriptor, *, apply=False):
    return Identity(descriptor).configure(api, apply=apply)

def admin():
    spec = importlib.util.spec_from_file_location(
        "db_admin_delegation_auth",
        Path(__file__).resolve().parent.parent / "conformance-delegation.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Admin()
