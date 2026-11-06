"""Inactive T27 jobs bind two exact sessions without host or receipt-write rights."""
import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'infrastructure/gitops/apps/agent-platform/conformance/transport'
IMAGE = 'registry.almckay.io/platform/session-runner:test@sha256:' + 'a9' * 32
VALUES = {
    'TRANSPORT_RUN_ID': '4bc9beea-e690-43eb-bf58-211044970094',
    'TRANSPORT_SESSION_ID': 'ce1099aa-252b-4a0d-b66d-120a5a3b4d67',
    'T4_SESSION_ID': '75abc4ab-4e05-4d21-bf83-b18c8335948b',
    'TRANSPORT_RELEASE': 'conformance-transport-signed',
    'T4_RELEASE': 'conformance-signed',
    'TRANSPORT_RUNNER_IMAGE': IMAGE,
}


def render(name):
    text = (DIRECTORY / name).read_text()
    for key, value in VALUES.items():
        text = text.replace('${' + key + '}', value)
    assert '${' not in text
    return list(yaml.safe_load_all(text))


class TransportTemplates(unittest.TestCase):
    def test_jobs_are_suspended_unlisted_and_have_no_host_privilege(self):
        for role in ('worker', 'harness'):
            job = render(role + '-job.yaml.in')[0]
            self.assertIs(job['spec']['suspend'], True)
            self.assertEqual(job['spec']['backoffLimit'], 0)
            pod = job['spec']['template']['spec']
            self.assertEqual(pod['serviceAccountName'], 'session-runner' if role == 'worker' else 'conformance-harness')
            self.assertEqual(pod['nodeSelector']['topology.kubani.io/role'], 'database')
            self.assertFalse(pod.get('hostNetwork', False))
            self.assertFalse(pod.get('hostPID', False))
            self.assertFalse(any('hostPath' in volume for volume in pod['volumes']))
            container = pod['containers'][0]
            self.assertEqual(container['image'], IMAGE)
            self.assertFalse(container['securityContext']['allowPrivilegeEscalation'])
            self.assertFalse(container['securityContext'].get('privileged', False))
            self.assertEqual(container['securityContext']['capabilities'], {'drop': ['ALL']})
            artifacts = next(v for v in container['volumeMounts'] if v['name'] == 'artifacts')
            self.assertEqual(artifacts.get('readOnly', False), role == 'harness')
            env = {v['name']: v for v in container['env']}
            if role == 'worker':
                self.assertEqual(container['command'][-1], 'runner.conformance_transport_worker')
                self.assertEqual(env['POD_UID']['valueFrom']['fieldRef']['fieldPath'], 'metadata.uid')
                self.assertEqual(env['TRANSPORT_RUN_ID']['value'], VALUES['TRANSPORT_RUN_ID'])
            else:
                self.assertEqual(container['args'][container['args'].index('--tests') + 1], 'T27')
                self.assertEqual(container['args'][container['args'].index('--agent') + 1], 'conformance')
                self.assertIn('--observe-host-capture', container['args'])
                self.assertEqual(container['args'][container['args'].index('--session-timeout') + 1], '900')
                self.assertEqual(env['ISSUER_URL']['value'], 'https://idp.almckay.io/realms/agents')
                self.assertEqual({v['name'] for v in pod['volumes']}, {'temporal-tls', 'payload-key', 'tmp', 'artifacts'})
        for path in (ROOT / 'infrastructure/gitops').rglob('kustomization.yaml'):
            self.assertNotIn('conformance/transport', path.read_text())

    def test_workloads_only_read_exact_control_and_releases(self):
        docs = render('rbac.yaml.in')
        self.assertEqual({d['kind'] for d in docs}, {'Role', 'RoleBinding'})
        roles = [d for d in docs if d['kind'] == 'Role']
        control = next(d for d in roles if d['metadata']['namespace'] == 'agent-platform')
        self.assertEqual(control['rules'], [{'apiGroups': [''], 'resources': ['configmaps'],
                                          'resourceNames': ['conformance-transport-control'], 'verbs': ['get']}])
        tenant = next(d for d in roles if d['metadata']['namespace'] == 'tenant-test')
        release = next(r for r in tenant['rules'] if r['resources'] == ['agentreleases'])
        self.assertEqual(release['resourceNames'], [VALUES['TRANSPORT_RELEASE'], VALUES['T4_RELEASE']])
        self.assertEqual(release['verbs'], ['get'])
        for role in roles:
            for rule in role['rules']:
                self.assertLessEqual(set(rule['verbs']), {'get', 'list'})
                self.assertNotIn('secrets', rule['resources'])

    def test_control_pins_same_two_sessions_queue_image_and_no_receipts(self):
        cm = render('control.yaml.in')[0]
        self.assertEqual(cm['metadata'], {'name': 'conformance-transport-control', 'namespace': 'agent-platform'})
        self.assertEqual(set(cm['data']), {'config'})
        cfg = json.loads(cm['data']['config'])
        self.assertEqual(cfg['sessions'], {'transport': VALUES['TRANSPORT_SESSION_ID'], 't4': VALUES['T4_SESSION_ID']})
        self.assertEqual(cfg['queue'], 'conformance-transport-' + VALUES['TRANSPORT_RUN_ID'])
        self.assertEqual(cfg['worker_image'], IMAGE)
        self.assertEqual(cfg['transport_release'], VALUES['TRANSPORT_RELEASE'])
        self.assertEqual(cfg['t4_release'], VALUES['T4_RELEASE'])
