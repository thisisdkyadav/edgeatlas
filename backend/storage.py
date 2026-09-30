import json
import sqlite3
import time
from pathlib import Path

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA busy_timeout=5000')
    return db

def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)

def edge_schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, document TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS projection(record_id TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS outbox(record_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL, base_revision INTEGER NOT NULL, document TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS conflicts(record_id TEXT PRIMARY KEY, remote TEXT NOT NULL, detected_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS versions(seq INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, document TEXT NOT NULL, action TEXT NOT NULL, time REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, message TEXT NOT NULL, record_id TEXT, time REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS searches(seq INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL, mode TEXT NOT NULL, duration REAL NOT NULL, count INTEGER NOT NULL, time REAL NOT NULL);
    ''')
    db.commit()

def save_record(db, record, action='save'):
    db.execute('INSERT INTO memories VALUES(?,?) ON CONFLICT(id) DO UPDATE SET document=excluded.document', (record['id'],dump(record)))
    db.execute('INSERT INTO versions(record_id,document,action,time) VALUES(?,?,?,?)', (record['id'],dump(record),action,time.time()))
    db.execute('INSERT OR IGNORE INTO projection VALUES(?)',(record['id'],))

def records(db):
    return [json.loads(r['document']) for r in db.execute('SELECT document FROM memories')]

def get_record(db, id):
    row = db.execute('SELECT document FROM memories WHERE id=?', (id,)).fetchone()
    return json.loads(row['document']) if row else None

def event(db, kind, message, id=None):
    db.execute('INSERT INTO events(kind,message,record_id,time) VALUES(?,?,?,?)',(kind,message,id,time.time()))

def setting(db, key, default=None):
    row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return json.loads(row['value']) if row else default

def set_setting(db, key, value):
    db.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,dump(value)))
