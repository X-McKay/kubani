"""Bounded read-only registration evidence; never proof of a successful tool call.

The callback returns public Kubernetes objects only. Explicit Secret objects are refused before invoking it. Derived Secret
references use a caller-guaranteed metadata-only existence transport. Unknown extra configuration fails closed; only documented API
server defaults and controller-assigned fields below are normalized.
"""
from __future__ import annotations

from copy import deepcopy
from ipaddress import ip_address
from . import identity

# API-server defaults, accepted only at these exact semantic locations.
POD_DEFAULTS = {
    'restartPolicy': 'Always', 'dnsPolicy': 'ClusterFirst',
    'schedulerName': 'default-scheduler', 'terminationGracePeriodSeconds': 30,
    'enableServiceLinks': True, 'securityContext': {}, 'hostNetwork': False,
    'hostPID': False, 'hostIPC': False, 'shareProcessNamespace': False,
    'serviceAccountName': 'default', 'serviceAccount': 'default',
}
CONTAINER_DEFAULTS = {
    'terminationMessagePath': '/dev/termination-log',
    'terminationMessagePolicy': 'File', 'imagePullPolicy': 'IfNotPresent',
    'resources': {}, 'stdin': False, 'stdinOnce': False, 'tty': False,
}
METADATA_SERVER_FIELDS = {
    'uid', 'resourceVersion', 'generation', 'creationTimestamp',
    'managedFields', 'selfLink',
}
JOB_LABELS = {
    'batch.kubernetes.io/controller-uid', 'controller-uid',
    'batch.kubernetes.io/job-name', 'job-name',
}


def _defaults(actual, desired, defaults):
    for key, value in defaults.items():
        if key not in desired and actual.get(key) == value:
            actual.pop(key)


def _metadata(actual, desired, *, job=False, top=False):
    for key in METADATA_SERVER_FIELDS:
        if key not in desired:
            actual.pop(key, None)
    # Flux inventory labels on object metadata do not change runtime specs.
    # Pod-template metadata deliberately does not get this normalization.
    if top:
        for key in ('kustomize.toolkit.fluxcd.io/name', 'kustomize.toolkit.fluxcd.io/namespace'):
            if key not in desired.get('labels', {}):
                actual.get('labels', {}).pop(key, None)
    # Flux/kubectl housekeeping does not affect runtime authority. Other
    # annotations (including bootstrap hashes) and labels remain compared.
    annotations = actual.get('annotations', {})
    for key in ('kubectl.kubernetes.io/last-applied-configuration',
                'deployment.kubernetes.io/revision'):
        if key not in desired.get('annotations', {}):
            annotations.pop(key, None)
    for key in ('annotations', 'labels'):
        if key not in desired and actual.get(key) == {}:
            actual.pop(key)
    if 'namespace' not in desired and actual.get('namespace') == 'default':
        actual.pop('namespace')


def _pod(actual, desired):
    _defaults(actual, desired, POD_DEFAULTS)
    for key in ('containers', 'initContainers'):
        for container, wanted in zip(actual.get(key, []), desired.get(key, [])):
            _defaults(container, wanted, CONTAINER_DEFAULTS)
            for port, expected in zip(container.get('ports', []), wanted.get('ports', [])):
                _defaults(port, expected, {'protocol': 'TCP'})
            for probe in ('readinessProbe', 'livenessProbe', 'startupProbe'):
                if probe in container and probe in wanted:
                    _defaults(container[probe], wanted[probe], {
                        'timeoutSeconds': 1, 'periodSeconds': 10,
                        'successThreshold': 1, 'failureThreshold': 3,
                    })
                    if 'httpGet' in container[probe] and 'httpGet' in wanted[probe]:
                        _defaults(container[probe]['httpGet'], wanted[probe]['httpGet'], {'scheme':'HTTP'})
    for volume, wanted in zip(actual.get('volumes', []), desired.get('volumes', [])):
        for key in ('secret', 'configMap'):
            if key in volume and key in wanted:
                _defaults(volume[key], wanted[key], {'defaultMode': 420})


