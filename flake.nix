{
  description = "CircleCI + Nix Dynamic Configuration Demo";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Example packages that form a dependency graph
        packageA = pkgs.runCommand "package-a" { } ''
          echo "Building package A (independent)"
          sleep 3
          mkdir -p $out
          echo "Package A built successfully" > $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';

        packageB = pkgs.runCommand "package-b"
          {
            buildInputs = [ packageA ];
          } ''
          echo "Building package B (depends on A)"
          echo "Package A output: ${packageA}"
          sleep 4
          mkdir -p $out
          echo "Package B built successfully" > $out/result
          echo "Dependency: ${packageA}/result" >> $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';

        packageC = pkgs.runCommand "package-c" { } ''
          echo "Building package C (independent)"
          sleep 5
          mkdir -p $out
          echo "Package C built successfully" > $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';

        packageD = pkgs.runCommand "package-d"
          {
            buildInputs = [ packageB packageC ];
          } ''
          echo "Building package D (depends on B and C)"
          echo "Package B output: ${packageB}"
          echo "Package C output: ${packageC}"
          sleep 6
          mkdir -p $out
          echo "Package D built successfully" > $out/result
          echo "Dependencies:" >> $out/result
          echo "  B: ${packageB}/result" >> $out/result
          echo "  C: ${packageC}/result" >> $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';
      in
      {
        packages = {
          inherit packageA packageB packageC packageD;
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python3
          ];
        };
      });
}
