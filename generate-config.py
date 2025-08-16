#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
from dataclasses import dataclass
from collections import defaultdict
from typing import List, Dict


@dataclass
class Derivation:
    name: str
    path: str
    deps: List[Derivation]

def generate_circleci_job(drv: Derivation) -> Dict:
    job = {
        "docker": [{"image": "cimg/base:stable"}],
        "resource_class": "medium",
        "steps": [
            "checkout",
            {
                "run": {
                    "name": "Install Nix",
                    "command": """
cat \\<< 'EOF' > /tmp/nix.conf
  allowed-users = *
  builders = 
  builders-use-substitutes = true
  cores = 0
  experimental-features = nix-command flakes ca-derivations
  keep-derivations = true
  keep-outputs = true
  max-jobs = auto
  require-sigs = true
  sandbox = false
  sandbox-fallback = true
  substituters = https://cache.nixos.org/
  system-features = nixos-test benchmark big-parallel kvm
  trusted-public-keys = cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY=
  trusted-substituters = 
  trusted-users = root circleci
EOF
sh <(curl -L https://nixos.org/nix/install) --no-daemon
sudo mkdir -p /etc/nix/
sudo mv /tmp/nix.conf /etc/nix/
echo 'export USER=circleci' >> $BASH_ENV
echo '. /home/circleci/.nix-profile/etc/profile.d/nix.sh' >> $BASH_ENV
""",
                }
            },
            {
                "run": {
                    "name": f"Build {drv.name}",
                    "command": f"""
nix build .#{drv.name} -L
ls -la result*
                    """.strip()
                }
            },
            {
                "save_cache": {
                    "key": f"nix-store-{drv.path.split('/')[-1]}",
                    "paths": ["/nix/store"],
                }
            },
        ]
    }
    if drv.deps:
        cache_step = {
            "restore_cache": {
                "keys": [f"nix-store-{dep.path.split('/')[-1]}" for dep in drv.deps]
            }
        }
        job["steps"] = job["steps"][:2] + [cache_step] + job["steps"][2:]
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
        "jobs": jobs,
        "workflows": {
            "build-all": {
                "jobs": workflow_jobs
            }
        }
    }

    return config

def load_derivations() -> Dict[str, Derivation]:
    graph = json.load(open(sys.argv[1], "r"))

    drvs = { k:Derivation(name=k, path=v["path"], deps=[]) for (k,v) in graph.items() }
    pathMap = { v["path"]:drvs[k] for (k,v) in graph.items()}
    for (k,v) in drvs.items():
        v.deps = [ pathMap[d] for d in graph[k]["deps"]]

    return drvs

drvs = load_derivations()
config = generate_circleci_config(drvs)
print(json.dumps(config, indent=2))
