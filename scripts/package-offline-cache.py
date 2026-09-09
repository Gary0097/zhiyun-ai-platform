"""Build a candidate from clean source and an existing compatible offline ZIP.

Cached files are streamed between archives, avoiding extraction of tens of
thousands of immutable dependency files. Every reused member gets a CRC check.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import zipfile

p = argparse.ArgumentParser()
p.add_argument('--source', required=True)
p.add_argument('--cache-archive', required=True)
p.add_argument('--output', required=True)
args = p.parse_args()
source = Path(args.source).resolve()
output = Path(args.output).resolve()
baseline = Path(args.cache_archive).resolve()
assert output != baseline, 'Output must differ from cache archive'
cache_prefix = 'apps/zhizaoyunAIOS/runtime/cache/'
lock_path = 'apps/zhizaoyunAIOS/qwenpaw.lock.json'
temp = output.with_suffix('.building.zip')
assert not temp.exists(), 'Unfinished archive exists; inspect it before retrying'
with zipfile.ZipFile(baseline) as old:
    members = {}
    for entry in old.infolist():
        name = entry.filename.removeprefix('./')
        assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts, 'Unsafe archive path'
        assert name not in members, 'Duplicate archive entry'
        members[name] = entry
    assert json.loads(old.read(members[lock_path])) == json.loads((source / lock_path).read_text()), 'Runtime lock mismatch'
    assert cache_prefix + 'bin/uv.exe' in members, 'Windows uv missing'
    assert any(n.startswith(cache_prefix + 'python/') and n.endswith('/python.exe') for n in members), 'Managed Python missing'
    count = 0
    try:
        with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as result:
            for name, entry in members.items():
                if name.startswith(cache_prefix) and not entry.is_dir():
                    result.writestr(name, old.read(entry))
                    count += 1
            for folder, dirs, files in os.walk(source):
                dirs[:] = [d for d in dirs if d != '.git']
                for filename in files:
                    path = Path(folder) / filename
                    name = path.relative_to(source).as_posix()
                    if name == '.git' or name.startswith(cache_prefix):
                        continue
                    assert not path.is_symlink(), 'Source symlinks are not supported'
                    result.write(path, name)
        with zipfile.ZipFile(temp) as verify:
            assert verify.testzip() is None, 'Candidate CRC check failed'
        os.replace(temp, output)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
print(f'Candidate archive verified; reused {count} cache files')
