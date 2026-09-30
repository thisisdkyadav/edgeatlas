import json
import socket
import time
import uuid
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app import create_app as edge_app
from backend.cloud import CloudStore, create_app as cloud_app
from backend.engine import Device
from backend.policy import routing
from backend.schemas import MemoryInput, SearchInput, ResolveInput
from backend.storage import get_record,save_record,set_setting
from backend.vectors import Embeddings

@pytest.fixture(scope='session')
def model(): return Embeddings()

@pytest.fixture
def device(tmp_path,model):
    d=Device(model,tmp_path/'edge',device_id='test-device')
    yield d
    d.close()

@pytest.fixture
def cloud(tmp_path):
    url='http://127.0.0.1:6333'
    if not httpx.get(url+'/healthz',timeout=2).is_success: pytest.fail('Start real Qdrant Server on localhost:6333 before the integration suite.')
    collection='edgeatlas_test_'+uuid.uuid4().hex
    store=CloudStore(tmp_path/'cloud',url,collection)
    app=cloud_app(store)
    yield store,app
    httpx.delete(url+'/collections/'+collection,timeout=10)
    store.close()

def attach(device,app):
    device.client.close()
    device.client=TestClient(app,headers={'x-sync-token':'local-demo-sync-token'})

def note(**kw):
    return MemoryInput(**{'title':'Pump vibration observation','body':'The pump vibrates on cold start. Check coupling alignment under the approved site procedure.','tags':['pump','vibration'],'visibility':'team',**kw})

def update(device,record,**kw):
    fields={k:record[k] for k in MemoryInput.model_fields if k in record}
    return device.save(MemoryInput(**{**fields,**kw,'expected_version':record['version']}),record['id'])

def test_real_edge_semantic_bm25_hybrid(device):
    pump=device.save(note())
    device.save(note(title='Battery shelf life',body='Check battery age against the manufacturer replacement guidance.',tags=['battery']))
    for mode in ['semantic','hybrid','keyword']:
        q='pump shaking on startup' if mode!='keyword' else 'vibration'
        result=device.search(SearchInput(query=q,mode=mode))
        assert result['engine']=='Qdrant Edge'
        assert result['results'][0]['id']==pump['id']
        assert result['duration_ms']>0

def test_search_filters(device):
    device.save(note(site='East station'))
    assert not device.search(SearchInput(query='pump',site='North station'))['results']
    assert device.search(SearchInput(query='pump',site='East station'))['results']

def test_offline_search_does_not_open_network_socket(device,monkeypatch):
    device.save(note())
    def blocked(*args,**kwargs): raise AssertionError('Offline semantic retrieval opened a network connection')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    assert device.search(SearchInput(query='pump startup vibration'))['results']

@pytest.mark.parametrize('sensitive',['engineer@example.test','password=synthetic-example','api_key=synthetic-example','passport: DEMO12345','+91 98765 43210'])
def test_sensitive_patterns_stay_local(device,sensitive):
    record=device.save(note(body='A synthetic maintenance note includes '+sensitive))
    assert record['routing']['route']=='local'
    assert record['routing']['flags']
    assert device.status()['queued']==0

def test_explicit_local_has_no_outbox(device):
    record=device.save(note(visibility='local'))
    assert record['routing']['route']=='local'
    assert device.status()['queued']==0

def test_stale_local_version_is_rejected(device):
    record=device.save(note())
    update(device,record,body='First valid update to the equipment observation.')
    with pytest.raises(HTTPException) as exc: update(device,record,body='Second update from an outdated editor state.')
    assert exc.value.status_code==409

def test_real_qdrant_server_sync_and_second_device_pull(device,cloud,tmp_path,model):
    store,app=cloud
    attach(device,app)
    record=device.save(note())
    private=device.save(note(title='Device only note',visibility='local'))
    assert device.sync()['pushed']==1
    overview=device.client.get('/sync/overview').json()
    assert [r['id'] for r in overview['memories']]==[record['id']]
    actual=httpx.post('http://127.0.0.1:6333/collections/'+store.collection+'/points',json={'ids':[record['id']],'with_payload':True}).json()['result']
    assert actual[0]['payload']['title']==record['title']
    second=Device(model,tmp_path/'second',device_id='test-device-b')
    attach(second,app)
    try:
        assert second.sync()['pulled']==1
        assert second.one(record['id'])['cloud_revision']==1
        assert all(r['id']!=private['id'] for r in second.list())
        assert second.search(SearchInput(query='pump startup'))['results'][0]['id']==record['id']
    finally: second.close()

