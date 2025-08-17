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
          sleep 2
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
          sleep 3
          mkdir -p $out
          echo "Package B built successfully" > $out/result
          echo "Dependency: ${packageA}/result" >> $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';

        packageC = pkgs.runCommand "package-c" { } ''
          echo "Building package C (independent)"
          sleep 1
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
          sleep 2
          mkdir -p $out
          echo "Package D built successfully" > $out/result
          echo "Dependencies:" >> $out/result
          echo "  B: ${packageB}/result" >> $out/result
          echo "  C: ${packageC}/result" >> $out/result
          echo "Build timestamp: $(date)" >> $out/result
        '';
        collect-direct-deps = attrs: pkgs.runCommand "collect-direct-deps"
          rec {
            __structuredAttrs = true;
            exportReferencesGraph = pkgs.lib.mapAttrs'
              (name: val:
                pkgs.lib.nameValuePair "graph-${name}" val.drvPath
              )
              attrs;
            names = builtins.attrNames attrs;
            paths = builtins.attrValues attrs;
            drvs = map (p: p.drvPath) paths;
            nativeBuildInputs = with pkgs; [ jq ];
          } ''
          for i in "''${!names[@]}"; do
            deps=("''${paths[@]:0:$i}" "''${paths}[@]:$((i+1))")
            jq ".\"graph-''${names[$i]}\" | [.[] | select(.path | IN(\$ARGS.positional[])) | .path] | {\"''${names[$i]}\": {deps:., path:\"''${paths[$i]}\", drv:\"''${drvs[$i]}\"}}" "$NIX_ATTRS_JSON_FILE" --args "''${deps[@]}" > "$i.json"
          done
          jq --slurp 'add' *.json > $out
        '';

        make-config = attrs:
          let
            deps = collect-direct-deps attrs;
          in
          pkgs.runCommand "config"
            {
              nativeBuildInputs = with pkgs; [ python3 ];
            } ''
            python3 ${./generate-config.py} ${deps} > $out
          '';
      in
      {
        packages = {
          inherit packageA packageB packageC packageD;
          deps = collect-direct-deps { inherit packageA packageB packageC packageD; };
          config = make-config { inherit packageA packageB packageC packageD; };
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python3
          ];
        };
      });
}
