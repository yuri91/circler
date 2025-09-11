from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from .circleci import DictRef, Executor, Job, JobInstance, Pipeline, Workflow
from .exec import env
from .steps import setup_steps


@dataclass
class Derivation:
    name: str
    drv: str
    outputs: dict[str, str]
    deps: list[Derivation]


def get_safe_name(name: str) -> str:
    return name.replace(".", "_")


def generate_build_job(
    p: Pipeline, executor: DictRef[Executor], drv: Derivation
) -> JobInstance:
    shell_path = env["SHELL_PATH"]
    job = p.job(
        get_safe_name(drv.name),
        Job(executor=executor, shell=shell_path, steps=setup_steps(shell_path) + []),
    )
    return JobInstance(job)


def generate_build_pipeline(drvs: dict[str, Derivation]) -> Pipeline:
    p = Pipeline(setup=False)
    docker = p.executor(
        "docker_large",
        Executor.docker(image="nixos/nix:latest", resource_class="large"),
    )
    jobs: dict[str, JobInstance] = {}
    for drv in drvs.values():
        jobs[drv.name] = generate_build_job(p, docker, drv)

    for name in jobs:
        for dep in drvs[name].deps:
            jobs[name].requires.append(jobs[dep.name].job)
    p.workflow("build-all", Workflow(jobs=list(jobs.values())))
    return p


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


def get_derivations() -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "nix-eval-jobs",
            "-E",
            "(import ./default.nix{}).ci.release",
            "--gc-roots-dir",
            ".",
            "--workers",
            "2",
            "--max-memory-size",
            "2G",
            "--verbose",
            "--log-format",
            "raw",
            "--check-cache-status",
        ],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    items = []
    for line in result.stdout.strip().split("\n"):
        i = json.loads(line)
        items.append(i)
    return items


def get_all_deps(drv: str) -> list[str]:
    result = subprocess.run(
        ["nix-store", "--query", "--requisites", drv],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip().split("\n")


def load_derivations() -> dict[str, Derivation]:
    items = get_derivations()

    drvs = {
        i["attr"]: Derivation(
            name=i["attr"], drv=i["drvPath"], outputs=i["outputs"], deps=[]
        )
        for i in items
    }
    filter_cached(drvs)
    drvMap = {i.drv: drvs[i.name] for i in drvs.values()}
    for i in drvs.values():
        v = drvs[i.name]
        v.deps = [drvMap[d] for d in get_all_deps(i.drv) if d in drvMap and d != v.drv]

    return drvs


def prune_graph(g: dict[str, Derivation]) -> dict[str, Derivation]:
    pruned = {
        k: Derivation(name=v.name, drv=v.drv, outputs=v.outputs, deps=[])
        for (k, v) in g.items()
    }
    for cur in g:
        for dx in g[cur].deps:
            dx_needed = True
            for dy in g[cur].deps:
                if dx in dy.deps:
                    dx_needed = False
                    break
            if dx_needed:
                pruned[cur].deps.append(dx)
    return pruned


def main() -> None:
    drvs = load_derivations()
    drvs = prune_graph(drvs)
    config = generate_circleci_config(drvs)
    print(json.dumps(config, indent=2))
