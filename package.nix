{ lib
, python3Packages
, nix-eval-jobs
, attic-client
, formats
}:
let
  pname = "circler";
  version = "0.1.0";
  deps = with python3Packages; [
    requests
    types-requests
    pyyaml
    types-pyyaml
    sh
    numpy
  ];
  formatDeps = deps:
    let
      formatOne = dep: ''${dep.pname}==${dep.version}'';
    in
    map formatOne deps;
  pyproject = (formats.toml { }).generate "pyproject.toml" {
    build-system = {
      requires = [
        "setuptools>=68"
        "wheel"
      ];
      build-backend = "setuptools.build_meta";
    };
    project = {
      name = pname;
      inherit version;
      dependencies = formatDeps deps;
      scripts."${pname}" = "${pname}.main:main";
      scripts."ci-cheerp" = "${pname}.cheerp:run";
      requires-python = ">=${python3Packages.python.pythonVersion}";
    };
    tool = {
      setuptools.packages.find.where = [ "src" ];
      mypy = {
        mypy_path = "src";
        python_version = python3Packages.python.pythonVersion;
        strict = true;
        warn_return_any = true;
        warn_unused_configs = true;
        disallow_untyped_defs = true;
        disallow_any_unimported = false;
        no_implicit_optional = true;
        warn_redundant_casts = true;
        warn_unused_ignores = true;
        warn_no_return = true;
        warn_unreachable = true;
        strict_equality = true;
      };
      ruff = {
        lint = {
          select = [
            "E" # pycodestyle errors
            "W" # pycodestyle warnings
            "F" # pyflakes
            "I" # isort
            "B" # flake8-bugbear
            "C4" # flake8-comprehensions
            "UP" # pyupgrade
            "ARG" # flake8-unused-arguments
            "SIM" # flake8-simplify
          ];
          ignore = [
            "E501" # line too long (handled by black)
            "B008" # do not perform function calls in argument defaults
          ];
        };
      };
    };
  };
in
python3Packages.buildPythonPackage {
  inherit pname version;
  format = "pyproject";

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.union ./src ./pyproject.toml;
  };

  nativeBuildInputs = with python3Packages; [
    setuptools
    wheel
  ];

  buildInputs = [
    nix-eval-jobs
    attic-client
  ];

  propagatedBuildInputs = deps;

  nativeCheckInputs = with python3Packages; [
    mypy
    ruff
  ];

  pythonImportsCheck = [ pname ];

  checkPhase = ''
    runHook preCheck

    # Run type checking
    mypy src/
    # Run linting
    ruff check src/

    runHook postCheck
  '';
  passthru.pyprojectfile = pyproject;
}
