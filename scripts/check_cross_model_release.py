"""Check and replay the portable payload without using checkout-specific frozen bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.export_cross_model import verify


def main():
    manifest=ROOT/'evidence/cross-model-compat-2026-11-15/manifest.json'
    verify(manifest)
    with tempfile.TemporaryDirectory(prefix='cm-release-') as temp:
        target=Path(temp)
        with zipfile.ZipFile(manifest.parent/'evidence.zip') as z:z.extractall(target)
        assert not (target/'.env').exists() and not (target/'.research').exists()
        code="import socket,runpy,sys;socket.create_connection=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Network blocked'));sys.argv=['scripts/reproduce_cross_model_compat.py','--output','replayed'];runpy.run_path(sys.argv[0],run_name='__main__')"
        subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=target,check=True)
        original=target/'artifacts/cross-model-compat-2026-11-15/analysis'
        files=['summary.json','item-level.json','agreement.csv']+[p.name for p in original.glob('*-confusion.csv')]
        for name in files:
            assert (original/name).read_bytes()==(target/'replayed'/name).read_bytes(),name
        print(json.dumps({'status':'passed','exact_files':len(files),'network_blocked':True,'paid_calls':0}))


if __name__=='__main__':main()
