"""Portable launcher: supports normal pip environments or this project's isolated .pydeps."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.pydeps'))
sys.path.insert(0, str(ROOT))
if (ROOT / '.env').exists():
    for line in (ROOT / '.env').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'edge'
    if mode == 'warm-model':
        from backend.vectors import Embeddings
        model = Embeddings(offline=False)
        print({'model': model.name, 'dimensions': model.dimensions, 'ready': len(model.encode('equipment maintenance'))})
    elif mode == 'test':
        import pytest
        raise SystemExit(pytest.main(sys.argv[2:] or ['tests', '-q']))
    elif mode in ('edge', 'cloud'):
        import uvicorn
        module = 'backend.app:create_app' if mode == 'edge' else 'backend.cloud:create_app'
        prefix = 'EDGE' if mode == 'edge' else 'CLOUD'
        uvicorn.run(module, factory=True, host=os.getenv(prefix + '_HOST', '127.0.0.1'), port=int(os.getenv(prefix + '_PORT', '4100' if mode == 'edge' else '4200')))
    else:
        raise SystemExit('Use: python run.py [edge|cloud|warm-model|test]')
