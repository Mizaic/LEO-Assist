"""Test GPU DLPack in subprocess with identical trainer environment."""
import sys
import subprocess
import tempfile
import pathlib

sys.path.insert(0, 'services/training_worker')
from app.trainer import _build_env, _should_use_gpu

use_gpu = _should_use_gpu()
print('GPU preflight:', use_gpu)

env = _build_env()

test_script = pathlib.Path(tempfile.mktemp(suffix='_spacy_gpu_test.py'))
test_script.write_text("""
import warnings
warnings.filterwarnings('ignore')
import cupy as cp
import torch
print('CuPy:', cp.__version__)
print('Torch:', torch.__version__)

import thinc.api
success = thinc.api.prefer_gpu()
print('prefer_gpu():', success)

from thinc.util import xp2torch, torch2xp
a = cp.zeros((2, 768), dtype=cp.float32)
t = xp2torch(a, device=torch.device('cuda:0'))
print('xp2torch OK, device:', t.device)
back = torch2xp(t)
print('torch2xp OK, device:', back.device)
print('ALL OK')
""", encoding='utf-8')

result = subprocess.run(
    [sys.executable, '-u', str(test_script)],
    capture_output=True, text=True, env=env, timeout=60
)
print('--- STDOUT ---')
print(result.stdout)
print('--- STDERR (last 3000 chars) ---')
print(result.stderr[-3000:])
print('Return code:', result.returncode)
test_script.unlink(missing_ok=True)
