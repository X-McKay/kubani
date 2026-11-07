import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'infrastructure/scripts/ops'))
from mcp_registry import identity
from test_db_admin_identity import Admin, helper

class GenericIdentity(unittest.TestCase):
    def test_descriptor_rejects_broad_admin_fields_before_reads(self):
        descriptor = helper.descriptor()
        descriptor['resource']['authorizationServicesEnabled'] = True
        api = Admin()
        with self.assertRaises(ValueError):
            identity.configure(api, descriptor, apply=True)
        self.assertEqual(api.calls, [])

    def test_second_backend_plan_is_independent(self):
        descriptor = helper.descriptor()
        text = __import__('json').dumps(descriptor).replace('postgres-admin', 'warehouse')
        result = identity.configure(Admin(), __import__('json').loads(text))
        self.assertEqual(result['scope'], 'mcp:warehouse')
        self.assertEqual(helper.SCOPE, 'mcp:postgres-admin')

    def test_partial_failure_requires_fresh_inspection_on_retry(self):
        api = Admin()
        original = api.call
        def fail(path, **kwargs):
            if path == 'clients' and kwargs.get('method') == 'POST':
                raise RuntimeError('PRIVATE credential response')
            return original(path, **kwargs)
        api.call = fail
        with self.assertRaises(RuntimeError):
            identity.configure(api, helper.descriptor(), apply=True)
        self.assertIsNotNone(api.role)
        api.call = original
        result = identity.configure(api, helper.descriptor())
        self.assertNotIn('create_role', result['planned'])
        self.assertNotIn('PRIVATE', str(result))
        self.assertEqual(identity.configure(api, helper.descriptor(), apply=True)['changed'], ['create_resource','create_scope','attach_aps_optional'])

    def test_unrelated_attachment_rename_detected_after_write(self):
        api = Admin()
        api.optional = [{'id':'keep','name':'keep'}]
        original=api.call
        def rename(path, **kwargs):
            result=original(path, **kwargs)
            if kwargs.get('method') == 'PUT':
                api.optional[0]['name']='changed'
            return result
        api.call=rename
        with self.assertRaises(ValueError):
            identity.configure(api, helper.descriptor(), apply=True)

    def test_second_descriptor_apply_and_idempotence(self):
        import json
        descriptor = json.loads(json.dumps(helper.descriptor()).replace('postgres-admin','warehouse'))
        api = Admin()
        original = api.call
        # Reuse the legacy transport fixture with bidirectional identity mapping.
        def translate(value, old, new):
            if isinstance(value,str): return value.replace(old,new)
            if isinstance(value,list): return [translate(v,old,new) for v in value]
            if isinstance(value,dict): return {k:translate(v,old,new) for k,v in value.items()}
            return value
        def call(path, **kwargs):
            request = translate(kwargs,'warehouse','postgres-admin')
            result = original(path.replace('warehouse','postgres-admin'), **request)
            return translate(result,'postgres-admin','warehouse')
        api.call=call
        first=identity.configure(api, descriptor, apply=True)
        self.assertEqual(first['role'],'agent-role-warehouse-read')
        self.assertEqual(len(first['changed']),4)
        self.assertEqual(identity.configure(api, descriptor, apply=True)['changed'],[])
        self.assertEqual(helper.configure(Admin())['scope'],'mcp:postgres-admin')
