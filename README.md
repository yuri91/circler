# CircleCI + Nix Dynamic Configuration Demo

This repository demonstrates how to integrate Nix with CircleCI using dynamic configuration to automatically generate build workflows based on Nix derivation dependencies.

## Overview

The integration works by:

1. **Setup Phase**: A setup job evaluates Nix expressions and analyzes package dependencies
2. **Dependency Analysis**: Python scripts examine the dependency graph of Nix derivations
3. **Dynamic Generation**: CircleCI workflows are generated that respect dependency ordering
4. **Parallel Execution**: Independent packages build in parallel while dependent packages wait

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Nix Flake     │    │   Dependency     │    │   CircleCI      │
│   Evaluation    │───▶│   Analysis       │───▶│   Dynamic       │
│                 │    │   (Python)       │    │   Config        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   Build DAG      │
                       │                  │
                       │   A ────┐        │
                       │   │     │        │
                       │   ▼     ▼        │
                       │   B ────D        │
                       │         ▲        │
                       │   C ────┘        │
                       └──────────────────┘
```

## Package Dependencies

This demo includes four example packages with the following dependency structure:

- **Package A**: Independent (no dependencies)
- **Package B**: Depends on Package A
- **Package C**: Independent (no dependencies)  
- **Package D**: Depends on both Package B and Package C

## Files Structure

```
.
├── flake.nix                          # Nix flake with package definitions
├── flake.lock                         # Nix flake lock file
├── .circleci/
│   └── config.yml                     # CircleCI setup workflow
├── scripts/
│   └── analyze-derivations.py         # Advanced dependency analyzer
├── src/
│   ├── package-a/main.c              # Example package A source
│   ├── package-b/main.c              # Example package B source
│   ├── package-c/main.c              # Example package C source
│   └── package-d/main.c              # Example package D source
└── README.md                          # This file
```

## Usage

### Local Development

1. **Enter development shell**:
   ```bash
   nix develop
   ```

2. **Test the dependency analyzer**:
   ```bash
   python3 scripts/analyze-derivations.py
   ```

3. **Build individual packages**:
   ```bash
   nix build .#packageA
   nix build .#packageB
   nix build .#packageC
   nix build .#packageD
   ```

4. **Build all packages**:
   ```bash
   nix build .#default
   ```

### CircleCI Integration

The CircleCI integration automatically:

1. **Setup Job**: 
   - Installs Nix and dependencies
   - Evaluates the flake
   - Runs dependency analysis
   - Generates dynamic configuration

2. **Dynamic Workflows**:
   - Creates jobs for each package
   - Sets up proper dependency relationships
   - Enables parallel builds where possible
   - Includes caching for efficiency

3. **Build Execution**:
   - Independent packages (A, C) build in parallel
   - Package B waits for A to complete
   - Package D waits for both B and C
   - Integration tests run after all packages

### Key Features

- **Automatic Dependency Detection**: Analyzes Nix derivations to understand dependencies
- **Topological Sorting**: Ensures builds happen in correct order
- **Parallel Optimization**: Maximizes parallelism within dependency constraints
- **Nix Store Caching**: Caches build artifacts between jobs
- **Dynamic Configuration**: Generates workflows programmatically

## Extending the Demo

### Adding New Packages

1. Add package definition to `flake.nix`:
   ```nix
   packageE = pkgs.stdenv.mkDerivation {
     name = "package-e";
     src = ./src/package-e;
     buildInputs = [ packageD ];  # Dependencies
     # ... build instructions
   };
   ```

2. Create source directory:
   ```bash
   mkdir src/package-e
   ```

3. Update the dependency graph in `scripts/analyze-derivations.py` if using hardcoded dependencies

### Customizing Build Jobs

Modify the `generate_circleci_job()` function in `scripts/analyze-derivations.py` to:
- Change Docker images
- Add custom build steps
- Configure resource classes
- Add test commands

### Advanced Dependency Analysis

For real-world usage, enhance the analyzer to:
- Use `nix-store --query` for actual dependency information
- Handle complex dependency patterns
- Support cross-compilation targets
- Integrate with existing CI systems

## Benefits

1. **Consistency**: Build order matches Nix's internal dependency resolution
2. **Efficiency**: Parallel builds reduce total CI time
3. **Maintainability**: Dependency changes automatically update CI workflows
4. **Reproducibility**: Nix ensures consistent builds across environments
5. **Scalability**: Works with large monorepos and complex dependency graphs

## Limitations

- Currently uses hardcoded dependency graph (for demo purposes)
- Requires CircleCI dynamic configuration feature
- Nix evaluation happens on every run (could be optimized with caching)

## Future Enhancements

- [ ] Real-time derivation dependency analysis
- [ ] Integration with Nix binary caches
- [ ] Support for cross-compilation matrices  
- [ ] Conditional builds based on changed files
- [ ] Integration with other CI providers (GitHub Actions, GitLab CI)
- [ ] Performance optimizations for large flakes