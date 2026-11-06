"""Inactive T23 templates retain exact bindings and separate harness/worker identities."""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'infrastructure/gitops/apps/agent-platform/conformance/checkpoint'
IMAGE = 'registry.almckay.io/platform/session-runner:test@sha256:' + 'a9' * 32


def render(name):
    text = (DIRECTORY / name).read_text()
    for key, value in {'CHECKPOINT_RUN_ID': '4bc9beea-e690-43eb-bf58-211044970094',
                       'CHECKPOINT_RELEASE': 'conformance-checkpoint-signed',
                       'CHECKPOINT_RUNNER_IMAGE': IMAGE}.items():
        text = text.replace('${' + key + '}', value)
    assert '${' not in text
    return list(yaml.safe_load_all(text))


class CheckpointTemplates(unittest.TestCase):
    def test_jobs_are_inactive_and_use_same_image_and_different_identities(self):
        for role in ('worker', 'harness'):
            job = render(role + '-job.yaml.in')[0]
            self.assertIs(job['spec']['suspend'], True)
            pod = job['spec']['template']['spec']
            self.assertEqual(pod['serviceAccountName'], 'session-runner' if role == 'worker' else 'conformance-harness')
            self.assertEqual(pod['nodeSelector']['topology.kubani.io/role'], 'database')
            container = pod['containers'][0]
            self.assertEqual(container['image'], IMAGE)
            self.assertIn('--allow-checkpoint-faults', container['args'])
            artifacts = next(v for v in container['volumeMounts'] if v['name'] == 'artifacts')
            self.assertEqual(artifacts.get('readOnly', False), role == 'harness')
            if role == 'harness':
                self.assertEqual({v['name'] for v in pod['volumes']}, {'temporal-tls', 'payload-key', 'tmp', 'artifacts'})
        for path in (ROOT / 'infrastructure/gitops').rglob('kustomization.yaml'):
            self.assertNotIn('conformance/checkpoint', path.read_text())

    def test_harness_gains_no_pod_mutation_secret_or_cluster_access(self):
        docs = render('rbac.yaml.in')
        self.assertEqual({d['kind'] for d in docs}, {'Role', 'RoleBinding'})
        for role in [d for d in docs if d['kind'] == 'Role']:
            for rule in role['rules']:
                self.assertNotIn('secrets', rule['resources'])
                if 'patch' in rule['verbs']:
                    self.assertEqual(rule['resources'], ['configmaps'])
                    self.assertEqual(rule['resourceNames'], ['conformance-checkpoint-control'])
                    self.assertEqual(role['metadata']['namespace'], 'agent-platform')
                else:
                    self.assertLessEqual(set(rule['verbs']), {'get', 'list'})
