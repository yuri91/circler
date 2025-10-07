import os
import pickle
import sys
from typing import Any

import sh as _sh  # type: ignore

try:
    with open("/tmp/env.pickle", "rb") as p:
        env = pickle.load(p)
except FileNotFoundError:
    env = os.environ.copy()

sh = _sh.bake(_tee=True, _out=sys.stdout, _err=sys.stderr)


def export(key: str, val: Any) -> None:
    env[key] = val
    with open("/tmp/env.pickle", "wb") as p:
        pickle.dump(env, p)
