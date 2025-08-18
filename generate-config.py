#!/usr/bin/env nix
#! nix shell nixpkgs#nix-eval-jobs nixpkgs#python3 --command python3

from __future__ import annotations
import json
from dataclasses import dataclass
from typing import List, Dict
import subprocess


@dataclass
class Derivation:
    name: str
    drv: str
    deps: List[Derivation]

def generate_circleci_job(drv: Derivation) -> Dict:
    job = {
        "docker": [{"image": "nixos/nix:latest"}],
        "resource_class": "medium",
        "steps": [
            "checkout",
            {
                "run": {
                    "name": "Configure Nix",
                    "command": """
cat \\<< 'EOF' > /etc/nix/nix.conf
  cores = 0
  experimental-features = nix-command flakes ca-derivations
  max-jobs = auto
  sandbox = false
  sandbox-fallback = true
  substituters = https://cache.nixos.org/
  system-features = nixos-test benchmark big-parallel kvm
  trusted-public-keys = cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY=
  trusted-substituters = 
  trusted-users = root circleci
EOF
""",
                }
            },
            {
                "restore_cache": {
                    "keys": ["<< pipeline.parameters.eval-cache-key >>"]
                }
            },
            {
                "run": {
                    "name": "Import eval cache",
                    "command": f"""
nix copy --all --from file://$(pwd)/cache
"""
                }
            },
            {
                "run": {
                    "name": f"Build {drv.name}",
                    "command": f"""
nix-store --add-root result --realize {drv.drv}
"""
                }
            },
            {
                "run": {
                    "name": f"Export NAR",
                    "command": f"""
mkdir -p nars
nix-store --export result > nars/{drv.name}.nar
"""
                }
            },
            {
                "save_cache": {
                    "key": f"nix-store-{drv.drv.split('/')[-1]}",
                    "paths": ["nars"],
                }
            },
        ]
    }
    cache_steps = []
    for dep in drv.deps:
        cache_steps.append({
            "restore_cache": {
                "keys": [f"nix-store-{dep.drv.split('/')[-1]}"]
            },
        })
        cache_steps.append({
            "run": {
                "name": f"Import NAR for dep {dep.name}",
                "command": f"nix-store --import < nars/{dep.name}.nar"
            },
        })

    job["steps"] = job["steps"][:3] + cache_steps + job["steps"][3:]
    return job


def generate_circleci_config(drvs: Dict[str, Derivation]) -> Dict:
    jobs = {}
    workflow_jobs = []

    # Generate jobs for each package
    for drv in drvs.values():
        jobs[drv.name] = generate_circleci_job(drv)

        job_config: Dict = {drv.name:{}}
        if drv.deps:
            job_config[drv.name]["requires"] = [ dep.name for dep in drv.deps]

        workflow_jobs.append(job_config)

    config = {
        "version": 2.1,
        "parameters": {
            "eval-cache-key": {
                "type": "string",
                "default": "",
            },
        },
        "jobs": jobs,
        "workflows": {
            "build-all": {
                "jobs": workflow_jobs
            }
        }
    }

    return config

def get_derivations() -> List[Dict]:
    result = subprocess.run(
               ["nix-eval-jobs", "--flake", ".#packages.x86_64-linux", "--gc-roots-dir", "."],
               capture_output=True,
               text=True,
               check=True
           )
    items = []
    for line in result.stdout.strip().split('\n'):
        items.append(json.loads(line))
    return items

def get_all_deps(drv: str) -> List[str]:
    result = subprocess.run(
               ["nix-store", "--query", "--requisites", drv],
               capture_output=True,
               text=True,
               check=True
           )
    return result.stdout.strip().split('\n')

def load_derivations() -> Dict[str, Derivation]:
    items = get_derivations()

    drvs = { i["attr"]:Derivation(name=i["attr"], drv=i["drvPath"], deps=[]) for i in items }
    drvMap = { i["drvPath"]:drvs[i["attr"]] for i in items}
    for i in items:
        v = drvs[i["attr"]]
        v.deps = [ drvMap[d] for d in get_all_deps(i["drvPath"]) if d in drvMap and d != v.drv]

    return drvs

drvs = load_derivations()
config = generate_circleci_config(drvs)
print(json.dumps(config, indent=2))
