# Cross-Device Build & Release Guide

Complete reference for building and releasing exo across all platforms.

## Quick Start

### Release a new version:

```bash
# 1. Update version numbers
# pyproject.toml, Cargo.toml, android/build.gradle

# 2. Create git tag
git tag v1.0.0
git push origin v1.0.0

# 3. Trigger release workflow
# Option A: Automatic (tag push) → workflow/release-all.yml
# Option B: Manual → GitHub Actions > Release All > Run workflow

# 4. Monitor builds at:
https://github.com/exo-explore/exo/actions/workflows/release-all.yml
```

---

## Platform-Specific Builds

### Linux

**Supported Distributions** (automatic multi-distro):
- Debian/Ubuntu (amd64, arm64) - APT (.deb)
- Fedora/RHEL (x86_64) - DNF (.rpm)
- Alpine (x86_64) - APK (.apk)
- Arch Linux (x86_64) - PKGBUILD (.pkg.tar.zst)
- AppImage (universal, amd64)
- Flatpak (universal, amd64)
- Snap (universal, amd64)

**Manual build (local):**
```bash
# Build for current distro
cd packaging/linux
./build-deb.sh     # Ubuntu/Debian
./build-rpm.sh     # Fedora/RHEL
./build-apk.sh     # Alpine
./build-arch.sh    # Arch Linux
./build-appimage.sh # AppImage
./build-flatpak.sh  # Flatpak
./build-snap.sh     # Snap
```

**GitHub Action:**
```bash
# Trigger from GitHub Actions UI or:
gh workflow run build-linux.yml
```

---

### Windows

**Supported Architectures**:
- x86_64 (Intel/AMD)
- ARM64 (Windows on ARM)

**Supported Installers**:
- NSIS installer (.exe) - traditional Windows installer
- Portable ZIP - no installation required
- (WiX MSI support available but optional)

**Manual build (Windows):**
```powershell
# Setup
uv sync --locked

# Build
uv run pyinstaller packaging/pyinstaller/exo.spec

# Create installer
makensis /V4 /DVERSION=1.0.0 packaging\windows\nsis\exo.nsi

# Sign (requires certificate)
.\packaging\windows\sign.ps1
```

**GitHub Action:**
```bash
gh workflow run build-windows.yml
```

---

### macOS

**Supported Architectures**:
- aarch64 (Apple Silicon: M1, M2, M3, M4)
- x86_64 (Intel)

**Build Process** (existing workflow, enhanced):
- PyInstaller bundle
- Swift app wrapper
- Code signing + notarization
- DMG creation
- Sparkle auto-update

**Manual build (macOS):**
```bash
# Build dashboard
nix build .#dashboard

# Build app
cd app/EXO
xcodebuild clean build \
  -scheme EXO \
  -configuration Release \
  MARKETING_VERSION=1.0.0 \
  CODE_SIGNING_IDENTITY="Developer ID Application"
```

**GitHub Action:**
```bash
# Automatic (via tag push) - uses existing build-app.yml
# Or manual:
gh workflow run build-app.yml
```

---

### Android

**Supported Architectures**:
- arm64-v8a (aarch64)
- armeabi-v7a (armv7l)
- x86_64
- x86

**Build Variants**:
- APK (direct install)
- AAB (Google Play)

**Manual build (Android):**
```bash
cd android
./gradlew assembleRelease -PversionName=1.0.0
./gradlew bundleRelease -PversionName=1.0.0
```

**GitHub Action:**
```bash
gh workflow run build-android.yml -f version=v1.0.0
```

**Distribution**:
- APK: Direct download or sideload
- AAB: Google Play internal testing → beta → production

---

### iOS

**Build Process**:
- Xcode build for device + simulator
- Code signing + provisioning profile
- .ipa creation (for direct install)
- App Store submission via App Store Connect

**Manual build (macOS only):**
```bash
cd app/EXO-iOS
xcodebuild clean build \
  -scheme EXO-iOS \
  -configuration Release \
  -destination 'generic/platform=iOS'
```

**GitHub Action**:
```bash
# Planned for future release
# Currently: Manual build + manual upload to App Store
```

---

## Release Workflow

### Complete Multi-Platform Release

**Method 1: Automatic (tag push)**
```bash
# Create tag and push
git tag v1.0.0
git push origin v1.0.0

# Workflow automatically triggers:
# 1. Runs tests
# 2. Builds all platforms (in parallel)
# 3. Signs packages
# 4. Creates GitHub release
# 5. Publishes to package managers
# Total time: ~45 minutes
```

