#!/usr/bin/env python3
"""
Test the dependency analyzer without requiring Nix evaluation.
This simulates the analysis process for demonstration purposes.
"""

import json
import subprocess
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple
import tempfile
import os


class OfflineNixAnalyzer:
    """Offline version that doesn't require Nix evaluation"""
    
    def __init__(self, flake_path: str = "."):
        self.flake_path = Path(flake_path)
        self.dependency_graph = {}
        self.reverse_deps = {}
    
    def get_flake_outputs(self):
        """Mock flake outputs for testing"""
        return {
            "packages": {
                "x86_64-linux": {
                    "packageA": {"type": "derivation"},
                    "packageB": {"type": "derivation"},
                    "packageC": {"type": "derivation"},
                    "packageD": {"type": "derivation"},
                    "default": {"type": "derivation"}
                }
            }
        }
    
    def get_package_derivations(self):
        """Return mock package derivations"""
        return {
            "packageA": ".#packageA",
            "packageB": ".#packageB", 
            "packageC": ".#packageC",
            "packageD": ".#packageD"
        }
    
    def build_dependency_graph(self):
        """Build a dependency graph from package analysis"""
        dependency_graph = {
            "packageA": [],
            "packageB": ["packageA"],
            "packageC": [],
            "packageD": ["packageB", "packageC"]
        }
        
        # Build reverse dependency graph for topological sorting
        self.reverse_deps = {}
        for pkg, deps in dependency_graph.items():
            if pkg not in self.reverse_deps:
                self.reverse_deps[pkg] = []
            for dep in deps:
                if dep not in self.reverse_deps:
                    self.reverse_deps[dep] = []
                self.reverse_deps[dep].append(pkg)
        
        self.dependency_graph = dependency_graph
        return dependency_graph
    
    def topological_sort(self):
        """Perform topological sort to determine build order"""
        in_degree = {pkg: len(deps) for pkg, deps in self.dependency_graph.items()}
        queue = [pkg for pkg, degree in in_degree.items() if degree == 0]
        levels = []
        
        while queue:
            current_level = queue[:]
            levels.append(current_level)
            queue = []
            
            for pkg in current_level:
                for dependent in self.reverse_deps.get(pkg, []):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)
        
        return levels
    
    def generate_circleci_job(self, package_name: str, dependencies: List[str]):
        """Generate a CircleCI job configuration for a package"""
        job = {
            "docker": [{"image": "cimg/base:stable"}],
            "resource_class": "medium",
            "steps": [
                "checkout",
                {
                    "run": {
                        "name": "Install Nix",
                        "command": """curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install linux --extra-conf "experimental-features = nix-command flakes" --no-confirm
echo 'source /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh' >> $BASH_ENV"""
                    }
                },
                {
                    "run": {
                        "name": f"Build {package_name}",
                        "command": f"""
source /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
echo "Building {package_name}"
echo "Dependencies: {', '.join(dependencies) if dependencies else 'none'}"
nix build .#{package_name} -L
ls -la result*
echo "Build completed successfully"
                        """.strip()
                    }
                },
                {
                    "store_artifacts": {
                        "path": "result",
                        "destination": f"{package_name}-artifacts"
                    }
                }
            ]
        }
        return job
    
    def generate_circleci_config(self):
        """Generate complete CircleCI configuration"""
        dependency_graph = self.build_dependency_graph()
        
        jobs = {}
        workflow_jobs = []
        
        # Generate jobs for each package
        for package, deps in dependency_graph.items():
            job_name = f"build-{package.lower()}"
            jobs[job_name] = self.generate_circleci_job(package, deps)
            
            # Add to workflow with proper dependencies
            job_config = {"job": job_name}
            if deps:
                job_config["requires"] = [f"build-{dep.lower()}" for dep in deps]
            
            workflow_jobs.append(job_config)
        
        # Add integration test job
        final_packages = [pkg for pkg in dependency_graph.keys() 
                         if not self.reverse_deps.get(pkg)]
        
        if final_packages:
            jobs["integration-test"] = {
                "docker": [{"image": "cimg/base:stable"}],
                "resource_class": "small",
                "steps": [
                    "checkout",
                    {
                        "run": {
                            "name": "Install Nix",
                            "command": """curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install linux --extra-conf "experimental-features = nix-command flakes" --no-confirm
echo 'source /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh' >> $BASH_ENV"""
                        }
                    },
                    {
                        "run": {
                            "name": "Run integration tests",
                            "command": """
source /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
echo "Running integration tests..."
nix build .#default -L
echo "All packages integrated successfully!"
                            """.strip()
                        }
                    }
                ]
            }
            
            workflow_jobs.append({
                "job": "integration-test",
                "requires": [f"build-{pkg.lower()}" for pkg in final_packages]
            })
        
        config = {
            "version": 2.1,
            "jobs": jobs,
            "workflows": {
                "build-dependency-graph": {
                    "jobs": workflow_jobs
                }
            }
        }
        
        return config
    
    def save_config(self, config: Dict, output_path: str = "/tmp/continuation-config.yml"):
        """Save the generated configuration to a file"""
        with open(output_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        print(f"Configuration saved to {output_path}")
        return output_path


def main():
    print("🧪 Testing Nix Derivation Analyzer (Offline Mode)")
    print("================================================")
    
    analyzer = OfflineNixAnalyzer()
    
    print("\n📋 Building dependency graph...")
    dependency_graph = analyzer.build_dependency_graph()
    
    print("Dependency Graph:")
    for pkg, deps in dependency_graph.items():
        deps_str = ", ".join(deps) if deps else "none"
        print(f"  {pkg}: depends on [{deps_str}]")
    
    print("\n🔄 Performing topological sort...")
    build_levels = analyzer.topological_sort()
    
    print("Build Order (by level):")
    for i, level in enumerate(build_levels):
        print(f"  Level {i + 1}: {', '.join(level)}")
    
    print("\n⚙️  Generating CircleCI configuration...")
    config = analyzer.generate_circleci_config()
    
    print("Generated Jobs:")
    for job_name in config["jobs"].keys():
        print(f"  - {job_name}")
    
    print("\nWorkflow Dependencies:")
    workflow_jobs = config["workflows"]["build-dependency-graph"]["jobs"]
    for job in workflow_jobs:
        if isinstance(job, dict) and "requires" in job:
            print(f"  {job['job']} requires: {', '.join(job['requires'])}")
        else:
            job_name = job if isinstance(job, str) else job["job"]
            print(f"  {job_name} (no dependencies)")
    
    print("\n💾 Saving configuration...")
    output_path = analyzer.save_config(config, "/tmp/test-continuation-config.yml")
    
    print(f"\n✅ Test completed successfully!")
    print(f"Configuration saved to: {output_path}")
    
    # Show a snippet of the generated config
    print("\nGenerated Configuration (first 30 lines):")
    print("-" * 50)
    with open(output_path, 'r') as f:
        lines = f.readlines()[:30]
        for i, line in enumerate(lines, 1):
            print(f"{i:2d}: {line.rstrip()}")
    if len(lines) == 30:
        print("    ... (truncated)")


if __name__ == "__main__":
    main()