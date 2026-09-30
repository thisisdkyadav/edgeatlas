"""Revision gateway. SQLite coordinates writes; Qdrant Server stores the cloud vector projection."""
import hmac
import json
import math
import os
import re
import time
import uuid
from pathlib import Path
from threading import RLock
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
from .schemas import MemoryInput
from .storage import connect, dump
from .policy import routing

class PushInput(BaseModel):
    operation_id: uuid.UUID
    device_id: str = Field(min_length=1,max_length=80)
    base_revision: int = Field(ge=0)
    document: dict
    vector: list[float] = Field(default_factory=list, max_length=384)
    model: str = 'BAAI/bge-small-en-v1.5'

class CloudSearchInput(BaseModel):
    vector: list[float] = Field(min_length=384,max_length=384)
    limit: int = Field(default=8,ge=1,le=30)

class CloudStore:
    def __init__(self, data_dir=None, qdrant_url=None, collection=None):
        self.path=Path(data_dir or os.getenv('CLOUD_DATA_DIR','./data/cloud'))
        self.db=connect(self.path / 'cloud.sqlite')
        self.lock=RLock()
        self.collection=collection or os.getenv('QDRANT_COLLECTION','edgeatlas_memories')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', self.collection):
            raise ValueError('Invalid collection name')
        self.client=httpx.Client(base_url=(qdrant_url or os.getenv('QDRANT_URL','http://127.0.0.1:6333')).rstrip('/'), headers={'api-key':os.getenv('QDRANT_API_KEY','')},timeout=10)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, document TEXT NOT NULL, vector TEXT NOT NULL, projected INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS changes(seq INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, document TEXT NOT NULL);
        ''')
        self.db.commit()

    def ensure_collection(self):
        response=self.client.get('/collections/'+self.collection)
        if response.status_code==404:
            response=self.client.put('/collections/'+self.collection,json={'vectors':{'dense':{'size':384,'distance':'Cosine'}}})
        response.raise_for_status()

    def project(self):
        self.ensure_collection()
        rows=list(self.db.execute('SELECT * FROM memories WHERE projected=0'))
        if rows:
            points=[{'id':r['id'],'vector':{'dense':json.loads(r['vector'])},'payload':json.loads(r['document'])} for r in rows]
            response=self.client.put('/collections/'+self.collection+'/points',params={'wait':'true'},json={'points':points})
            response.raise_for_status()
            self.db.executemany('UPDATE memories SET projected=1 WHERE id=?',[(r['id'],) for r in rows])
            self.db.commit()

    def push(self, value):
        import hashlib
        fingerprint=hashlib.sha256(dump(value.model_dump(mode='json')).encode()).hexdigest()
        with self.lock:
            previous=self.db.execute('SELECT * FROM operations WHERE id=?',(str(value.operation_id),)).fetchone()
            if previous:
                if previous['fingerprint']!=fingerprint:
                    raise HTTPException(409,'Operation ID was reused with different content.')
                self.project()
                return json.loads(previous['response'])
            doc=value.document
            try:
                id=str(uuid.UUID(doc['id']))
            except (KeyError,ValueError,TypeError):
                raise HTTPException(422,'A UUID memory ID is required.')
            existing=self.db.execute('SELECT document FROM memories WHERE id=?',(id,)).fetchone()
            current=json.loads(existing['document']) if existing else None
            revision=current['cloud_revision'] if current else 0
            if value.base_revision!=revision:
                raise HTTPException(409,{'message':'Concurrent edit requires resolution.','remote':current})
            if value.model!='BAAI/bge-small-en-v1.5':
                raise HTTPException(422,'Embedding model mismatch.')
            if doc.get('deleted'):
                doc={'id':id,'deleted':True,'visibility':'team','title':'Withdrawn memory','body':'','tags':[],'category':'Observation','site':'','source':''}
                vector=[0.0]*384
            else:
                # Validate at the gateway too: no edge-only payload can bypass routing.
                try:
                    validated=MemoryInput.model_validate(doc).model_dump(exclude={'expected_version'})
                except ValueError:
                    raise HTTPException(422,'Invalid memory document.')
                if routing(validated)['route']!='cloud':
                    raise HTTPException(422,'This memory is not eligible for cloud sharing.')
                if len(value.vector)!=384 or any(not math.isfinite(v) for v in value.vector):
                    raise HTTPException(422,'A finite 384-dimensional vector is required.')
                doc={**validated,'id':id,'deleted':False}
                vector=value.vector
            doc.update(cloud_revision=revision+1, cloud_updated_at=time.time(), origin_device=value.device_id)
            response={'document':doc,'cloud_revision':revision+1}
            with self.db:
                self.db.execute('INSERT INTO memories VALUES(?,?,?,0) ON CONFLICT(id) DO UPDATE SET document=excluded.document,vector=excluded.vector,projected=0',(id,dump(doc),dump(vector)))
                self.db.execute('INSERT INTO changes(record_id,document) VALUES(?,?)',(id,dump(doc)))
                self.db.execute('INSERT INTO operations VALUES(?,?,?)',(str(value.operation_id),fingerprint,dump(response)))
            # Failed projection remains durable and is retried on the same operation ID.
            self.project()
            return response

    def changes(self, after, limit):
        with self.lock:
            self.project()
            rows=list(self.db.execute('SELECT * FROM changes WHERE seq>? ORDER BY seq LIMIT ?',(after,limit)))
            return {'changes':[{'seq':r['seq'],'document':json.loads(r['document'])} for r in rows],'cursor':rows[-1]['seq'] if rows else after,'has_more':len(rows)==limit}

    def overview(self):
        with self.lock:
            self.project()
            docs=[json.loads(r['document']) for r in self.db.execute('SELECT document FROM memories')]
            return {'engine':'Qdrant Server','collection':self.collection,'memories':[d for d in docs if not d.get('deleted')], 'withdrawn':sum(bool(d.get('deleted')) for d in docs), 'changes':self.db.execute('SELECT COUNT(*) FROM changes').fetchone()[0]}

    def close(self):
        self.client.close()
        self.db.close()

def create_app(store=None):
    store=store or CloudStore()
    token=os.getenv('EDGE_SYNC_TOKEN','local-demo-sync-token')
    if os.getenv('CLOUD_HOST','127.0.0.1') not in ('127.0.0.1','localhost') and token=='local-demo-sync-token':
        raise ValueError('Set a custom EDGE_SYNC_TOKEN before exposing the gateway beyond loopback.')
    @asynccontextmanager
    async def lifespan(app):
        yield
        store.close()
    app=FastAPI(title='EdgeAtlas synchronization gateway',lifespan=lifespan)
    app.state.store=store
    @app.middleware('http')
    async def authenticate(request:Request,call_next):
        from fastapi.responses import JSONResponse
        if request.url.path!='/health' and not hmac.compare_digest(request.headers.get('x-sync-token',''),token):
            return JSONResponse({'detail':'Invalid synchronization token.'},status_code=401)
        if request.headers.get('origin'):
            return JSONResponse({'detail':'Cloud gateway is for authenticated device clients.'},status_code=403)
        try:
            return await call_next(request)
        except httpx.HTTPError:
            return JSONResponse({'detail':'Qdrant Server unavailable; durable projection pending.'},status_code=503)
    @app.get('/health')
    def health():
        try:
            with store.lock: store.ensure_collection()
            return {'ok':True,'engine':'Qdrant Server'}
        except httpx.HTTPError:
            raise HTTPException(503,'Qdrant Server unavailable.')
    @app.post('/sync/push')
    def push(value:PushInput): return store.push(value)
    @app.get('/sync/changes')
    def changes(after:int=0,limit:int=100):
        if after<0 or not 1<=limit<=500: raise HTTPException(422,'Invalid cursor or limit.')
        return store.changes(after,limit)
    @app.get('/sync/overview')
    def overview(): return store.overview()
    @app.post('/sync/search')
    def search(value:CloudSearchInput):
        if any(not math.isfinite(x) for x in value.vector): raise HTTPException(422,'Invalid vector.')
        with store.lock:
            store.project()
            response=store.client.post('/collections/'+store.collection+'/points/query',json={'query':value.vector,'using':'dense','limit':value.limit,'with_payload':True,'filter':{'must':[{'key':'deleted','match':{'value':False}}]}})
            response.raise_for_status()
            return response.json()['result']
    return app
