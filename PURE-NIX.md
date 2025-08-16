# Pure Nix CircleCI Configuration Generation

This demo showcases a **pure Nix approach** to generating CircleCI dynamic configuration directly from Nix derivation dependency graphs, without requiring external tools or languages.

## The Pure Nix Approach

### Traditional Approach ❌
```bash
# External dependencies and complex setup
nix profile install nixpkgs#python3 nixpkgs#python3Packages.pyyaml
python3 scripts/analyze-derivations.py
```

### Pure Nix Approach ✅
```bash
# Everything expressed in Nix
nix build .#continuation-config
nix run .#generate-continuation-config
```

## How It Works

The `continuation-config` derivation is a **pure Nix expression** that:

1. **Defines Dependencies**: Package relationships are expressed directly in Nix
2. **Generates DAG**: Uses Nix's functional programming capabilities to build dependency graphs
3. **Creates Config**: Produces CircleCI YAML (as JSON) entirely within Nix evaluation
4. **Zero Dependencies**: No external tools, interpreters, or runtimes required

### Dependency Graph Definition

```nix
# Pure Nix dependency graph - single source of truth
packageGraph = {
  packageA = [];                    # Independent
  packageB = ["packageA"];          # Depends on A  
  packageC = [];                    # Independent
  packageD = ["packageB" "packageC"]; # Depends on B and C
};
```

### CircleCI Job Generation

```nix
# Generate CircleCI jobs functionally
generateJob = pkgName: deps: {
  docker = [{ image = "cimg/base:stable"; }];
  resource_class = "medium";
  steps = [
    "checkout"
    { run = { 
        name = "Build ${pkgName}";
        command = ''
          nix build .#${pkgName} -L
        '';
      };
    }
  ];
};
```

### Workflow Generation with Dependencies

```nix
# Build workflow jobs respecting dependency order
generateWorkflowJobs = graph: 
  map (pkgName: 
    let deps = graph.${pkgName}; in
    if deps == [] then
      { job = "build-${pkgs.lib.toLower pkgName}"; }
    else
      { 
        job = "build-${pkgs.lib.toLower pkgName}";
        requires = map (dep: "build-${pkgs.lib.toLower dep}") deps;
      }
  ) (builtins.attrNames graph);
```

## Benefits of Pure Nix

### ✅ **Hermetic**: 
- No external dependencies or runtime requirements
- Everything needed is expressed in the flake
- Reproducible across all environments

### ✅ **Declarative**:
- Dependency relationships defined once in Nix
- Configuration generation is pure functional programming
- No imperative scripts or complex logic

### ✅ **Efficient**:
- Leverages Nix's lazy evaluation
- Cached builds and evaluations
- No setup or installation steps

### ✅ **Type-Safe**:
- Nix's type system catches errors at evaluation time
- Structured data handling built-in
- No runtime failures from missing dependencies

### ✅ **Introspective**:
- Can analyze the flake's own dependency structure
- Self-documenting through Nix expressions
- Easy to extend and modify

## Usage Examples

### Generate Configuration
```bash
# Build the configuration file directly
nix build .#continuation-config
cat result

# Or run the wrapper script
nix run .#generate-continuation-config
```

### View Dependency Graph
```bash
# The dependency relationships are visible in the Nix code
nix eval .#continuation-config --json | jq '.workflows'
```

### Extend with New Packages
```nix
# Simply add to the packageGraph
packageGraph = {
  packageA = [];
  packageB = ["packageA"];
  packageC = [];
  packageD = ["packageB" "packageC"];
  packageE = ["packageD"];  # New package depending on D
};
```

## Advanced Features

### Real Derivation Introspection (Future)

The pure Nix approach could be extended to analyze actual derivation dependencies:

```nix
# Hypothetical: analyze real derivations
actualDependencies = pkgs.lib.mapAttrs (name: drv:
  builtins.map baseNameOf (builtins.attrNames drv.inputDrvs)
) { inherit packageA packageB packageC packageD; };
```

### Cross-System Support

```nix
# Generate configs for multiple systems
forAllSystems = system: 
  generateCircleCIConfig (packagesFor system);
```

### Custom Build Strategies

```nix
# Different job types based on package characteristics
generateJob = pkgName: deps: 
  if hasTests pkgName then testJob pkgName deps
  else if isDocumentation pkgName then docsJob pkgName deps  
  else buildJob pkgName deps;
```

## Comparison: Pure Nix vs External Tools

| Aspect | External Tools | Pure Nix |
|--------|---------------|----------|
| Dependencies | Python, PyYAML, Scripts | None (flake only) |
| Evaluation | Runtime execution | Build-time evaluation |
| Caching | Limited | Full Nix caching |
| Reproducibility | Environment dependent | Hermetic |
| Type Safety | Runtime errors | Evaluation-time checks |
| Extensibility | Modify scripts | Extend expressions |

## Why This Matters

This demonstrates that **Nix can be its own build orchestration language**. Instead of generating configs for external CI systems, we can:

1. **Express Everything in Nix**: Dependencies, build logic, and CI orchestration
2. **Leverage Nix's Strengths**: Lazy evaluation, caching, and functional programming
3. **Eliminate Dependencies**: No external interpreters, tools, or runtimes
4. **Maintain Single Source of Truth**: Dependency graph lives in Nix where it belongs

This is a step toward **Nix-native CI/CD** where the same language that describes your build also orchestrates it.

## Files

- **`flake.nix`**: Contains the pure Nix configuration generator
- **`.#continuation-config`**: The generated CircleCI configuration as a derivation
- **`.#generate-continuation-config`**: Wrapper script to copy config to expected location

The future is **pure, functional, reproducible CI/CD entirely within Nix**.