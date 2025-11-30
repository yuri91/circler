from __future__ import annotations

import contextlib
import json
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class Derivation:
    name: str
    drv: str
    outputs: dict[str, str]
    deps: list[Derivation]
    meta: dict[str, Any]


def get_safe_name(name: str) -> str:
    return name.replace(".", "_")


def filter_cached(drvs: dict[str, Derivation]) -> None:
    paths = [i for d in drvs.values() for i in d.outputs.values()]
    out = subprocess.run(
        [
            "nix",
            "path-info",
            "--json",
            "--refresh",
            "--store",
            "https://nix.leaningtech.com/cheerp",
        ]
        + paths,
        stdout=subprocess.PIPE,
        check=True,
    )
    result: dict[str, Any] = json.loads(out.stdout)
    for d in list(drvs.values()):
        for o in d.outputs.values():
            if result.get(o) is None:
                break
        else:
            del drvs[d.name]


def filter_disabled(drvs: dict[str, Derivation]) -> None:
    for d in list(drvs.values()):
        disabled = False
        with contextlib.suppress(KeyError, TypeError):
            disabled = d.meta["ci"]["disabled"] is True
        if disabled:
            del drvs[d.name]


def get_all_deps(drv: str) -> list[str]:
    result = subprocess.run(
        ["nix-store", "--query", "--requisites", drv],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip().split("\n")


def load_derivations(items: list[Any]) -> dict[str, Derivation]:
    drvs = {
        i["attr"]: Derivation(
            name=i["attr"],
            drv=i["drvPath"],
            outputs=i["outputs"],
            deps=[],
            meta=i["meta"],
        )
        for i in items
    }
    filter_cached(drvs)
    filter_disabled(drvs)
    drvMap = {i.drv: drvs[i.name] for i in drvs.values()}
    for i in drvs.values():
        v = drvs[i.name]
        v.deps = [drvMap[d] for d in get_all_deps(i.drv) if d in drvMap and d != v.drv]

    return drvs