def _matches(live, desired):
    actual = deepcopy(live)
    wanted = deepcopy(desired)
    actual.pop('status', None)
    wanted.pop('status', None)
    kind = wanted['kind']
    _metadata(actual.setdefault('metadata', {}), wanted.get('metadata', {}), top=True)
    spec = actual.get('spec', {})
    desired_spec = wanted.get('spec', {})
    if kind in ('Deployment', 'Job'):
        template = spec.get('template', {})
        desired_template = desired_spec.get('template', {})
        if kind == 'Job':
            labels = template.get('metadata', {}).get('labels', {})
            for key in JOB_LABELS:
                generated = live.get('metadata', {}).get('uid') if 'uid' in key else live.get('metadata', {}).get('name')
                if key not in desired_template.get('metadata', {}).get('labels', {}) and labels.get(key) == generated:
                    labels.pop(key, None)
        _metadata(template.setdefault('metadata', {}), desired_template.get('metadata', {}))
        if not template.get('metadata') and 'metadata' not in desired_template:
            template.pop('metadata', None)
        _pod(template.get('spec', {}), desired_template.get('spec', {}))
    if kind == 'Deployment':
        _defaults(spec, desired_spec, {
            'replicas': 1, 'revisionHistoryLimit': 10, 'progressDeadlineSeconds': 600,
            'strategy': {'type':'RollingUpdate', 'rollingUpdate':{'maxSurge':'25%', 'maxUnavailable':'25%'}},
        })
    elif kind == 'Job':
        _defaults(spec, desired_spec, {'backoffLimit':6, 'completions':1, 'parallelism':1,
                  'completionMode':'NonIndexed', 'suspend':False, 'manualSelector':False,
                  'podReplacementPolicy':'TerminatingOrFailed'})
        if 'selector' not in desired_spec:
            selector = spec.get('selector', {})
            labels = selector.get('matchLabels', {})
            uid = live.get('metadata', {}).get('uid')
            # Only remove the API-generated selector tied to this Job's UID.
            if selector and set(selector) == {'matchLabels'} and labels and all(k in JOB_LABELS and v == uid for k,v in labels.items()):
                spec.pop('selector')
    elif kind == 'Service':
        _defaults(spec, desired_spec, {'type':'ClusterIP', 'sessionAffinity':'None',
                  'internalTrafficPolicy':'Cluster', 'ipFamilyPolicy':'SingleStack'})
        # Only real IP allocations are server-assigned. The string "None"
        # denotes meaningful headless routing and must remain compared.
        try:
            primary_value = spec['clusterIP']
            values = spec.get('clusterIPs', [primary_value])
            if (not isinstance(primary_value, str) or not isinstance(values, list)
                    or not 1 <= len(values) <= 2 or any(not isinstance(value, str) for value in values)):
                raise ValueError('invalid IP allocation')
            primary = ip_address(primary_value)
            addresses = [ip_address(value) for value in values]
            families = ['IPv' + str(address.version) for address in addresses]
            allocated = addresses[0] == primary and len(set(families)) == len(families)
        except (KeyError, ValueError, TypeError):
            allocated = False
        if allocated:
            for key in ('clusterIP', 'clusterIPs'):
                if key not in desired_spec:
                    spec.pop(key, None)
            if 'ipFamilies' not in desired_spec and spec.get('ipFamilies') == families:
                spec.pop('ipFamilies')
        for port, expected in zip(spec.get('ports', []), desired_spec.get('ports', [])):
            _defaults(port, expected, {'protocol':'TCP', 'targetPort':expected.get('port')})
    elif kind == 'HTTPRoute':
        for ref, expected in zip(spec.get('parentRefs', []), desired_spec.get('parentRefs', [])):
            _defaults(ref, expected, {'group':'gateway.networking.k8s.io','kind':'Gateway'})
        for rule, expected_rule in zip(spec.get('rules', []), desired_spec.get('rules', [])):
            for ref, expected in zip(rule.get('backendRefs', []), expected_rule.get('backendRefs', [])):
                _defaults(ref, expected, {'group':'','kind':'Service','weight':1})
    elif kind == 'AgentgatewayBackend':
        if 'mcp' in spec and 'mcp' in desired_spec:
            _defaults(spec['mcp'], desired_spec['mcp'], {'failureMode':'FailClosed','sessionRouting':'Stateless'})
    return actual == wanted


