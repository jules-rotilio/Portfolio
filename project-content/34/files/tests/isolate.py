"""Imported first by every test module: keeps the tests away from the real
~/.config/valkyrie and ~/.local/share/valkyrie."""
import atexit
import os
import shutil
import tempfile

ROOT = tempfile.mkdtemp(prefix='valkyrie-tests-')
os.environ['VALKYRIE_CONFIG_DIR'] = os.path.join(ROOT, 'config')
atexit.register(shutil.rmtree, ROOT, ignore_errors=True)
