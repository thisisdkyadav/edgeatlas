import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.pydeps'))
sys.path.insert(0,str(ROOT))
os.environ['HF_HUB_OFFLINE']='1'
os.environ['EDGE_AUTO_SYNC']='false'
os.environ['EDGE_SEED']='false'
os.environ['EDGE_SYNC_TOKEN']='local-demo-sync-token'
os.environ['EDGE_APP_TOKEN']=''
os.environ['EDGE_HOST']='127.0.0.1'
os.environ['CLOUD_HOST']='127.0.0.1'
os.environ['EDGE_MODEL_CACHE']=str(ROOT/'data/models')
