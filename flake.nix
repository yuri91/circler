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
        circler = pkgs.callPackage ./package.nix { };
      in
      {
        packages.default = circler;
        packages.circler = circler;
        packages.python = pkgs.python3.withPackages (ps: [
          circler
        ]);
        devShells.default = pkgs.callPackage ./shell.nix { };
      });
}
