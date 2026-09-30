import os
from pathlib import Path
from threading import RLock
from time import perf_counter
from fastembed import TextEmbedding
from qdrant_edge import (EdgeShard, EdgeConfig, EdgeVectorParams, EdgeSparseVectorParams, Distance, Modifier, Bm25, Point, UpdateOperation, Query, QueryRequest, Filter, FieldCondition, MatchValue, Prefetch, Fusion)

class Embeddings:
    dimensions = 384
    def __init__(self, offline=True):
        self.name = os.getenv('EDGE_MODEL', 'BAAI/bge-small-en-v1.5')
        if self.name != 'BAAI/bge-small-en-v1.5':
            raise ValueError('This index schema requires BAAI/bge-small-en-v1.5 (384 dimensions).')
        self.cache = Path(os.getenv('EDGE_MODEL_CACHE', './data/models')).resolve()
        self.cache.mkdir(parents=True, exist_ok=True)
        self.model = TextEmbedding(model_name=self.name, cache_dir=str(self.cache), threads=2, providers=['CPUExecutionProvider'], local_files_only=offline)
        self.lock = RLock()

    def encode(self, text, query=False):
        with self.lock:
            iterator = self.model.query_embed(text) if query else self.model.embed([text])
            return next(iter(iterator)).tolist()

def content(record):
    return record['title'] + '\n' + record['body'] + '\n' + ' '.join(record.get('tags', []))

class EdgeIndex:
    def __init__(self, path, embedder):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.bm25 = Bm25()
        self.lock = RLock()
        config = EdgeConfig(vectors={'dense': EdgeVectorParams(size=384, distance=Distance.Cosine, on_disk=True)}, sparse_vectors={'bm25': EdgeSparseVectorParams(modifier=Modifier.Idf)}, on_disk_payload=True, max_search_threads=2)
        self.shard = EdgeShard.load(str(path), config) if (path / 'edge_config.json').exists() else EdgeShard.create(str(path), config)

    def upsert(self, record, vector=None):
        with self.lock:
            if record.get('deleted'):
                self.shard.update(UpdateOperation.delete_points([record['id']]))
            else:
                text = content(record)
                point = Point(id=record['id'], vector={'dense': vector or self.embedder.encode(text), 'bm25': self.bm25.embed_document(text)}, payload={k: record.get(k, '') for k in ('title','category','visibility','site')})
                self.shard.update(UpdateOperation.upsert_points([point]))
            self.shard.flush()

    def search(self, query, mode='hybrid', limit=8, filters=None):
        start = perf_counter()
        conditions = [FieldCondition(key=key, match=MatchValue(value)) for key,value in (filters or {}).items() if value]
        where = Filter(must=conditions) if conditions else None
        with self.lock:
            keyword = Query.Nearest(self.bm25.embed_query(query), using='bm25')
            if mode == 'keyword':
                request = QueryRequest(query=keyword, filter=where, limit=limit, with_payload=True)
            else:
                dense = Query.Nearest(self.embedder.encode(query, query=True), using='dense')
                if mode == 'semantic':
                    request = QueryRequest(query=dense, filter=where, limit=limit, with_payload=True)
                else:
                    request = QueryRequest(query=Fusion.Rrf(k=60), prefetches=[Prefetch(query=dense, filter=where, limit=max(30,limit)), Prefetch(query=keyword, filter=where, limit=max(30,limit))], filter=where, limit=limit, with_payload=True)
            results = self.shard.query(request)
        return [{'id':str(p.id),'score':float(p.score)} for p in results], round((perf_counter()-start)*1000,2)

    def optimize(self):
        with self.lock:
            result = self.shard.optimize()
            self.shard.flush()
            return result

    def close(self):
        with self.lock:
            self.shard.flush()
            self.shard.close()
