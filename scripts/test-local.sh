#!/bin/bash
set -euo pipefail

echo "🧪 Testing Nix + CircleCI Integration Locally"
echo "=============================================="

# Check if nix is available
if ! command -v nix &> /dev/null; then
    echo "❌ Error: Nix is not installed or not in PATH"
    exit 1
fi

echo "✅ Nix found: $(nix --version)"

# Test flake evaluation
echo ""
echo "📋 Testing flake evaluation..."
if nix flake show --json . > /dev/null 2>&1; then
    echo "✅ Flake evaluation successful"
    nix flake show .
else
    echo "❌ Flake evaluation failed"
    exit 1
fi

# Test dependency analyzer
echo ""
echo "🔍 Testing dependency analyzer..."
if python3 scripts/analyze-derivations.py > /tmp/test-output.yml; then
    echo "✅ Dependency analysis successful"
    echo "Generated configuration:"
    head -20 /tmp/test-output.yml
    echo "... (truncated)"
else
    echo "❌ Dependency analysis failed"
    exit 1
fi

# Test building packages in dependency order
echo ""
echo "🔨 Testing package builds in dependency order..."

packages=("packageA" "packageC" "packageB" "packageD")
for pkg in "${packages[@]}"; do
    echo "Building $pkg..."
    if nix build ".#$pkg" --no-link; then
        echo "✅ $pkg built successfully"
    else
        echo "❌ $pkg build failed"
        exit 1
    fi
done

# Test final integration
echo ""
echo "🎯 Testing final integration..."
if nix build ".#default" --no-link; then
    echo "✅ Integration build successful"
else
    echo "❌ Integration build failed"
    exit 1
fi

echo ""
echo "🎉 All tests passed! The integration is working correctly."
echo ""
echo "Next steps:"
echo "1. Push to a repository connected to CircleCI"
echo "2. Enable dynamic configuration in CircleCI project settings"
echo "3. Watch the automated workflow generation in action"