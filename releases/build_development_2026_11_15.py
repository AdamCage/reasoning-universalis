"""Build release assets solely from committed Git bytes; never call models."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(commit,output):
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
    commit=git('rev-parse','--verify',commit+'^{commit}').decode().strip()
    def blob(path):return git('show',commit+':'+path)
    prefix='evidence/cross-model-compat-2026-11-15/'
    manifest=json.loads(blob(prefix+'manifest.json'));raw=blob(prefix+'evidence.zip')
    assert sha(raw)==manifest['archive']['sha256'] and len(raw)==manifest['archive']['bytes']
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist();assert len(names)==len(set(names))
        expected={r['path']:r for r in manifest['payload']['files']}
        assert set(names)==set(expected)
        for name in names:
            data=z.read(name);assert sha(data)==expected[name]['sha256'] and len(data)==expected[name]['bytes']
    output.mkdir(parents=True,exist_ok=False)
    (output/'cross-model-replay-2026-11-15.zip').write_bytes(raw)
    (output/'cross-model-measurement-pilot.pdf').write_bytes(blob('output/pdf/cross-model-measurement-pilot.pdf'))
    assets=[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(output.iterdir())]
    result={'schema_version':1,'source_commit':commit,'tag':'development-2026-11-15','reference_runtime':'CPython 3.13.1',
            'scope':'Exploratory instrument portability; no human gold; E0 not passed; collection closed',
            'evidence_manifest_sha256':sha(blob(prefix+'manifest.json')),'assets':assets}
    (output/'release-manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    checks=''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in sorted(output.iterdir()))
    (output/'SHA256SUMS.txt').write_text(checks,encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--commit',default='HEAD');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.commit,a.output)