def _conditions(conditions, generation, required):
    if not isinstance(generation, int) or generation < 1 or not isinstance(conditions, list):
        return False
    for name in required:
        found = [c for c in conditions if isinstance(c, dict) and c.get('type') == name]
        if len(found) != 1 or found[0].get('status') != 'True' or found[0].get('observedGeneration') != generation:
            return False
    return True


def _ready(live, desired, expected):
    kind = desired['kind']
    status = live.get('status', {})
    generation = live.get('metadata', {}).get('generation')
    if kind == 'Deployment':
        replicas = desired.get('spec', {}).get('replicas', 1)
        return (isinstance(generation, int) and generation > 0
                and status.get('observedGeneration') == generation
                and all(status.get(key, 0) == replicas for key in
                        ('replicas','updatedReplicas','availableReplicas','readyReplicas'))
                and status.get('unavailableReplicas', 0) == 0)
    if kind == 'Job':
        conditions = status.get('conditions', [])
        return (sum(c.get('type') == 'Complete' and c.get('status') == 'True' for c in conditions) == 1
                and not any(c.get('type') == 'Failed' and c.get('status') == 'True' for c in conditions))
    if kind == 'HTTPRoute':
        parents = status.get('parents', [])
        desired_parents = desired.get('spec', {}).get('parentRefs', [])
        if not desired_parents:
            return False
        def parent_key(ref):
            return (ref.get('group','gateway.networking.k8s.io'), ref.get('kind','Gateway'),
                    ref.get('namespace', desired.get('metadata', {}).get('namespace','default')),
                    ref.get('name'), ref.get('sectionName'), ref.get('port'))
        for ref in desired_parents:
            matches = [p for p in parents if parent_key(p.get('parentRef', {})) == parent_key(ref)]
            if len(matches) != 1 or matches[0].get('controllerName') != 'agentgateway.dev/agentgateway' or not _conditions(matches[0].get('conditions'), generation, ('Accepted','ResolvedRefs')):
                return False
        return True
    if kind == 'AgentgatewayBackend':
        return _conditions(status.get('conditions'), generation, ('Accepted',))
    if kind == 'AgentgatewayPolicy':
        gateways = _policy_gateways(desired, expected)
        if not gateways:
            return False
        ancestors = status.get('ancestors', [])
        for namespace, name in gateways:
            matching = [a for a in ancestors
                        if a.get('controllerName') == 'agentgateway.dev/agentgateway'
                        and a.get('ancestorRef', {}).get('group','gateway.networking.k8s.io') == 'gateway.networking.k8s.io'
                        and a.get('ancestorRef', {}).get('kind','Gateway') == 'Gateway'
                        and a.get('ancestorRef', {}).get('name') == name
                        and a.get('ancestorRef', {}).get('namespace',desired.get('metadata',{}).get('namespace','default')) == namespace]
            if len(matching) != 1 or not _conditions(matching[0].get('conditions'), generation, ('Accepted','Attached')):
                return False
        return True
    return True


def _policy_gateways(policy, expected):
    """Resolve policy targets through desired routes to the expected Gateway."""
    namespace = policy.get('metadata', {}).get('namespace','default')
    routes = [o for o in expected if o.get('kind') == 'HTTPRoute']
    result = set()
    for target in policy.get('spec', {}).get('targetRefs', []):
        target_ns = target.get('namespace', namespace)
        if target.get('kind') == 'Gateway':
            result.add((target_ns, target.get('name')))
            continue
        for route in routes:
            route_ns = route.get('metadata', {}).get('namespace','default')
            match = (target.get('kind') == 'HTTPRoute' and route_ns == target_ns
                     and route['metadata']['name'] == target.get('name'))
            if target.get('kind') == 'AgentgatewayBackend':
                match = any(ref.get('kind','Service') == 'AgentgatewayBackend'
                            and ref.get('name') == target.get('name')
                            and ref.get('namespace',route_ns) == target_ns
                            for rule in route.get('spec',{}).get('rules',[])
                            for ref in rule.get('backendRefs',[]))
            if match:
                result.update((ref.get('namespace',route_ns), ref.get('name'))
                              for ref in route.get('spec',{}).get('parentRefs',[])
                              if ref.get('kind','Gateway') == 'Gateway'
                              and ref.get('group','gateway.networking.k8s.io') == 'gateway.networking.k8s.io')
    return result


