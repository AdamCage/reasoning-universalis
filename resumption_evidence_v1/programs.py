"""Offline byte checks; reanalysis uses the same bytes and is not replication."""
PRIMARY = '''import base64, hashlib, json, pathlib, sys
if len(sys.argv)!=4 or sys.argv[2]!='--seed': raise SystemExit('expected INPUT --seed INDEX')
data=json.loads(pathlib.Path(sys.argv[1]).read_bytes()); unit=int(sys.argv[3])
artifact=data['artifacts'][unit]
raw={'schema_version':1,'roster_unit':unit,'manifest_sha256':data['manifest_sha256'],'artifact':artifact}
source=base64.b64decode(artifact['base64'],validate=True)
if len(source)!=artifact['bytes'] or hashlib.sha256(source).hexdigest()!=artifact['sha256']: raise SystemExit('artifact mismatch')
if artifact['format']=='json': json.loads(source)
value=len(source)
'''
REANALYSIS = '''import binascii, hashlib, json, pathlib, sys
if len(sys.argv)!=4 or sys.argv[2]!='--seed': raise SystemExit('expected INPUT --seed INDEX')
raw=json.loads(pathlib.Path(sys.argv[1]).read_bytes())
if raw['roster_unit']!=int(sys.argv[3]): raise SystemExit('foreign artifact index')
artifact=raw['artifact']; source=binascii.a2b_base64(artifact['base64'],strict_mode=True)
digest=hashlib.new('sha256'); digest.update(source)
if digest.hexdigest()!=artifact['sha256'] or len(source)!=artifact['bytes']: raise SystemExit('artifact mismatch')
if artifact['format']=='json': json.loads(source.decode('utf-8'))
value=sum(1 for _ in source)
'''
TAIL = '''pathlib.Path('raw.json').write_bytes(json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode())
pathlib.Path('metrics.json').write_bytes(json.dumps({'captured_bytes':value},sort_keys=True,separators=(',',':'),allow_nan=False).encode())
'''
PYPROJECT = b'[project]\nname = "resumption-evidence-offline"\nversion = "0"\nrequires-python = ">=3.11"\ndependencies = []\n\n[tool.uv]\npackage = false\n'
UV_LOCK = b'version = 1\nrevision = 3\nrequires-python = ">=3.11"\n\n[[package]]\nname = "resumption-evidence-offline"\nversion = "0"\nsource = { virtual = "." }\n'
