#!/usr/bin/env python3
"""
Advanced Nix derivation analyzer for CircleCI dynamic configuration.
This script analyzes Nix derivations, builds a dependency graph, and generates
CircleCI workflows that respect the dependency ordering.
"""

import json
import subprocess
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple
import tempfile
import os


class NixDerivationAnalyzer:
    def __init__(self, flake_path: str = "."):
        self.flake_path = Path(flake_path)
        self.dependency_graph = {}
        self.reverse_deps = {}
        
    def get_flake_outputs(self) -> Dict:
        """Get all outputs from the flake"""
        try:
            result = subprocess.run([
                "nix", "flake", "show", "--json", str(self.flake_path)
            ], capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error getting flake outputs: {e.stderr}", file=sys.stderr)
            raise
    
    def get_package_derivations(self) -> Dict[str, str]:
        """Get derivation paths for all packages"""
        packages = {}
        flake_outputs = self.get_flake_outputs()
        
        # Extract packages from flake show output
        systems = flake_outputs.get("packages", {})
        for system, system_packages in systems.items():
            for pkg_name, pkg_info in system_packages.items():
                if pkg_name != "default":  # Skip default package for now
                    packages[pkg_name] = f".#{pkg_name}"
        
        return packages
    
    def analyze_derivation_dependencies(self, derivation_path: str) -> List[str]:
        """Analyze dependencies of a specific derivation"""
        try:
            # Get the store path for the derivation
            result = subprocess.run([
                "nix", "path-info", "--derivation", derivation_path
            ], capture_output=True, text=True, check=True)
            
            drv_path = result.stdout.strip()
            
            # Query dependencies
            result = subprocess.run([
                "nix-store", "--query", "--references", drv_path
            ], capture_output=True, text=True, check=True)
            
            references = result.stdout.strip().split('\n') if result.stdout.strip() else []
            
            # Filter for .drv files (other derivations)
            derivation_deps = [ref for ref in references if ref.endswith('.drv')]
            return derivation_deps
            
        except subprocess.CalledProcessError:
            # Fallback: return empty list if we can't analyze
            return []
    
    def build_dependency_graph(self) -> Dict[str, List[str]]:
        """Build a dependency graph from package analysis"""
        packages = self.get_package_derivations()
        
        # For this demo, we'll use the known dependencies from our flake
        # In a real implementation, you'd analyze the actual derivations
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
    
    def topological_sort(self) -> List[List[str]]:
        """Perform topological sort to determine build order"""
        # Kahn's algorithm for topological sorting
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
    
    def generate_circleci_job(self, package_name: str, dependencies: List[str]) -> Dict:
        """Generate a CircleCI job configuration for a package"""
        job = {
            "docker": [{"image": "cimg/base:stable"}],
            "resource_class": "medium",
            "steps": [
                "checkout",
                {
                    "run": {
                        "name": "Install Nix",
                        "command": """curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install linux \\
  --extra-conf "experimental-features = nix-command flakes" \\
  --no-confirm \\
  --init none \\
  --no-start-daemon
echo '. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh' >> $BASH_ENV"""
                    }
                },
                {
                    "run": {
                        "name": f"Build {package_name}",
                        "command": f"""
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
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
        
        # Add cache restoration for dependencies
        if dependencies:
            cache_steps = []
            for dep in dependencies:
                cache_steps.append({
                    "restore_cache": {
                        "keys": [f"nix-store-{dep}-{{{{ checksum \"flake.lock\" }}}}"]
                    }
                })
            job["steps"] = job["steps"][:1] + cache_steps + job["steps"][1:]
            
            # Add cache saving
            job["steps"].append({
                "save_cache": {
                    "key": f"nix-store-{package_name}-{{{{ checksum \"flake.lock\" }}}}",
                    "paths": ["/nix/store"]
                }
            })
        
        return job
    
    def generate_circleci_config(self) -> Dict:
        """Generate complete CircleCI configuration"""
        dependency_graph = self.build_dependency_graph()
        build_levels = self.topological_sort()
        
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
                            "command": """curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install linux \\
  --extra-conf "experimental-features = nix-command flakes" \\
  --no-confirm \\
  --init none \\
  --no-start-daemon
echo '. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh' >> $BASH_ENV"""
                        }
                    },
                    {
                        "run": {
                            "name": "Run integration tests",
                            "command": """
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
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
    analyzer = NixDerivationAnalyzer()
    
    try:
        print("Analyzing Nix derivations...")
        config = analyzer.generate_circleci_config()
        
        print("Generated CircleCI configuration:")
        print(yaml.dump(config, default_flow_style=False, sort_keys=False))
        
        output_path = analyzer.save_config(config)
        print(f"\nConfiguration written to: {output_path}")
        
        # Print dependency graph information
        print("\nDependency Analysis:")
        print("===================")
        for pkg, deps in analyzer.dependency_graph.items():
            deps_str = ", ".join(deps) if deps else "none"
            print(f"{pkg}: depends on [{deps_str}]")
        
        print("\nBuild Order:")
        print("============")
        levels = analyzer.topological_sort()
        for i, level in enumerate(levels):
            print(f"Level {i + 1}: {', '.join(level)}")
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()