def _secret_refs(expected):
    refs = set()
    def walk(value, namespace):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('secretKeyRef','secretRef') and isinstance(child,dict) and isinstance(child.get('name'),str):
                    refs.add((namespace,child['name']))
                elif key == 'secret' and isinstance(child,dict):
                    # Ordinary volume sources use secretName; projected volume
                    # sources use name. Both require metadata-only existence.
                    name = child.get('secretName', child.get('name'))
                    if isinstance(name, str):
                        refs.add((namespace,name))
                elif key == 'imagePullSecrets' and isinstance(child,list):
                    refs.update((namespace,ref['name']) for ref in child if isinstance(ref,dict) and isinstance(ref.get('name'),str))
                walk(child, namespace)
        elif isinstance(value,list):
            for child in value:
                walk(child, namespace)
    for obj in expected:
        if obj.get('kind') in ('Deployment','Job'):
            walk(obj.get('spec',{}), obj.get('metadata',{}).get('namespace','default'))
    return refs


def inspect_registration(expected, descriptor, *, read_object, api):
    """Inspect bounded public resource layers and exact Keycloak semantics.

    Transport errors are summarized without exception messages/raw API bodies.
    Desired input must be the caller's validated complete effective public set.
    """
    identity.validate_descriptor(descriptor)
    if not isinstance(expected, list) or not expected or len(expected) > 256:
        raise ValueError('invalid bounded public object set')
    layers = []
    seen = set()
    for desired in expected:
        if not isinstance(desired, dict):
            raise ValueError('invalid public object')
        metadata = desired.get('metadata', {})
        key = (desired.get('apiVersion'), desired.get('kind'), metadata.get('namespace',''), metadata.get('name'))
        if any(not isinstance(x,str) or len(x) > 253 for x in key) or not key[0] or not key[1] or not key[3] or key in seen:
            raise ValueError('invalid or duplicate public object identity')
        seen.add(key)
        layer = {'layer':key[1], 'namespace':key[2], 'name':key[3], 'complete':False}
        if key[1] not in {'Deployment','Service','HTTPRoute','AgentgatewayBackend','AgentgatewayPolicy','NetworkPolicy','Job','ConfigMap'}:
            layer['state']='unsupported-public-kind'
            layers.append(layer)
            continue
        try:
            live = read_object(*key)
            if live is None:
                layer['state']='missing'
            elif not isinstance(live,dict) or not _matches(live, desired):
                layer['state']='configuration-mismatch'
            elif not _ready(live, desired, expected):
                layer['state']='not-current-or-ready'
            else:
                layer.update(state='current', complete=True)
        except Exception:
            layer['state']='unavailable'
        layers.append(layer)
    # The caller guarantees a metadata-only transport for these derived reads.
    # Reject any accidental secret body without examining or returning its data.
    for namespace, name in sorted(_secret_refs(expected)):
        layer = {'layer':'SecretReference','namespace':namespace,'name':name,'complete':False}
        try:
            public = read_object('v1','Secret',namespace,name)
            if public is None:
                layer['state']='missing'
            elif (not isinstance(public,dict) or set(public) - {'apiVersion','kind','metadata'}
                  or public.get('kind') != 'Secret' or public.get('apiVersion') != 'v1'
                  or public.get('metadata') != {'name':name,'namespace':namespace}):
                layer['state']='invalid-metadata-only-response'
            else:
                layer.update(state='present',complete=True)
        except Exception:
            layer['state']='unavailable'
        layers.append(layer)
    try:
        plan = identity.configure(api, descriptor)
        pending = plan['planned']
        layers.append({'layer':'identity', 'complete':not pending, 'state':'incomplete' if pending else 'current', 'planned':pending})
    except Exception:
        layers.append({'layer':'identity', 'complete':False, 'state':'unavailable-or-conflicting'})
    return {'complete':all(layer['complete'] for layer in layers), 'functional':'not-tested', 'layers':layers}
