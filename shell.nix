{ mkShell
, callPackage
, writeShellApplication
}:
let
  package = callPackage ./package.nix {};
  generate-pyproject = writeShellApplication {
    name = "generate-pyproject";
    text = ''
      cat ${package.pyproject} > pyproject.toml
    '';
  };
in
mkShell {
  inputsFrom = [
    package
  ];
  packages = [
    generate-pyproject
  ];
  shellHook = ''
    generate-pyproject
  '';
}
