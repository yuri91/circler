from __future__ import annotations

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


def generate_circleci_job(drv: Derivation) -> dict[str, Any]:
    job = {
        "docker": [{"image": "nixos/nix:latest"}],
        "resource_class": "large",
        "steps": [
            "checkout",
            {
                "run": {
                    "name": "Configure Nix",
                    "command": """
cat \\<< 'EOF' > /etc/nix/nix.conf
  cores = 4
  experimental-features = nix-command flakes ca-derivations
  max-jobs = 2
  sandbox = false
  sandbox-fallback = true
  system-features = nixos-test benchmark big-parallel kvm
  substituters = https://nix.leaningtech.com/cheerp https://cache.nixos.org/
  trusted-public-keys = cheerp:WtaH6hNyE1jx3KqrDkTqHfub4qEBhJWZwiIuPAPqF44= lt:990XBPGBQWHGyzpLno3a5vfWo5G8O+0qlxRmrvbOQVQ= cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY=
  trusted-users = root circleci
EOF
nix run nixpkgs#attic-client -- login lt 'https://nix.leaningtech.com' ${ATTIC_TOKEN}
""",
                }
            },
            {
                "run": {
                    "name": f"Build {drv.name}",
                    "no_output_timeout": "20m",
                    "command": f"""
nix-store --add-root result --realize {drv.drv}
""",
                }
            },
            {
                "run": {
                    "name": "Upload to cache",
                    "command": """
nix run nixpkgs#attic-client push lt:cheerp result*
""",
                }
            },
        ],
    }
    return job


def get_safe_name(name: str) -> str:
    return name.replace(".", "_")


def generate_circleci_config(drvs: dict[str, Derivation]) -> dict[str, Any]:
    jobs = {}
    workflow_jobs = []

    # Generate jobs for each package
    for drv in drvs.values():
        safe_name = get_safe_name(drv.name)
        jobs[safe_name] = generate_circleci_job(drv)

        job_config: dict[str, Any] = {safe_name: {}}
        if drv.deps:
            job_config[safe_name]["requires"] = [
                get_safe_name(dep.name) for dep in drv.deps
            ]

        workflow_jobs.append(job_config)

    config = {
        "version": 2.1,
        "jobs": jobs,
        "workflows": {"build-all": {"jobs": workflow_jobs}},
    }

    return config


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

if __name__ == "__main__":
    main()