**Method 2: Manual Workflow Dispatch**
```bash
# Via GitHub Actions UI:
# 1. Go to Actions
# 2. Select "Multi-Platform Release"
# 3. Click "Run workflow"
# 4. Enter version (v1.0.0)
# 5. Click "Run"
```

**Method 3: CLI**
```bash
gh workflow run release-all.yml \
  -f version=v1.0.0 \
  -f skip_tests=false
```

---

## Package Manager Integration

### APT (Debian/Ubuntu)

**Setup** (one-time):
```bash
# 1. Create PPA on launchpad.net/~exo/+archive/ubuntu/ppa
# 2. Generate GPG key
# 3. Add to GitHub secrets: GPG_PRIVATE_KEY, GPG_PASSPHRASE

# 4. Add Launchpad credentials
echo "LAUNCHPAD_CREDENTIALS=<base64>" >> ~/.env
```

**Publish**:
```bash
# Automatic via release workflow
# Manual:
dput ppa:exo/ppa exo_1.0.0_source.changes
```

**Install** (users):
```bash
sudo add-apt-repository ppa:exo/ppa
sudo apt update
sudo apt install exo
```

---

### DNF/YUM (Fedora/RHEL)

**Setup** (one-time):
```bash
# 1. Create Fedora COPR: copr.fedorainfracloud.org
#    Project: exo-explore/exo
# 2. Add credentials to GitHub: COPR_CREDENTIALS
```

**Publish**:
```bash
# Automatic via release workflow
# Manual:
copr-cli build exo-explore/exo exo-1.0.0-1.fc41.src.rpm
```

**Install** (users):
```bash
sudo dnf copr enable exo-explore/exo
sudo dnf install exo
```

---

### Snap

**Setup** (one-time):
```bash
# 1. Create account on snapcraft.io
# 2. Login: snapcraft login
# 3. Store credentials to GitHub: SNAPCRAFT_STORE_CREDENTIALS
```

**Publish**:
```bash
# Automatic via release workflow
# Manual:
snapcraft upload exo_1.0.0_amd64.snap --release=edge
```

**Install** (users):
```bash
snap install exo
```

---

### Flatpak (via Flathub)

**Setup** (one-time):
```bash
# Submit PR to github.com/flathub/io.exo.EXO
# Once accepted, automatic updates available
```

**Publish**:
```bash
# Create PR with updated manifest
# Flathub auto-builds when merged
```

**Install** (users):
```bash
flatpak install flathub io.exo.EXO
```

---

### Google Play (Android)

**Setup** (one-time):
```bash
# 1. Create Play Console account
# 2. Create app "io.exo.app"
# 3. Generate service account JSON
# 4. Add to GitHub: GOOGLE_PLAY_SERVICE_ACCOUNT
# 5. Create signed keystore
# 6. Add to GitHub: ANDROID_KEYSTORE_BASE64, etc.
```

**Publish**:
```bash
# Automatic via release workflow (internal testing track)
# Then promote: internal → beta → production via Play Console UI
```

**Install** (users):
```bash
# Google Play app search: "exo"
```

---

### App Store (iOS)

**Setup** (one-time):
```bash
# 1. Create App Store account
# 2. Create app "EXO"
# 3. Generate API key in App Store Connect
# 4. Add to GitHub: APP_STORE_CONNECT_API_KEY
```

**Publish**:
```bash
# Manual upload via Xcode or App Store Connect
# Automatic workflow (future)
```

**Install** (users):
```bash
# App Store search: "exo"
```

---

## Configuration Reference

### GitHub Secrets Required

```yaml
# Code signing (all platforms)
MACOS_CERTIFICATE: <p12 base64>
MACOS_CERTIFICATE_PASSWORD: <password>
WINDOWS_CODE_SIGN_CERT: <pfx base64>
WINDOWS_CODE_SIGN_PASS: <password>

# Linux
GPG_PRIVATE_KEY: <asc file>
GPG_PASSPHRASE: <passphrase>
LAUNCHPAD_CREDENTIALS: <ssh key base64>
COPR_CREDENTIALS: <config base64>
AUR_GIT_SSH_KEY: <ssh key base64>

# Mobile
ANDROID_KEYSTORE_BASE64: <keystore base64>
ANDROID_KEYSTORE_PASSWORD: <password>
ANDROID_KEY_ALIAS: <alias>
ANDROID_KEY_PASSWORD: <password>
GOOGLE_PLAY_SERVICE_ACCOUNT: <json>

APP_STORE_CONNECT_API_KEY: <api key>

# Package managers
SNAPCRAFT_STORE_CREDENTIALS: <credentials>

# S3 (optional, for release artifacts)
AWS_S3_BUCKET: exo-releases
AWS_ACCESS_KEY_ID: <key>
AWS_SECRET_ACCESS_KEY: <secret>

# CI
CACHIX_AUTH_TOKEN: <token>

# Notifications (optional)
SLACK_WEBHOOK: <webhook url>
```

