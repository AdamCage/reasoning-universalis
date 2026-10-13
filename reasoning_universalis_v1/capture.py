"""The sole read-only file-reading hook, called before kernel binding."""
from pathlib import Path
from episteme.domains import api
from .inventory import verify


def capture(source):
    root = Path(source)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Capture needs a plain directory')
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Capture links forbidden')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    checked = verify(files)
    return api.CaptureBundle(pack_id='reasoning_universalis_v1', pack_version='1',
                             source_label='stage2_external_observation_import', files=files,
                             audit={'purpose': checked['purpose'], 'attempts': len(checked['observations']),
                                    'external_inference': True, 'scientific_validity': 'not_assessed'})
