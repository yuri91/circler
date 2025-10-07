{
  description = "CircleCI + Nix Dynamic Configuration Demo";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        circler = pkgs.callPackage ./package.nix { };
      in
      {
        packages.default = circler;
        packages.circler = circler;
        packages.python = (pkgs.python3.withPackages (ps: [
          circler
        ])).overrideAttrs
          (old: {
            nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ pkgs.makeWrapper ];
            postBuild = (old.postBuild or "") + ''
              for bin in $out/bin/{python,python3}; do
                wrapProgram $bin --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.attic-client pkgs.nix-eval-jobs]}
              done
            '';
          });
        devShells.default = pkgs.callPackage ./shell.nix { };
      });
}