def test_offline_queue_reconnect(device,cloud):
    _,app=cloud;attach(device,app)
    with device.db:set_setting(device.db,'online',False)
    record=device.save(note())
    assert device.sync()['status']=='offline'
    assert device.one(record['id'])['sync_state']=='queued'
    with device.db:set_setting(device.db,'online',True)
    assert device.sync()['pushed']==1
    assert device.one(record['id'])['sync_state']=='synced'

def test_durable_queue_and_shard_reopen(tmp_path,model):
    d=Device(model,tmp_path/'persistent')
    record=d.save(note())
    d.close()
    d=Device(model,tmp_path/'persistent')
    try:
        assert d.status()['queued']==1
        assert d.search(SearchInput(query='pump shaking'))['results'][0]['id']==record['id']
    finally:d.close()

def test_retry_backoff_persists(device):
    device.client.close()
    def fail(request):raise httpx.ConnectError('Deliberate test disconnection',request=request)
    device.client=httpx.Client(base_url='http://test',transport=httpx.MockTransport(fail))
    record=device.save(note())
    assert device.sync()['status']=='unavailable'
    r=device.one(record['id'])
    assert r['sync_state']=='retry' and r['queue']['attempts']==1
    assert r['queue']['retry_at']>time.time()

def test_metered_priority_and_withdrawal(device,cloud):
    _,app=cloud;attach(device,app)
    low=device.save(note(priority='low'))
    critical=device.save(note(title='Urgent pressure change',priority='critical'))
    with device.db:set_setting(device.db,'metered',True)
    assert device.sync()['pushed']==1
    assert device.one(low['id'])['sync_state']=='queued'
    synced=device.one(critical['id'])
    update(device,synced,priority='low',visibility='local')
    assert device.sync()['pushed']==1 # privacy withdrawal bypasses bandwidth cutoff
    assert device.client.get('/sync/overview').json()['memories']==[]

def test_privacy_reclassification_retracts_without_leaking(device,cloud):
    store,app=cloud;attach(device,app)
    record=device.save(note());device.sync()
    private=update(device,device.one(record['id']),body='Private note with engineer@example.test kept only on device.')
    queued=json.loads(device.db.execute('SELECT document FROM outbox').fetchone()['document'])
    assert queued['document']=={'id':record['id'],'deleted':True} and queued['vector']==[]
    assert device.sync()['pushed']==1
    assert device.one(record['id'])['deleted'] is False
    assert device.client.get('/sync/overview').json()['memories']==[]
    raw=store.db.execute('SELECT document FROM memories').fetchone()['document']
    assert 'engineer@example.test' not in raw
    assert 'Private note' not in raw

def conflict_setup(device,cloud,tmp_path,model):
    _,app=cloud;attach(device,app)
    record=device.save(note());device.sync()
    second=Device(model,tmp_path/'other',device_id='other-device');attach(second,app)
    second.sync()
    update(device,device.one(record['id']),body='Device technician checked the coupling alignment and found loose mounts.')
    update(second,second.one(record['id']),body='Control room found a blocked inlet strainer in the maintenance history.')
    second.sync()
    device.sync()
    second.close()
    return device.one(record['id'])

@pytest.mark.parametrize('choice',['local','cloud','merge'])
def test_conflict_keeps_both_and_resolves(device,cloud,tmp_path,model,choice):
    record=conflict_setup(device,cloud,tmp_path,model)
    assert record['sync_state']=='conflict'
    assert 'loose mounts' in record['body'] and 'inlet strainer' in record['conflict']['remote']['body']
    resolved=device.resolve(record['id'],ResolveInput(choice=choice,merged_body='Inspect both coupling alignment and the inlet strainer under the approved procedure.'))
    assert resolved['conflict'] is None
    assert device.sync()['status']=='connected'
    current=device.one(record['id'])
    assert current['cloud_revision']==(2 if choice=='cloud' else 3)
    assert current['sync_state']=='synced'

def test_edit_cannot_bypass_unresolved_conflict(device,cloud,tmp_path,model):
    record=conflict_setup(device,cloud,tmp_path,model)
    with pytest.raises(HTTPException):update(device,record,body='Accidental edit while the conflict is still unresolved.')

def test_archive_restore_and_cloud_tombstone(device,cloud):
    _,app=cloud;attach(device,app)
    record=device.save(note());device.sync()
    record=device.one(record['id']);archived=device.archive(record['id'],record['version'])
    assert not device.search(SearchInput(query='pump'))['results']
    assert device.sync()['pushed']==1
    assert device.client.get('/sync/overview').json()['withdrawn']==1
    device.archive(record['id'],device.one(record['id'])['version'],True)
    assert device.sync()['pushed']==1
    assert device.search(SearchInput(query='pump'))['results']

