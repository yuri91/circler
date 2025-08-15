{
  description = "CircleCI + Nix Dynamic Configuration Demo";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        
        # Example packages that form a dependency graph
        packageA = pkgs.runCommand "package-a" {} ''
          echo "Building package A (independent)"
          sleep 2
          mkdir -p $out
          echo "Package A built successfully" > $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';
        
        packageB = pkgs.runCommand "package-b" { 
          buildInputs = [ packageA ]; 
        } ''
          echo "Building package B (depends on A)"
          echo "Package A output: ${packageA}"
          sleep 3
          mkdir -p $out
          echo "Package B built successfully" > $out/result
          echo "Dependency: ${packageA}/result" >> $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';
        
        packageC = pkgs.runCommand "package-c" {} ''
          echo "Building package C (independent)"
          sleep 1
          mkdir -p $out
          echo "Package C built successfully" > $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';
        
        packageD = pkgs.runCommand "package-d" { 
          buildInputs = [ packageB packageC ]; 
        } ''
          echo "Building package D (depends on B and C)"
          echo "Package B output: ${packageB}"
          echo "Package C output: ${packageC}"
          sleep 2
          mkdir -p $out
          echo "Package D built successfully" > $out/result
          echo "Dependencies:" >> $out/result
          echo "  B: ${packageB}/result" >> $out/result
          echo "  C: ${packageC}/result" >> $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';

        # Tool for analyzing derivations and generating CircleCI config
        circleci-nix-generator = pkgs.writeScriptBin "circleci-nix-generator" ''
          #!${pkgs.python3}/bin/python3
          import json
          import sys
          import subprocess
          from pathlib import Path

          def get_derivation_info():
              """Get information about all derivations in the flake"""
              result = subprocess.run([
                  "nix", "flake", "show", "--json", "."
              ], capture_output=True, text=True, check=True)
              
              flake_info = json.loads(result.stdout)
              return flake_info

          def build_dependency_graph(packages):
              """Build a dependency graph from package information"""
              # This is a simplified version - in practice you'd use nix-store --query
              graph = {
                  "package-a": [],
                  "package-b": ["package-a"],
                  "package-c": [],
                  "package-d": ["package-b", "package-c"]
              }
              return graph

          def generate_circleci_config(dependency_graph):
              """Generate CircleCI configuration from dependency graph"""
              workflows = {}
              jobs = {}
              
              # Create a job for each package
              for package, deps in dependency_graph.items():
                  job_name = f"build-{package}"
                  jobs[job_name] = {
                      "docker": [{"image": "nixos/nix:latest"}],
                      "steps": [
                          "checkout",
                          {"run": {"command": f"nix build .#{package}"}},
                          {
                              "store_artifacts": {
                                  "path": f"/nix/store",
                                  "destination": f"artifacts/{package}"
                              }
                          }
                      ]
                  }
              
              # Create workflow with dependencies
              workflow_jobs = []
              for package, deps in dependency_graph.items():
                  job_name = f"build-{package}"
                  job_config = {"job": job_name}
                  
                  if deps:
                      job_config["requires"] = [f"build-{dep}" for dep in deps]
                  
                  workflow_jobs.append(job_config)
              
              workflows["build-all"] = {"jobs": workflow_jobs}
              
              config = {
                  "version": 2.1,
                  "jobs": jobs,
                  "workflows": workflows
              }
              
              return config

          def main():
              try:
                  # For this demo, we'll use a hardcoded dependency graph
                  # In practice, you'd analyze the actual Nix derivations
                  dependency_graph = build_dependency_graph({})
                  
                  config = generate_circleci_config(dependency_graph)
                  
                  # Write to continuation file for CircleCI
                  with open('/tmp/continuation-config.yml', 'w') as f:
                      import yaml
                      yaml.dump(config, f, default_flow_style=False)
                  
                  print("Generated CircleCI configuration successfully")
                  print(json.dumps(config, indent=2))
                  
              except Exception as e:
                  print(f"Error: {e}", file=sys.stderr)
                  sys.exit(1)

          if __name__ == "__main__":
              main()
        '';

      in
      {
        packages = {
          inherit packageA packageB packageC packageD;
          circleci-nix-generator = circleci-nix-generator;
          default = packageD;
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            nix
            python3
            python3Packages.pyyaml
            circleci-nix-generator
          ];
        };
      });
}