---

## Troubleshooting

### Build Failures

**Check logs**:
```bash
# GitHub Actions
# 1. Go to https://github.com/exo-explore/exo/actions
# 2. Click workflow run
# 3. Expand failed step
# 4. Check error message
```

**Common issues**:

| Issue | Solution |
|:---|:---|
| "GPG key not found" | Check GPG_PRIVATE_KEY secret format (must be base64) |
| "CUDA not found" | Ubuntu container missing CUDA - use nvidia/cuda base image |
| "Code signing failed" | Verify certificate is valid and not expired |
| "Package too large" | GitHub artifacts have 5GB limit per upload |
| "Signature verification failed" | Check key permissions (chmod 600) |

---

## Performance Tips

1. **Parallel builds** (GitHub Actions automatically):
   - Linux builds run in parallel (7 jobs)
   - Windows builds run in parallel (2 jobs)
   - Mobile builds run in parallel
   - Saves ~20 minutes per release

2. **Caching**:
   - Rust dependencies cached via Cachix
   - Python dependencies cached via uv
   - Nix derivations cached via Cachix

3. **Incremental builds**:
   - Only changed packages rebuild
   - Dashboard only rebuilds if dashboard/ changed
   - Rust only rebuilds if rust/ changed

---

## Security Checklist

Before each release:

- [ ] All commits signed with GPG
- [ ] Tags signed: `git tag -s v1.0.0`
- [ ] Code review completed
- [ ] Security scan passed (if enabled)
- [ ] All tests pass
- [ ] GPU support verified on each platform
- [ ] Installer tested on each platform
- [ ] Release notes reviewed
- [ ] Changelog updated

---

## Monitoring Releases

### Real-time monitoring

```bash
# Watch workflow
gh run watch

# Stream logs
gh run view --log --tail -1

# List recent runs
gh run list --workflow build-linux.yml --limit 5
```

### Post-release validation

```bash
# Download and test package
wget https://github.com/exo-explore/exo/releases/download/v1.0.0/exo-1.0.0-amd64.deb
sudo dpkg -i exo-1.0.0-amd64.deb
exo --version

# Verify signature
gpg --verify exo-1.0.0.asc exo-1.0.0-amd64.deb

# Check package in managers
apt-cache policy exo
snap info exo
```

---

## Support Matrix

| Platform | Version | Status | GPU | Notes |
|:---|:---|:---|:---|:---|
| **Ubuntu** | 22.04 LTS | ✅ | NVIDIA CUDA | Recommended for development |
| **Ubuntu** | 24.04 LTS | ✅ | NVIDIA CUDA | Latest stable |
| **Debian** | 12 | ✅ | Any | Stable release |
| **Fedora** | 41 | ✅ | AMD ROCm | Cutting edge |
| **RHEL** | 9 | ✅ | Any | Enterprise support |
| **Alpine** | 3.20 | ✅ | Limited | Minimal footprint |
| **Arch** | Latest | ✅ | Any | Bleeding edge |
| **Windows** | 11 | ✅ | NVIDIA/AMD | Latest version |
| **Windows** | 10 | ⚠️ | NVIDIA/AMD | Legacy support |
| **macOS** | 13+ | ✅ | Apple Silicon | M1/M2/M3/M4 |
| **Android** | 12+ | ✅ | Adreno/Mali | Google Play |
| **iOS** | 15+ | ✅ | Apple GPU | App Store |

---

## Next Steps

1. **First release**: Test with v0.1.0-alpha.1
2. **Validate package managers**: Verify apt, dnf, snap, flatpak work
3. **Collect user feedback**: Monitor GitHub issues and discussions
4. **Production release**: v1.0.0 with full QA

---

## Resources

- **Build system**: .github/workflows/*.yml
- **Packaging scripts**: packaging/
- **Build docs**: CROSS_DEVICE_BUILD_AUTOMATION.md
- **Release timeline**: See IMPLEMENTATION_STATUS.md