def test_retention_archives_reversibly(device):
    record=device.save(note(ttl_days=1))
    raw=get_record(device.db,record['id']);raw['expires_at']=time.time()-1
    with device.db:save_record(device.db,raw)
    device.expire()
    assert device.one(record['id'])['deleted']
    assert device.history(record['id'])

def test_cloud_idempotency_and_operation_reuse(device,cloud):
    store,app=cloud;attach(device,app)
    record=device.save(note())
    row=device.db.execute('SELECT * FROM outbox').fetchone();snap=json.loads(row['document'])
    request={'operation_id':row['operation_id'],'device_id':device.id,'base_revision':0,**snap,'model':device.embedder.name}
    first=device.client.post('/sync/push',json=request)
    second=device.client.post('/sync/push',json=request)
    assert first.status_code==second.status_code==200 and first.json()==second.json()
    assert store.db.execute('SELECT COUNT(*) FROM changes').fetchone()[0]==1
    request['document']['body']='An intentionally different operation payload should be rejected.'
    assert device.client.post('/sync/push',json=request).status_code==409

def test_cloud_rejects_sensitive_and_bad_vector(device,cloud):
    _,app=cloud;attach(device,app)
    record=device.save(note())
    raw=get_record(device.db,record['id'])
    req={'operation_id':str(uuid.uuid4()),'device_id':device.id,'base_revision':0,'document':{k:v for k,v in raw.items() if k!='vector'},'vector':raw['vector']}
    req['document']['body']='Sensitive note engineer@example.test should never reach the cloud.'
    assert device.client.post('/sync/push',json=req).status_code==422
    req['document']['body']=record['body'];req['vector']=[1.0]
    assert device.client.post('/sync/push',json=req).status_code==422

def test_durable_cloud_projection_recovers_after_qdrant_failure(device,cloud,monkeypatch):
    store,app=cloud;attach(device,app)
    record=device.save(note())
    real_put=store.client.put
    def fail(*args,**kwargs):raise httpx.ConnectError('Deliberate cloud projection failure')
    store.ensure_collection()
    monkeypatch.setattr(store.client,'put',fail)
    assert device.sync()['status']=='unavailable'
    assert store.db.execute('SELECT projected FROM memories').fetchone()[0]==0
    monkeypatch.setattr(store.client,'put',real_put)
    assert device.sync(force=True)['pushed']==1
    assert store.db.execute('SELECT projected FROM memories').fetchone()[0]==1
    assert store.db.execute('SELECT COUNT(*) FROM changes').fetchone()[0]==1

def test_api_validation_origin_export(device):
    client=TestClient(edge_app(device))
    assert client.post('/api/memories',json={'title':'x','body':'short'}).status_code==422
    assert client.post('/api/search',json={'query':'pump'},headers={'origin':'https://untrusted.example'}).status_code==403
    record=client.post('/api/memories',json=note(title='=FORMULA demo note').model_dump()).json()
    assert record['id']
    assert "'=FORMULA" in client.get('/api/export?format=csv').text
    assert client.get('/api/export?format=json').json()['memories']
    assert client.get('/api/export?format=bad').status_code==422

def test_gateway_authentication(cloud):
    _,app=cloud
    client=TestClient(app)
    assert client.get('/sync/overview').status_code==401

def test_device_access_token(device,monkeypatch):
    monkeypatch.setenv('EDGE_APP_TOKEN','synthetic-test-token')
    client=TestClient(edge_app(device))
    assert client.get('/api/status').status_code==401
    assert client.get('/api/status',headers={'x-edge-token':'synthetic-test-token'}).status_code==200

def test_control_room_edit_appears_on_pull(device,cloud):
    _,app=cloud;attach(device,app)
    record=device.save(note());device.sync()
    client=TestClient(edge_app(device))
    payload=note(body='Updated control-room observation about the inlet filter.').model_dump();payload['expected_version']=1
    assert client.put('/api/cloud/memories/'+record['id'],json=payload).status_code==200
    assert device.sync()['pulled']==1
    assert 'control-room' in device.one(record['id'])['body']

def test_local_projection_failure_repaired_before_search(device,monkeypatch):
    real=device.index.upsert
    def fail(*args,**kwargs):raise RuntimeError('Deliberate index projection failure')
    monkeypatch.setattr(device.index,'upsert',fail)
    with pytest.raises(RuntimeError):device.save(note())
    assert device.db.execute('SELECT COUNT(*) FROM projection').fetchone()[0]==1
    assert device.status()['total']==1
    monkeypatch.setattr(device.index,'upsert',real)
    assert device.search(SearchInput(query='pump startup'))['results']
    assert device.db.execute('SELECT COUNT(*) FROM projection').fetchone()[0]==0
