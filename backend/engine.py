import json
import os
import time
import uuid
from pathlib import Path
from threading import RLock
import httpx
from fastapi import HTTPException
from .policy import routing
from .storage import connect, edge_schema, records, get_record, save_record, event, setting, set_setting, dump
from .vectors import EdgeIndex, content

class Device:
    def __init__(self, embedder, data_dir=None, device_id=None, client=None, seed=False):
        self.path=Path(data_dir or os.getenv('EDGE_DATA_DIR','./data/edge'))
        self.id=device_id or os.getenv('EDGE_DEVICE_ID','field-unit-07')
        self.name=os.getenv('EDGE_DEVICE_NAME','Field unit 07')
        self.embedder=embedder
        self.lock=RLock()
        self.db=connect(self.path/'device.sqlite')
        edge_schema(self.db)
        self.index=EdgeIndex(self.path/'shard',embedder)
        self.cloud_url=os.getenv('EDGE_CLOUD_URL','http://127.0.0.1:4200')
        self.client=client or httpx.Client(base_url=self.cloud_url.rstrip('/'),headers={'x-sync-token':os.getenv('EDGE_SYNC_TOKEN','local-demo-sync-token')},timeout=8)
        self.last_status='Not connected yet'
        self.last_search_ms=None
        # SQLite is authoritative: replay the complete local projection after a crash.
        for record in records(self.db): self.project(record)
        if seed and not records(self.db):
            from .seed import seed_device
            seed_device(self)

    def project(self,record):
        self.index.upsert(record,record.get('vector'))
        with self.db: self.db.execute('DELETE FROM projection WHERE record_id=?',(record['id'],))

    def repair_index(self):
        for row in list(self.db.execute('SELECT record_id FROM projection')):
            record=get_record(self.db,row['record_id'])
            if record: self.project(record)

    def decorate(self, record):
        if record is None: return None
        result={k:v for k,v in record.items() if k!='vector'}
        result['routing']=routing(record)
        queue=self.db.execute('SELECT state,attempts,error,retry_at FROM outbox WHERE record_id=?',(record['id'],)).fetchone()
        conflict=self.db.execute('SELECT remote,detected_at FROM conflicts WHERE record_id=?',(record['id'],)).fetchone()
        result['sync_state']='conflict' if conflict else (queue['state'] if queue else ('synced' if record.get('cloud_revision',0)>0 and result['routing']['route']=='cloud' else 'local'))
        result['queue']=dict(queue) if queue else None
        result['conflict']={'remote':json.loads(conflict['remote']), 'detected_at':conflict['detected_at']} if conflict else None
        return result

    def list(self, include_deleted=False):
        with self.lock:
            return [self.decorate(r) for r in sorted(records(self.db),key=lambda r:r['updated_at'],reverse=True) if include_deleted or not r.get('deleted')]

    def one(self,id):
        with self.lock:
            record=get_record(self.db,id)
            if not record: raise HTTPException(404,'Memory not found.')
            return self.decorate(record)

    def queue(self,record):
        route=routing(record)
        if route['route']=='cloud' or record.get('cloud_revision',0)>0:
            # Withdrawing a shared record never transmits its new private content or vector.
            outgoing=record if route['route']=='cloud' else {'id':record['id'],'deleted':True}
            snapshot={'document':{k:v for k,v in outgoing.items() if k!='vector'}, 'vector':record['vector'] if route['route']=='cloud' else []}
            self.db.execute('INSERT INTO outbox VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(record_id) DO UPDATE SET operation_id=excluded.operation_id,base_revision=excluded.base_revision,document=excluded.document,state=excluded.state,attempts=0,retry_at=0,error=excluded.error', (record['id'],str(uuid.uuid4()),record.get('cloud_revision',0),dump(snapshot),'queued',0,0,''))
        else:
            self.db.execute('DELETE FROM outbox WHERE record_id=?',(record['id'],))

    def save(self,value,id=None):
        with self.lock:
            old=get_record(self.db,id) if id else None
            if id and not old: raise HTTPException(404,'Memory not found.')
            if old and value.expected_version!=old['version']: raise HTTPException(409,'This memory changed. Refresh before saving.')
            if old and self.db.execute('SELECT 1 FROM conflicts WHERE record_id=?',(id,)).fetchone(): raise HTTPException(409,'Resolve the synchronization conflict before editing.')
            doc=value.model_dump(exclude={'expected_version'})
            now=time.time()
            doc.update(id=id or str(uuid.uuid4()),version=old['version']+1 if old else 1,cloud_revision=old.get('cloud_revision',0) if old else 0,created_at=old['created_at'] if old else now,updated_at=now,deleted=False,origin_device=self.id)
            doc['expires_at']=now+doc['ttl_days']*86400 if doc['ttl_days'] else None
            doc['vector']=self.embedder.encode(content(doc))
            with self.db:
                save_record(self.db,doc,'edit' if old else 'create')
                self.queue(doc)
                event(self.db,'memory','Updated memory' if old else 'Captured a new memory',doc['id'])
            self.project(doc)
            return self.decorate(doc)

    def archive(self,id,version,restore=False):
        with self.lock:
            doc=get_record(self.db,id)
            if not doc: raise HTTPException(404,'Memory not found.')
            if doc['version']!=version: raise HTTPException(409,'This memory changed. Refresh before archiving.')
            if self.db.execute('SELECT 1 FROM conflicts WHERE record_id=?',(id,)).fetchone(): raise HTTPException(409,'Resolve this conflict first.')
            doc.update(deleted=not restore,version=doc['version']+1,updated_at=time.time())
            if restore: doc['expires_at']=time.time()+doc['ttl_days']*86400 if doc['ttl_days'] else None
            with self.db:
                save_record(self.db,doc,'restore' if restore else 'archive')
                self.queue(doc)
                event(self.db,'memory','Restored memory' if restore else 'Archived memory',id)
            self.project(doc)
            return self.decorate(doc)

    def expire(self):
        with self.lock:
            for doc in records(self.db):
                if not doc.get('deleted') and doc.get('expires_at') and doc['expires_at']<time.time() and not self.db.execute('SELECT 1 FROM conflicts WHERE record_id=?',(doc['id'],)).fetchone():
                    self.archive(doc['id'],doc['version'])
                    with self.db: event(self.db,'policy','Retention period reached; memory archived',doc['id'])

    def search(self,value):
        with self.lock:
            self.repair_index()
            hits,duration=self.index.search(value.query,value.mode,value.limit,{'category':value.category,'visibility':value.visibility,'site':value.site})
            output=[]
            for hit in hits:
                doc=get_record(self.db,hit['id'])
                if doc and not doc.get('deleted'):
                    output.append({**self.decorate(doc),'score':hit['score']})
            self.last_search_ms=duration
            with self.db:
                self.db.execute('INSERT INTO searches(query,mode,duration,count,time) VALUES(?,?,?,?,?)',(value.query,value.mode,duration,len(output),time.time()))
            # Source-grounded extractive response. No unsupported generative claims.
            return {'results':output,'duration_ms':duration,'mode':value.mode,'engine':'Qdrant Edge','model':self.embedder.name,'answer': [{'id':r['id'],'title':r['title'],'excerpt':r['body'][:500],'source':r['source']} for r in output[:3]], 'answer_method':'Extractive evidence — inspect source notes before acting.'}

    def conflict(self,id,remote):
        with self.db:
            self.db.execute('INSERT INTO conflicts VALUES(?,?,?) ON CONFLICT(record_id) DO UPDATE SET remote=excluded.remote,detected_at=excluded.detected_at',(id,dump(remote),time.time()))
            self.db.execute("UPDATE outbox SET state='conflict',error='Concurrent cloud edit' WHERE record_id=?",(id,))
            event(self.db,'conflict','Concurrent edits preserved for your review',id)

    def sync(self,force=False):
        with self.lock:
            previous_status=self.last_status
            if not setting(self.db,'online',True):
                self.last_status='Offline · changes stay on device'
                return {'status':'offline','pushed':0,'pulled':0}
            pushed=pulled=deferred=0
            try:
                rows=list(self.db.execute("SELECT * FROM outbox WHERE state!='conflict' ORDER BY rowid"))
                rows.sort(key=lambda row:110 if json.loads(row['document'])['document'].get('deleted') else routing(get_record(self.db,row['record_id']))['priority'],reverse=True)
                for row in rows[:20]:
                    current=get_record(self.db,row['record_id'])
                    priority=routing(current)['priority']
                    snap=json.loads(row['document'])
                    withdrawing=bool(snap['document'].get('deleted'))
                    if (row['retry_at']>time.time() and not force) or (setting(self.db,'metered',False) and priority<setting(self.db,'metered_min_priority',70) and not withdrawing):
                        deferred+=1
                        continue
                    request={'operation_id':row['operation_id'],'device_id':self.id,'base_revision':row['base_revision'],**snap,'model':self.embedder.name}
                    response=self.client.post('/sync/push',json=request)
                    if response.status_code==409:
                        detail=response.json().get('detail',{})
                        if isinstance(detail,dict) and detail.get('remote'):
                            self.conflict(row['record_id'],detail['remote'])
                            continue
                    response.raise_for_status()
                    current['cloud_revision']=response.json()['cloud_revision']
                    with self.db:
                        save_record(self.db,current,'cloud-ack')
                        self.db.execute('DELETE FROM outbox WHERE operation_id=?',(row['operation_id'],))
                        event(self.db,'sync','Shared copy withdrawn' if withdrawing else 'Memory synchronized to Qdrant Server',row['record_id'])
                    pushed+=1
                # A bounded, ordered change feed. Cursor advances only with applied durable writes.
                for _ in range(5):
                    cursor=setting(self.db,'cursor',0)
                    response=self.client.get('/sync/changes',params={'after':cursor,'limit':100})
                    response.raise_for_status()
                    batch=response.json()
                    for change in batch['changes']:
                        remote=change['document']
                        local=get_record(self.db,remote['id'])
                        if local and remote['cloud_revision']<=local.get('cloud_revision',0): continue
                        if local and self.db.execute('SELECT 1 FROM outbox WHERE record_id=?',(local['id'],)).fetchone():
                            self.conflict(local['id'],remote)
                            continue
                        if local and remote.get('deleted') and routing(local)['route']=='local':
                            local['cloud_revision']=remote['cloud_revision']
                            with self.db: save_record(self.db,local,'withdrawn-ack')
                            continue
                        doc={**remote,'version':(local['version']+1 if local else 1),'created_at':local['created_at'] if local else time.time(),'updated_at':time.time(),'expires_at':None,'ttl_days':0}
                        doc['vector']=self.embedder.encode(content(doc)) if not doc.get('deleted') else [0.0]*384
                        with self.db: save_record(self.db,doc,'cloud-pull')
                        self.project(doc)
                        pulled+=1
                    with self.db: set_setting(self.db,'cursor',batch['cursor'])
                    if not batch['has_more']: break
                self.last_status=f'Connected · {pushed} sent, {pulled} received'
                with self.db:
                    set_setting(self.db,'last_sync',time.time())
                    if pushed or pulled or not previous_status.startswith('Connected'):
                        event(self.db,'sync',f'Sync complete: {pushed} sent, {pulled} received, {deferred} deferred')
                return {'status':'connected','pushed':pushed,'pulled':pulled,'deferred':deferred}
            except (httpx.HTTPError, KeyError,ValueError) as exc:
                self.last_status='Cloud unavailable · local memory remains usable'
                # Durable retry metadata is not marked as synced on an uncertain outcome.
                if 'row' in locals():
                    attempts=row['attempts']+1
                    with self.db:
                        self.db.execute("UPDATE outbox SET attempts=?,retry_at=?,state='retry',error=? WHERE operation_id=?",(attempts,time.time()+min(300,2**min(attempts,8)),str(exc)[:200],row['operation_id']))
                if not previous_status.startswith('Cloud unavailable'):
                    with self.db: event(self.db,'network','Cloud unreachable; synchronization will retry')
                return {'status':'unavailable','pushed':pushed,'pulled':pulled,'deferred':deferred}

    def resolve(self,id,value):
        with self.lock:
            row=self.db.execute('SELECT remote FROM conflicts WHERE record_id=?',(id,)).fetchone()
            if not row: raise HTTPException(404,'No unresolved conflict.')
            remote=json.loads(row['remote'])
            local=get_record(self.db,id)
            if value.choice=='cloud':
                doc={**remote,'version':local['version']+1,'created_at':local['created_at'],'updated_at':time.time(),'ttl_days':0,'expires_at':None}
                doc['vector']=self.embedder.encode(content(doc)) if not doc.get('deleted') else [0.0]*384
                with self.db:
                    self.db.execute('DELETE FROM outbox WHERE record_id=?',(id,))
                    save_record(self.db,doc,'resolve-cloud')
            else:
                doc={**local,'cloud_revision':remote['cloud_revision'],'version':local['version']+1,'updated_at':time.time()}
                if value.choice=='merge':
                    if len(value.merged_body.strip())<10: raise HTTPException(422,'Merged content needs at least 10 characters.')
                    doc['body']=value.merged_body.strip()
                    doc['deleted']=False
                    doc['vector']=self.embedder.encode(content(doc))
                with self.db:
                    save_record(self.db,doc,'resolve-'+value.choice)
                    self.queue(doc)
            with self.db:
                self.db.execute('DELETE FROM conflicts WHERE record_id=?',(id,))
                event(self.db,'conflict','Conflict resolved: '+value.choice,id)
            self.project(doc)
            return self.decorate(doc)

    def status(self):
        with self.lock:
            docs=records(self.db)
            active=[d for d in docs if not d.get('deleted')]
            return {'device_id':self.id,'device_name':self.name,'engine':'Qdrant Edge 0.8.0','model':self.embedder.name,'dimensions':384,'online':setting(self.db,'online',True),'metered':setting(self.db,'metered',False),'auto_sync':setting(self.db,'auto_sync',os.getenv('EDGE_AUTO_SYNC','true')=='true'),'metered_min_priority':setting(self.db,'metered_min_priority',70),'cloud_url':self.cloud_url,'connection':self.last_status,'last_sync':setting(self.db,'last_sync'),'last_search_ms':self.last_search_ms,'cursor':setting(self.db,'cursor',0),'total':len(active),'local':sum(routing(d)['route']=='local' for d in active),'shared':sum(routing(d)['route']=='cloud' for d in active),'queued':self.db.execute("SELECT COUNT(*) FROM outbox WHERE state!='conflict'").fetchone()[0],'conflicts':self.db.execute('SELECT COUNT(*) FROM conflicts').fetchone()[0],'archived':len(docs)-len(active),'storage_bytes':sum(p.stat().st_size for p in self.path.rglob('*') if p.is_file())}

    def history(self,id):
        with self.lock:
            if not get_record(self.db,id): raise HTTPException(404,'Memory not found.')
            return [{'seq':r['seq'],'action':r['action'],'time':r['time'],'document':{k:v for k,v in json.loads(r['document']).items() if k!='vector'}} for r in self.db.execute('SELECT * FROM versions WHERE record_id=? ORDER BY seq DESC LIMIT 100',(id,))]

    def close(self):
        with self.lock:
            self.index.close()
            self.client.close()
            self.db.close()
