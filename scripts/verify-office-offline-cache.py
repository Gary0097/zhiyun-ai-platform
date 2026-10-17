"""Prove the exact archive can install all pinned office packages offline."""
import argparse
from pathlib import Path, PurePosixPath
import os
import shutil
import subprocess
import tempfile
import zipfile


def verify(archive, scratch):
    prefix = 'apps/zhizaoyunAIOS/runtime/cache/'
    lock = 'skills/office/requirements-office-windows.lock.txt'
    scratch.mkdir(parents=True, exist_ok=True)
    # TemporaryDirectory owns only its unique child of the supplied scratch root.
    with tempfile.TemporaryDirectory(prefix='office-cache-', dir=scratch) as directory:
        target = Path(directory).resolve()
        cache = target / 'cache'
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                name = entry.filename.removeprefix('./')
                if not name.startswith(prefix) or entry.is_dir():
                    continue
                relative = PurePosixPath(name[len(prefix):])
                if relative.is_absolute() or '..' in relative.parts or any(':' in p or '\\' in p for p in relative.parts):
                    raise ValueError('Unsafe cache path')
                destination = cache.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(entry) as source, destination.open('wb') as output:
                    shutil.copyfileobj(source, output)
            requirements = target / 'office.txt'
            requirements.write_bytes(bundle.read(lock))
        uv = cache / 'bin/uv.exe'
        interpreters = sorted((cache / 'python').glob('*/python.exe'))
        if not uv.is_file() or not interpreters:
            raise RuntimeError('Archive missing uv or managed Python')
        environment = dict(os.environ, UV_OFFLINE='1', UV_CACHE_DIR=str(cache / 'uv'), UV_PYTHON_DOWNLOADS='never')
        venv = target / 'venv'
        subprocess.run([str(uv), 'venv', '--offline', '--python', str(interpreters[0]), str(venv)], env=environment, check=True)
        subprocess.run([str(uv), 'pip', 'install', '--offline', '--link-mode', 'copy', '--python', str(venv / 'Scripts/python.exe'), '-r', str(requirements)], env=environment, check=True)
        print('PASS exact packaged cache installs every locked office dependency offline', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    args = parser.parse_args()
    verify(args.archive, args.scratch)
