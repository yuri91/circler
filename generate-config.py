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
    drv: str
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
                    "name": "Make nix store writable for cache restore",
                    "command": "sudo chmod -R u+w /nix/store || true"
                }
            },
            {
                "restore_cache": {
                    "keys": ["<< pipeline.parameters.eval-cache-key >>"] + [f"nix-store-{dep.drv.split('/')[-1]}" for dep in drv.deps]
                }
            },
            {
                "run": {
                    "name": "Undo writable nix store",
                    "command": "sudo chmod -R 555 /nix/store && sudo chmod 777 /nix/store"
                }
            },
            {
                "run": {
                    "name": f"Build {drv.name}",
                    "command": f"""
nix-store --realize {drv.drv}
ls -la result*
"""
                }
            },
            {
                "save_cache": {
                    "key": f"nix-store-{drv.drv.split('/')[-1]}",
                    "paths": ["/nix/store"],
                }
            },
        ]
    }
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

def load_derivations() -> Dict[str, Derivation]:
    graph = json.load(open(sys.argv[1], "r"))

    drvs = { k:Derivation(name=k, drv=v["drv"], deps=[]) for (k,v) in graph.items() }
    drvMap = { v["drv"]:drvs[k] for (k,v) in graph.items()}
    for (k,v) in drvs.items():
        v.deps = [ drvMap[d] for d in graph[k]["deps"]]

    return drvs

drvs = load_derivations()
config = generate_circleci_config(drvs)
print(json.dumps(config, indent=2))
