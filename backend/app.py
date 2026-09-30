import asyncio
import csv
import hmac
import io
import json
import os
import httpx
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .engine import Device
from .schemas import MemoryInput, SearchInput, ResolveInput, ConnectionInput, PolicyInput
from .storage import set_setting, event
from .vectors import Embeddings

class VersionInput(BaseModel):
    expected_version:int=Field(ge=1)

def create_app(device=None):
    owned=device is None
    if owned: device=Device(Embeddings(),seed=os.getenv('EDGE_SEED','true')=='true')
    token=os.getenv('EDGE_APP_TOKEN','')
    if os.getenv('EDGE_HOST','127.0.0.1') not in ('127.0.0.1','localhost') and not token:
        raise ValueError('An EDGE_APP_TOKEN is required when exposing the edge API beyond loopback.')
    async def worker():
        while True:
            try:
                await asyncio.to_thread(device.expire)
                if device.status()['auto_sync'] and device.status()['online']:
                    await asyncio.to_thread(device.sync)
            except Exception:
                # Keep offline service alive. Per-item failures remain in durable storage.
                with device.lock,device.db: event(device.db,'error','Background maintenance failed; check device logs')
            await asyncio.sleep(15)
    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(worker()) if owned else None
        yield
        if task:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        if owned: device.close()
    app=FastAPI(title='EdgeAtlas local device API',lifespan=lifespan)
    app.state.device=device
    @app.middleware('http')
    async def security(request:Request,call_next):
        if request.url.path.startswith('/api') and request.url.path!='/api/health':
            if token and not hmac.compare_digest(request.headers.get('x-edge-token',''),token):
                return JSONResponse({'detail':'Enter the configured device access token.'},status_code=401)
            origin=request.headers.get('origin')
            allowed={str(request.base_url).rstrip('/'),'http://127.0.0.1:5174',os.getenv('EDGE_APP_ORIGIN','')}
            if origin and origin not in allowed:
                return JSONResponse({'detail':'Origin is not allowed.'},status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        if request.url.path.startswith('/api'): response.headers['Cache-Control']='no-store'
        return response
    @app.get('/api/health')
    def health(): return {'ok':True,'engine':'Qdrant Edge','model_cached':True}
    @app.get('/api/status')
    def status(): return device.status()
    @app.get('/api/memories')
    def memories(include_deleted:bool=False): return device.list(include_deleted)
    @app.post('/api/memories',status_code=201)
    def create(value:MemoryInput): return device.save(value)
    @app.get('/api/memories/{id}')
    def one(id:str): return device.one(id)
    @app.put('/api/memories/{id}')
    def edit(id:str,value:MemoryInput): return device.save(value,id)
    @app.post('/api/memories/{id}/archive')
    def archive(id:str,value:VersionInput): return device.archive(id,value.expected_version)
    @app.post('/api/memories/{id}/restore')
    def restore(id:str,value:VersionInput): return device.archive(id,value.expected_version,True)
    @app.get('/api/memories/{id}/history')
    def history(id:str): return device.history(id)
    @app.post('/api/memories/{id}/resolve')
    def resolve(id:str,value:ResolveInput): return device.resolve(id,value)
    @app.post('/api/search')
    def search(value:SearchInput): return device.search(value)
    @app.post('/api/sync')
    def sync(): return device.sync(force=True)
    @app.put('/api/connection')
    def connection(value:ConnectionInput):
        with device.lock,device.db:
            set_setting(device.db,'online',value.online)
            set_setting(device.db,'metered',value.metered)
            event(device.db,'network','Cloud link enabled' if value.online else 'Cloud link disabled; offline mode active')
        return device.status()
    @app.put('/api/policy')
    def policy(value:PolicyInput):
        with device.lock,device.db:
            set_setting(device.db,'auto_sync',value.auto_sync)
            set_setting(device.db,'metered_min_priority',value.metered_min_priority)
            event(device.db,'policy','Updated synchronization policy')
        return device.status()
    @app.get('/api/activity')
    def activity():
        with device.lock:
            return [dict(r) for r in device.db.execute('SELECT * FROM events ORDER BY seq DESC LIMIT 150')]
    @app.get('/api/search-history')
    def search_history():
        with device.lock:
            return [dict(r) for r in device.db.execute('SELECT * FROM searches ORDER BY seq DESC LIMIT 30')]
    @app.get('/api/cloud')
    def cloud():
        if not device.status()['online']: raise HTTPException(503,'Cloud link is disabled. Local search still works.')
        try:
            response=device.client.get('/sync/overview')
            response.raise_for_status()
            return response.json()
        except Exception:
            raise HTTPException(503,'Cloud gateway is unavailable. Local memory remains usable.')
    @app.put('/api/cloud/memories/{id}')
    def cloud_edit(id:str,value:MemoryInput):
        import uuid
        from .policy import routing
        from .vectors import content
        if not device.status()['online']: raise HTTPException(503,'Cloud link is disabled.')
        if value.expected_version is None: raise HTTPException(422,'The cloud revision is required.')
        doc=value.model_dump(exclude={'expected_version'})
        if routing(doc)['route']!='cloud': raise HTTPException(422,'The control room can only save team-safe memories.')
        try: id=str(uuid.UUID(id))
        except ValueError: raise HTTPException(422,'Invalid memory ID.')
        doc.update(id=id,deleted=False)
        try:
            response=device.client.post('/sync/push',json={'operation_id':str(uuid.uuid4()),'device_id':'control-room','base_revision':value.expected_version,'document':doc,'vector':device.embedder.encode(content(doc)),'model':device.embedder.name})
            if response.status_code==409: raise HTTPException(409,'The cloud copy changed; reload it before saving.')
            response.raise_for_status()
            with device.lock,device.db: event(device.db,'cloud','Control room updated the shared memory',id)
            return response.json()['document']
        except httpx.HTTPError:
            raise HTTPException(503,'Cloud gateway unavailable; the control-room edit was not confirmed.')
    @app.post('/api/optimize')
    def optimize():
        with device.lock:
            changed=device.index.optimize()
            with device.db: event(device.db,'system','Qdrant Edge index optimized')
        return {'ok':True,'changed':changed}
    @app.get('/api/export')
    def export(format:str='json'):
        docs=device.list(True)
        if format=='json':
            return Response(json.dumps({'device':device.id,'memories':docs},indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="edgeatlas-memories.json"'})
        if format!='csv': raise HTTPException(422,'Use json or csv.')
        stream=io.StringIO()
        writer=csv.writer(stream)
        fields=['id','title','body','category','site','visibility','priority','source','version','cloud_revision','deleted']
        writer.writerow(fields)
        for doc in docs:
            writer.writerow([("'"+str(doc.get(f,''))) if str(doc.get(f,'')).startswith(('=','+','-','@','\t','\r')) else doc.get(f,'') for f in fields])
        return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="edgeatlas-memories.csv"'})
    dist=Path(__file__).resolve().parents[1]/'dist'
    if dist.exists():
        app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
        @app.get('/favicon.svg')
        def favicon(): return FileResponse(dist/'favicon.svg')
        @app.get('/{path:path}')
        def frontend(path:str):
            if path.startswith('api/'): raise HTTPException(404,'API route not found.')
            return FileResponse(dist/'index.html')
    return app
