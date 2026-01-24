# GitHub Actions Workflows

## Overview

This directory contains GitHub Actions workflows for CI/CD:

### `pipeline.yml`
- **Purpose**: Continuous Integration pipeline
- **Triggers**: Push to main/staging, Pull Requests
- **Jobs**:
  - Typecheck (basedpyright)
  - Nix builds (multi-platform)
  - Build verification
- **Secrets Used**: None (uses Cachix but can work without)

### `release-all-optimized.yml`
- **Purpose**: Complete multi-platform release workflow
- **Triggers**: Git tags (v*), Manual workflow_dispatch
- **Platforms Supported**:
  - Linux: deb, rpm, apk, pkg.tar.zst, appimage, flatpak, snap
  - Windows: NSIS installer, portable ZIP
  - macOS: DMG (unsigned)
  - Android: APK/AAB
- **Features**:
  - Smart caching for dependencies
  - Parallel builds across platforms
  - Artifact verification
  - GitHub Release creation
  - Artifact cleanup (keeps last 3 releases)
- **Secrets Required**: None (only uses GitHub-provided GITHUB_TOKEN)

## Running Releases

### Automated (Tag Push)
```bash
git tag v1.0.0
git push origin v1.0.0
```

### Manual (Workflow Dispatch)
1. Go to Actions → release-all-optimized
2. Click "Run workflow"
3. Enter version (e.g., v1.0.0)
4. Select which platforms to build
5. Run

## Environment

### No External Secrets Required

The workflows are designed to work without any external API credentials:
- **Removed**: CACHIX_AUTH_TOKEN, AWS credentials, GPG keys, code signing certs, app store credentials
- **Kept**: GITHUB_TOKEN (auto-provided by GitHub Actions)

### Building Without Credentials

All builds use public toolchains:
- Nix (public channels)
- Standard compilers (rustc, gcc, clang)
- Public SDKs (Java, Android, Xcode)

## Simplified Build Matrix

### Linux
- Single build job with matrix for all distros
- Falls back to custom scripts if Nix fails
- No GPG signing (optional)

### Windows
- Native build-tools via Chocolatey
- NSIS installer + portable ZIP
- No code signing (optional)

### macOS
- Xcode compilation (no notarization)
- PyInstaller for Python runtime
- Unsigned DMG (sign locally if needed)

### Android
- Gradle builds (APK/AAB)
- Native libraries via Rust
- No keystore signing (optional)

## Cache Strategy

All builds use GitHub Actions cache for:
- **Python deps**: `uv.lock`, `pyproject.toml`
- **Rust**: `Cargo.lock`, `Cargo.toml`
- **Nix**: `flake.lock`, `flake.nix`
- **Dashboard**: Built once, reused across platforms

Cache is automatically invalidated on dependency changes.

## Artifact Retention

- Build artifacts: 1 day
- GitHub Release: Permanent (cleanup keeps last 3)
- Shared build outputs: 1 day

## Troubleshooting

### Build Failures
1. Check runner logs in GitHub Actions
2. Look for missing build scripts in `packaging/`
3. Verify Nix flake is valid: `nix flake check`

### No Artifacts Generated
- Ensure at least one platform didn't fail
- Verify minimum artifact count check passes
- Download artifacts manually from Actions page

### Release Not Created
- Check if `verify-builds` job passed
- Ensure version format is correct: `v1.0.0` or `v1.0.0-alpha.1`
- Check GITHUB_TOKEN has release permissions
