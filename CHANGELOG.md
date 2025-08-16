# Changelog

## Latest Changes

### Fixed CircleCI Base Image Issues

**Problem**: The original configuration used `nixos/nix:latest` Docker images, which had compatibility issues with CircleCI's continuation installer and dynamic configuration features.

**Solution**: Switched to Ubuntu-based approach for better CircleCI compatibility:

#### Changes Made:

1. **Setup Job** (`.circleci/config.yml`):
   - Changed from `nixos/nix:latest` to `cimg/base:stable` 
   - Added Nix installation using Determinate Systems installer
   - Added proper environment setup with `$BASH_ENV`
   - Fixed CircleCI CLI installation with `sudo bash`

2. **Dynamic Job Generation** (`scripts/analyze-derivations.py`):
   - Updated all generated jobs to use `cimg/base:stable`
   - Added Nix installation step to each job
   - Added proper environment sourcing before Nix commands

3. **Offline Test** (`scripts/test-analyzer-offline.py`):
   - Updated to match the new Ubuntu + Nix approach
   - Ensures test output matches actual generated configuration

4. **Documentation Updates**:
   - Updated README.md and DEMO.md to reflect Ubuntu base images
   - Updated sample configurations to show new approach

#### Benefits:

✅ **Better Compatibility**: Ubuntu base images work reliably with CircleCI features  
✅ **Consistent Environment**: Same Nix installation method across all jobs  
✅ **Reliable Installation**: Determinate Systems Nix installer is more robust  
✅ **Proper Isolation**: Each job gets fresh Nix installation  
✅ **CircleCI CLI Support**: Ubuntu environment supports continuation features  

#### Technical Details:

- **Base Image**: `cimg/base:stable` (Ubuntu-based CircleCI image)
- **Nix Installer**: `https://install.determinate.systems/nix` 
- **Nix Config**: Flakes and nix-command enabled automatically
- **Environment**: Proper `$BASH_ENV` setup for persistent environment

The integration now uses a more reliable foundation while maintaining all the original functionality of automatic dependency analysis and dynamic workflow generation.

## Package Simplification

### Converted from `stdenv.mkDerivation` to `runCommand`

**Changes**:
- Simplified package definitions using `runCommand` instead of `mkDerivation`
- Removed need for source directories (`src/package-*`)
- Cleaner dependency declarations
- More concise build scripts

**Benefits**:
- Easier to understand and modify
- Less boilerplate code
- Direct build script execution
- Better demonstration of Nix concepts