# CircleCI + Nix Dynamic Configuration Demo

## What This Demo Shows

This repository demonstrates a complete integration between Nix and CircleCI that automatically generates build workflows based on package dependencies. Here's what happens:

1. **Dependency Analysis**: The system analyzes Nix derivations to understand package relationships
2. **DAG Generation**: Creates a directed acyclic graph representing build dependencies  
3. **Dynamic Workflows**: Generates CircleCI configuration that respects dependency ordering
4. **Parallel Optimization**: Maximizes build parallelism within dependency constraints

## Demo Package Structure

```
Package A (independent) ────┐
                            ▼
Package B (depends on A) ───┼─── Package D (depends on B & C)
                            ▲
Package C (independent) ────┘
```

## Generated Build Order

**Level 1 (Parallel)**: Package A, Package C  
**Level 2**: Package B (waits for A)  
**Level 3**: Package D (waits for B and C)  
**Level 4**: Integration Tests (waits for D)

## Key Files

- **`flake.nix`**: Defines packages with dependencies
- **`.circleci/config.yml`**: Setup workflow that triggers dynamic generation
- **`scripts/analyze-derivations.py`**: Core analyzer that builds dependency graph
- **`scripts/test-analyzer-offline.py`**: Offline test demonstrating the analysis

## Testing the Demo

### Local Testing
```bash
# Test the analyzer (uses Nix for all dependencies)
nix run .#analyze-derivations

# Or test the offline version in development shell
nix develop
python3 scripts/test-analyzer-offline.py
```

### With Nix (Requires Nix installation)
```bash
# Test flake evaluation
nix flake show

# Build packages individually  
nix build .#packageA
nix build .#packageB
nix build .#packageC
nix build .#packageD

# Build all packages
nix build .#default
```

## CircleCI Integration

To use with CircleCI:

1. Push this repo to GitHub/GitLab
2. Connect to CircleCI
3. Enable "Enable dynamic config using setup workflows" in project settings
4. Push changes to trigger the workflow

The setup job will:
- Evaluate the Nix flake
- Analyze package dependencies
- Generate dynamic CircleCI configuration
- Continue the pipeline with optimized build order

## Sample Generated Configuration

The analyzer generates CircleCI configuration like this:

```yaml
version: 2.1
jobs:
  build-packagea:
    docker: [image: cimg/base:stable]
    steps: 
      - checkout
      - run: curl -sSf https://install.determinate.systems/nix | sh
      - run: nix build .#packageA
  
  build-packagec: 
    docker: [image: cimg/base:stable]
    steps: 
      - checkout  
      - run: curl -sSf https://install.determinate.systems/nix | sh
      - run: nix build .#packageC
    
  build-packageb:
    docker: [image: cimg/base:stable] 
    steps: 
      - checkout
      - run: curl -sSf https://install.determinate.systems/nix | sh
      - run: nix build .#packageB
    
  build-packaged:
    docker: [image: cimg/base:stable]
    steps: 
      - checkout
      - run: curl -sSf https://install.determinate.systems/nix | sh
      - run: nix build .#packageD

workflows:
  build-dependency-graph:
    jobs:
      - build-packagea        # No dependencies
      - build-packagec        # No dependencies  
      - build-packageb:       # Waits for A
          requires: [build-packagea]
      - build-packaged:       # Waits for B and C
          requires: [build-packageb, build-packagec]
```

## Benefits

✅ **Automatic**: No manual workflow maintenance  
✅ **Optimized**: Maximum parallelism within constraints  
✅ **Consistent**: Build order matches Nix's dependency resolution  
✅ **Scalable**: Works with complex dependency graphs  
✅ **Maintainable**: Changes to dependencies automatically update CI

## Extending the Demo

- Add more complex packages with intricate dependencies
- Implement real derivation analysis using `nix-store --query`
- Add conditional builds based on changed files
- Integrate with Nix binary caches for faster builds
- Support multiple systems/architectures

This demo provides a foundation for sophisticated CI/CD pipelines that leverage Nix's declarative package management with CircleCI's dynamic configuration capabilities.