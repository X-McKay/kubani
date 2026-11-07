import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'infrastructure/scripts/ops'))
from mcp_registry.status import inspect_registration
from test_db_admin_identity import Admin, helper

class StatusTests(unittest.TestCase):
    def setUp(self):
        self.api=Admin()
        helper.configure(self.api, apply=True)
        self.api.calls.clear()
        self.expected=[{'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'backend','namespace':'mcp'},'spec':{'replicas':1,'selector':{'matchLabels':{'app':'backend'}},'template':{'metadata':{'labels':{'app':'backend'}},'spec':{'containers':[{'name':'server','image':'image@sha256:123','ports':[{'containerPort':8000}]}]}}}}]
        self.live=copy.deepcopy(self.expected[0])
        self.live['metadata']['generation']=2
        self.live['status']={'observedGeneration':2,'updatedReplicas':1,'availableReplicas':1,'readyReplicas':1,'replicas':1}
    def run_status(self, expected=None, reader=None):
        return inspect_registration(expected or self.expected, helper.descriptor(), read_object=reader or (lambda *args:self.live),api=self.api)
    def test_reloader_marker_requires_exact_reviewed_public_config(self):
        import hashlib
        cm = {'apiVersion':'v1', 'kind':'ConfigMap', 'metadata':{'name':'kubernetes-mcp-config', 'namespace':'mcp'}, 'data':{'config.toml':'read_only = true'}}
        obj = copy.deepcopy(self.expected[0])
        obj['metadata'] = {'name':'kubernetes-mcp', 'namespace':'mcp', 'annotations':{'reloader.stakater.com/auto':'true'}}
        pod = obj['spec']['template']['spec']
        pod['volumes'] = [{'name':'config', 'configMap':{'name':'kubernetes-mcp-config'}}]
        server = pod['containers'][0]
        server['name'] = 'kubernetes-mcp'
        server['volumeMounts'] = [{'name':'config', 'mountPath':'/etc/kubernetes-mcp-server', 'readOnly':True}]
        marker = {'name':'STAKATER_KUBERNETES_MCP_CONFIG_CONFIGMAP', 'value':hashlib.sha1(b'config.toml=read_only = true').hexdigest()}
        live = copy.deepcopy(obj)
        live['metadata']['generation'] = 2
        live['status'] = copy.deepcopy(self.live['status'])
        live['spec']['template']['spec']['containers'][0]['env'] = [marker]
        def run(desired=obj, actual=live, actual_cm=cm, context=True):
            expected = [desired, cm] if context else [desired]
            return self.run_status(expected, lambda version,kind,namespace,name:actual_cm if kind == 'ConfigMap' else actual)['complete']
        self.assertTrue(run())
        unmarked = copy.deepcopy(live)
        unmarked['spec']['template']['spec']['containers'][0].pop('env')
        self.assertTrue(run(actual=unmarked))
        self.assertFalse(run(context=False))
        for change in ['hash', 'duplicate', 'extra', 'container', 'annotation', 'mount']:
            actual = copy.deepcopy(live)
            server = actual['spec']['template']['spec']['containers'][0]
            if change == 'hash': server['env'][0]['value'] = '0' * 40
            if change == 'duplicate': server['env'].append(copy.deepcopy(marker))
            if change == 'extra': server['env'].append({'name':'UNREVIEWED', 'value':'extra'})
            if change == 'container': server['name'] = 'capture'
            if change == 'annotation': actual['metadata']['annotations']['reloader.stakater.com/auto'] = 'false'
            if change == 'mount': server['volumeMounts'][0]['name'] = 'other'
            self.assertFalse(run(actual=actual), change)
        changed_cm = copy.deepcopy(cm)
        changed_cm['data']['config.toml'] = 'read_only = false'
        self.assertFalse(run(actual_cm=changed_cm))
        for change in ['annotation', 'mount']:
            desired = copy.deepcopy(obj)
            actual = copy.deepcopy(live)
            if change == 'annotation':
                for value in [desired, actual]: value['metadata']['annotations']['reloader.stakater.com/auto'] = 'false'
            else:
                for value in [desired, actual]: value['spec']['template']['spec']['containers'][0]['volumeMounts'][0]['name'] = 'other'
            self.assertFalse(run(desired=desired, actual=actual), change)

    def test_matching_deprecated_service_account_alias_only(self):
        desired = self.expected[0]['spec']['template']['spec']
        desired['serviceAccountName'] = 'kubernetes-mcp'
        live = self.live['spec']['template']['spec']
        live.update(serviceAccountName='kubernetes-mcp', serviceAccount='kubernetes-mcp')
        self.assertTrue(self.run_status()['complete'])
        live['serviceAccount'] = 'other-account'
        self.assertFalse(self.run_status()['complete'])
        live['serviceAccount'] = 'kubernetes-mcp'
        live['serviceAccountName'] = 'other-account'
        self.assertFalse(self.run_status()['complete'])

    def test_service_account_authority_is_exact(self):
        obj = {'apiVersion':'v1', 'kind':'ServiceAccount', 'metadata':{'name':'server', 'namespace':'mcp'}}
        self.live = copy.deepcopy(obj)
        self.live['automountServiceAccountToken'] = True
        self.assertTrue(self.run_status([obj])['complete'])
        for field, value in [('automountServiceAccountToken', False), ('imagePullSecrets', [{'name':'extra'}]), ('secrets', [{'name':'extra'}])]:
            self.live = copy.deepcopy(obj)
            self.live[field] = value
            self.assertFalse(self.run_status([obj])['complete'])

    def test_binding_complete_subjects_and_role_ref(self):
        obj = {'apiVersion':'rbac.authorization.k8s.io/v1', 'kind':'ClusterRoleBinding', 'metadata':{'name':'binding'}, 'roleRef':{'apiGroup':'rbac.authorization.k8s.io', 'kind':'ClusterRole', 'name':'view'}, 'subjects':[{'kind':'ServiceAccount', 'name':'server', 'namespace':'mcp'}]}
        self.live = copy.deepcopy(obj)
        self.live['subjects'][0]['apiGroup'] = ''
        self.assertTrue(self.run_status([obj])['complete'])
        self.live['subjects'].append({'kind':'User', 'name':'extra', 'apiGroup':'rbac.authorization.k8s.io'})
        self.assertFalse(self.run_status([obj])['complete'])
        self.live = copy.deepcopy(obj)
        self.live['roleRef']['name'] = 'admin'
        self.assertFalse(self.run_status([obj])['complete'])
        self.live = copy.deepcopy(obj)
        self.live['metadata']['namespace'] = 'default'
        self.assertFalse(self.run_status([obj])['complete'])

    def test_external_cluster_role_projects_metadata_but_preserves_authority(self):
        obj = {'apiVersion':'rbac.authorization.k8s.io/v1', 'kind':'ClusterRole', 'metadata':{'name':'view'}, 'rules':[{'apiGroups':[''], 'resources':['pods'], 'verbs':['get','list','watch']}], 'aggregationRule':{'clusterRoleSelectors':[{'matchLabels':{'aggregate':'true'}}]}}
        self.live = copy.deepcopy(obj)
        self.live['metadata']['labels'] = {'kubernetes.io/bootstrapping':'rbac-defaults'}
        self.assertTrue(self.run_status([obj])['complete'])
        for mutate in [lambda x:x['rules'][0]['resources'].append('secrets'), lambda x:x['rules'][0]['verbs'].append('create'), lambda x:x['aggregationRule']['clusterRoleSelectors'].append({'matchLabels':{'extra':'true'}}), lambda x:x['metadata'].update(name='admin'), lambda x:x['metadata'].update(namespace='mcp')]:
            self.live = copy.deepcopy(obj)
            mutate(self.live)
            self.assertFalse(self.run_status([obj])['complete'])

    def test_structural_success_is_not_functional(self):
        result=self.run_status()
        self.assertTrue(result['complete'])
        self.assertEqual(result['functional'],'not-tested')
        self.assertEqual(self.api.writes,[])
    def test_missing_stale_and_unavailable(self):
        for reader in [lambda *a:None, lambda *a:(_ for _ in ()).throw(RuntimeError('SECRET'))]:
            result=self.run_status(reader=reader)
            self.assertFalse(result['complete'])
            self.assertNotIn('SECRET',str(result))
        self.live['status']['observedGeneration']=1
        self.assertFalse(self.run_status()['complete'])
    def test_changed_container_or_extra_authority_is_incomplete(self):
        self.live['spec']['template']['spec']['containers'][0]['image']='different'
        self.assertFalse(self.run_status()['complete'])
        self.live=copy.deepcopy(self.expected[0])
        self.live['spec']['template']['spec']['hostNetwork']=True
        self.assertFalse(self.run_status()['complete'])
    def test_service_and_policy_changes_are_incomplete(self):
        for kind in ['Service','NetworkPolicy','AgentgatewayPolicy']:
            obj={'apiVersion':'v1','kind':kind,'metadata':{'name':'x'},'spec':{'ports':[{'port':80}]}}
            self.live=copy.deepcopy(obj)
            self.live['spec']['ports'][0]['port']=81
            self.assertFalse(self.run_status([obj])['complete'])
    def test_route_conditions_must_be_current_and_both_true(self):
        obj={'apiVersion':'gateway.networking.k8s.io/v1','kind':'HTTPRoute','metadata':{'name':'route'},'spec':{'parentRefs':[{'name':'gateway'}],'rules':[]}}
        self.live=copy.deepcopy(obj)
        self.live['metadata']['generation']=3
        conditions=[{'type':t,'status':'True','observedGeneration':3} for t in ['Accepted','ResolvedRefs']]
        self.live['status']={'parents':[{'parentRef':{'name':'gateway'},'controllerName':'agentgateway.dev/agentgateway','conditions':conditions}]}
        self.assertTrue(self.run_status([obj])['complete'])
        conditions[1]['observedGeneration']=2
        self.assertFalse(self.run_status([obj])['complete'])
    def test_bootstrap_job_and_configmap_exact(self):
        obj={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':'bootstrap-v1'},'spec':{'template':{'spec':{'containers':[{'name':'sql','image':'postgres','command':['psql']}],'restartPolicy':'Never'}}}}
        self.live=copy.deepcopy(obj)
        self.live['status']={'conditions':[{'type':'Complete','status':'True'}]}
        self.assertTrue(self.run_status([obj])['complete'])
        self.live['status']={}
        self.assertFalse(self.run_status([obj])['complete'])
        cm={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'sql'},'data':{'sql':'approved'}}
        self.live=copy.deepcopy(cm); self.live['data']['sql']='changed'
        self.assertFalse(self.run_status([cm])['complete'])
    def test_identity_gap_and_no_secret_reads(self):
        self.api.scope['protocolMappers'][0]['config']['access.token.claim']='false'
        self.assertFalse(self.run_status()['complete'])
        reads=[]
        obj={'apiVersion':'v1','kind':'Secret','metadata':{'name':'secret'}}
        result=self.run_status([obj],lambda *a:reads.append(a))
        self.assertFalse(result['complete'])
        self.assertEqual(reads,[])

    def test_backend_only_accepted_and_policy_exact_ancestor(self):
        backend={'apiVersion':'agentgateway.dev/v1alpha1','kind':'AgentgatewayBackend','metadata':{'name':'b','namespace':'ai-gateway'},'spec':{'mcp':{}}}
        route={'apiVersion':'gateway.networking.k8s.io/v1','kind':'HTTPRoute','metadata':{'name':'r','namespace':'ai-gateway'},'spec':{'parentRefs':[{'name':'agents'}],'rules':[{'backendRefs':[{'kind':'AgentgatewayBackend','name':'b'}]}]}}
        policy={'apiVersion':'agentgateway.dev/v1alpha1','kind':'AgentgatewayPolicy','metadata':{'name':'p','namespace':'ai-gateway'},'spec':{'targetRefs':[{'kind':'AgentgatewayBackend','name':'b'}]}}
        objects={o['kind']:copy.deepcopy(o) for o in [backend,route,policy]}
        for obj in objects.values(): obj['metadata']['generation']=1
        cond=lambda types:[{'type':t,'status':'True','observedGeneration':1} for t in types]
        objects['AgentgatewayBackend']['status']={'conditions':cond(['Accepted'])}
        objects['HTTPRoute']['status']={'parents':[{'parentRef':{'name':'agents'},'controllerName':'agentgateway.dev/agentgateway','conditions':cond(['Accepted','ResolvedRefs'])}]}
        ancestor={'ancestorRef':{'name':'agents','namespace':'ai-gateway'},'controllerName':'agentgateway.dev/agentgateway','conditions':cond(['Accepted','Attached'])}
        objects['AgentgatewayPolicy']['status']={'ancestors':[ancestor]}
        reader=lambda version,kind,namespace,name:objects[kind]
        self.assertTrue(self.run_status([backend,route,policy],reader)['complete'])
        ancestor['ancestorRef']['name']='unrelated'
        self.assertFalse(self.run_status([backend,route,policy],reader)['complete'])

    def test_derived_secret_existence_uses_metadata_only(self):
        self.expected[0]['spec']['template']['spec']['containers'][0]['env']=[{'name':'PW','valueFrom':{'secretKeyRef':{'name':'creds','key':'password'}}}]
        self.live=copy.deepcopy(self.expected[0]); self.live['metadata']['generation']=1
        self.live['status']={'observedGeneration':1,'replicas':1,'updatedReplicas':1,'availableReplicas':1,'readyReplicas':1}
        reads=[]
        def reader(version,kind,namespace,name):
            reads.append((kind,namespace,name))
            if kind=='Secret': return {'apiVersion':'v1','kind':'Secret','metadata':{'namespace':namespace,'name':name}}
            return self.live
        self.assertTrue(self.run_status(reader=reader)['complete'])
        self.assertIn(('Secret','mcp','creds'),reads)

    def test_explicit_server_defaults_do_not_hide_extra_meaningful_fields(self):
        self.live['metadata']['labels']={'kustomize.toolkit.fluxcd.io/name':'apps','kustomize.toolkit.fluxcd.io/namespace':'flux-system'}
        self.live['spec']['revisionHistoryLimit']=10
        self.live['spec']['template']['spec']['dnsPolicy']='ClusterFirst'
        self.live['spec']['template']['spec']['containers'][0]['ports'][0]['protocol']='TCP'
        self.assertTrue(self.run_status()['complete'])
        self.live['spec']['template']['spec']['dnsPolicy']='Default'
        self.assertFalse(self.run_status()['complete'])

    def test_service_allocation_does_not_hide_headless_mode(self):
        service={'apiVersion':'v1','kind':'Service','metadata':{'name':'backend','namespace':'mcp'},'spec':{'selector':{'app':'backend'},'ports':[{'port':8000}]}}
        self.live=copy.deepcopy(service)
        self.live['spec'].update(clusterIP='10.96.0.20', clusterIPs=['10.96.0.20'], ipFamilies=['IPv4'])
        self.assertTrue(self.run_status([service])['complete'])
        self.live['spec'].update(clusterIP='None', clusterIPs=['None'])
        self.assertFalse(self.run_status([service])['complete'])
        headless=copy.deepcopy(service)
        headless['spec'].update(clusterIP='None', clusterIPs=['None'], ipFamilies=['IPv4'])
        self.assertTrue(self.run_status([headless])['complete'])

    def test_completed_job_missing_projected_secret_is_incomplete(self):
        job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':'bootstrap-v1','namespace':'database'},'spec':{'template':{'spec':{'restartPolicy':'Never','containers':[{'name':'sql','image':'postgres'}],'volumes':[{'name':'credentials','projected':{'sources':[{'secret':{'name':'projected-creds','items':[{'key':'password','path':'password'}]}}]}}]}}}}
        self.live=copy.deepcopy(job)
        self.live['status']={'conditions':[{'type':'Complete','status':'True'}]}
        reads=[]
        def reader(version,kind,namespace,name):
            reads.append((version,kind,namespace,name))
            return None if kind=='Secret' else self.live
        result=self.run_status([job],reader)
        self.assertFalse(result['complete'])
        self.assertIn(('v1','Secret','database','projected-creds'),reads)
        self.assertIn({'layer':'SecretReference','namespace':'database','name':'projected-creds','complete':False,'state':'missing'},result['layers'])

    def test_unsupported_policies_never_claim_current(self):
        for kind in ('BackendTLSPolicy','SecurityPolicy','AuthorizationPolicy'):
            policy={'apiVersion':'example.io/v1','kind':kind,'metadata':{'name':'unsupported','namespace':'mcp'},'spec':{}}
            for conditions in ([], [{'type':'Accepted','status':'False','observedGeneration':2}], [{'type':'Accepted','status':'True','observedGeneration':1}]):
                self.live=copy.deepcopy(policy)
                self.live['metadata']['generation']=2
                self.live['status']={'conditions':conditions}
                reads=[]
                with self.subTest(kind=kind,conditions=conditions):
                    result=self.run_status([policy],lambda *a:reads.append(a) or self.live)
                    self.assertFalse(result['complete'])
                    self.assertEqual(result['layers'][0]['state'],'unsupported-public-kind')
                    self.assertEqual(reads,[])

    def test_policy_core_service_group_defaults_are_path_specific(self):
        for mode in ('extAuth','jwtAuthentication'):
            ref={'kind':'Service','name':'upstream','namespace':'auth','port':8080}
            if mode == 'extAuth':
                traffic={'extAuth':{'backendRef':ref,'failureMode':'FailClosed'}}
                path=('extAuth','backendRef')
            else:
                traffic={'jwtAuthentication':{'mode':'Strict','providers':[{'issuer':'https://idp.example','jwks':{'remote':{'backendRef':ref,'jwksPath':'/certs'}}}]}}
                path=('jwtAuthentication','providers',0,'jwks','remote','backendRef')
            policy={'apiVersion':'agentgateway.dev/v1alpha1','kind':'AgentgatewayPolicy','metadata':{'name':mode,'namespace':'ai-gateway'},'spec':{'targetRefs':[{'group':'gateway.networking.k8s.io','kind':'Gateway','name':'agents'}],'traffic':traffic}}
            self.live=copy.deepcopy(policy)
            self.live['metadata']['generation']=1
            self.live['status']={'ancestors':[{'ancestorRef':{'name':'agents','namespace':'ai-gateway'},'controllerName':'agentgateway.dev/agentgateway','conditions':[{'type':t,'status':'True','observedGeneration':1} for t in ('Accepted','Attached')]}]}
            actual_ref=self.live['spec']['traffic']
            for key in path: actual_ref=actual_ref[key]
            actual_ref['group']=''
            with self.subTest(mode=mode,case='core-default'):
                self.assertTrue(self.run_status([policy])['complete'])
            actual_ref['group']='wrong.example.io'
            with self.subTest(mode=mode,case='wrong-group'):
                self.assertFalse(self.run_status([policy])['complete'])
            # Explicit desired groups remain compared, including empty groups.
            ref['group']='custom.example.io'
            actual_ref['group']=''
            with self.subTest(mode=mode,case='explicit-desired-group'):
                self.assertFalse(self.run_status([policy])['complete'])

    def test_policy_group_default_is_not_normalized_at_other_paths(self):
        policy={'apiVersion':'agentgateway.dev/v1alpha1','kind':'AgentgatewayPolicy','metadata':{'name':'other-path','namespace':'ai-gateway'},'spec':{'traffic':{'other':{'backendRef':{'kind':'Service','name':'upstream'}}}}}
        self.live=copy.deepcopy(policy)
        self.live['spec']['traffic']['other']['backendRef']['group']=''
        result=self.run_status([policy])
        self.assertFalse(result['complete'])
        self.assertEqual(result['layers'][0]['state'],'configuration-mismatch')

    def test_policy_default_normalization_preserves_target_order(self):
        policy={'apiVersion':'agentgateway.dev/v1alpha1','kind':'AgentgatewayPolicy','metadata':{'name':'shared','namespace':'ai-gateway'},'spec':{'targetRefs':[{'kind':'Gateway','name':'agents'},{'kind':'Gateway','name':'other'}]}}
        self.live=copy.deepcopy(policy)
        self.live['spec']['targetRefs'].reverse()
        self.assertFalse(self.run_status([policy])['complete'])
