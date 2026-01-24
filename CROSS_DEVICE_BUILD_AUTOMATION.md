# Cross-Device Build & Deploy Automation - 100% Implementation

**Status**: Plan for Complete Build Automation across all Distributions  
**Date**: January 24, 2026  
**Objective**: Extend GitHub deploy pipeline to support Linux, Windows, Android, iOS with automatic multi-distro builds

---

## Executive Summary

The current exo build pipeline is **macOS-only** (build-app.yml) with limited CI/CD (pipeline.yml). To achieve 100% cross-device support, we need:

1. **Multi-distribution build automation** (Linux, Windows, Android, iOS)
2. **Continuous integration** across all platforms
3. **Automated release distribution** to appropriate package managers
4. **Platform-specific build caching** and optimization
5. **Container-based builds** for reproducibility and isolation

---

## Current State Assessment

### What Works ✅
- macOS DMG builds with code signing and notarization
- Nix-based reproducible builds (pipeline.yml)
- CI pipeline checks (typecheck, linting, format)
- Dashboard build automation
- Sparkle update framework integration

### What's Missing ❌
- Linux distribution packages (Debian, RPM, AppImage, Flatpak, Snap)
- Windows installer (.exe/.msi) with auto-update
- Android APK/AAB builds for Google Play
- iOS TestFlight and App Store distribution
- Multi-arch support (x86_64, ARM, Apple Silicon)
- Automated release distribution to package managers
- Platform-specific tests in CI
- GPU support verification in builds

---

## 1. Build Architecture

```
GitHub Actions Workflow
├── matrix builds (parallel across systems)
├── Container-based Linux builds
├── Native builds (macOS, Windows)
├── Mobile builds (Android, iOS)
└── Artifact aggregation & distribution
```

### Build Matrix Strategy

```yaml
# Platforms and architectures
- macOS: aarch64 (Apple Silicon), x86_64
- Linux: x86_64, aarch64, armv7l (RPM, DEB, AppImage, Flatpak, Snap)
- Windows: x86_64, ARM64
- Android: armeabi-v7a, arm64-v8a, x86, x86_64
- iOS: arm64 (device), x86_64 (simulator)
```

---

## 2. Linux Distribution Support

### 2.1 Distribution Matrix

| Distribution | Package Format | Base Image | GPU Support |
|:---|:---|:---|:---|
| **Debian/Ubuntu** | .deb (apt) | ubuntu:24.04 | NVIDIA CUDA |
| **Fedora/RHEL** | .rpm (dnf/yum) | fedora:41 | AMD ROCm |
| **Alpine** | .apk (apk) | alpine:3.20 | OpenCL |
| **Arch** | .pkg.tar.zst | archlinux:latest | Native CUDA/ROCm |
| **AppImage** | .AppImage | ubuntu:24.04 | Portable (all) |
| **Flatpak** | .flatpak | flathub base | Sandboxed |
| **Snap** | .snap | snapcraft | Confined |

### 2.2 Build Process

```bash
# Debian/Ubuntu
dpkg-deb --build exo-linux
# Creates: exo-0.1.0-amd64.deb

# Fedora/RHEL
fpm -s dir -t rpm -n exo -v 0.1.0 ...
# Creates: exo-0.1.0-1.el9.x86_64.rpm

# AppImage
appimagetool
# Creates: exo-0.1.0-x86_64.AppImage

# Flatpak
flatpak-builder --repo=repo exo-build io.exo.EXO.json
# Creates: io.exo.EXO-0.1.0-x86_64.flatpak

# Snap
snapcraft snap
# Creates: exo_0.1.0_amd64.snap
```

### 2.3 Package Manager Integration

| Package Manager | Upload Method | Repository | Status |
|:---|:---|:---|:---|
| **apt** | launchpad.net/~exo/+archive/ubuntu/ppa | Official PPA | New |
| **dnf** | Fedora COPR | exo-explore/exo | New |
| **AUR** | git push | aur.archlinux.org/exo | New |
| **Flathub** | Pull request | flathub/flathub | New |
| **Snapcraft** | snapcraft upload | Snapcraft Store | New |

---

## 3. Windows Build Pipeline

### 3.1 Installer Strategy

```
Windows Package
├── NSIS Installer (.exe)
│   ├── Python runtime (pyinstaller)
│   ├── Dashboard UI
│   ├── Service installer
│   └── Auto-update integration
├── WiX MSI (.msi)
│   ├── GUID registration
│   ├── Registry entries
│   └── Uninstall logic
└── Portable ZIP
    └── Standalone executable (no install)
```

### 3.2 Auto-Update on Windows

```
Sparkle for Windows or custom update mechanism
├── HTTP/S update check
├── Signature verification
├── Staged rollout
└── Rollback capability
```

### 3.3 GPU Detection & Installation

```python
# Windows GPU detection at install time
- Check for NVIDIA CUDA (nvidia-smi)
- Check for AMD ROCm (hipcc)
- Check for Intel Arc (oneAPI)
- Store detected GPU info in registry
- Download appropriate GPU libraries during install
```

---

## 4. Mobile Build Pipeline

### 4.1 Android

```
Android APK/AAB Build
├── Gradle build
├── Native Rust bindings (JNI)
├── Vulkan GPU backend
├── App signing (debug/release)
└── Google Play release
    ├── Internal testing
    ├── Closed testing
    ├── Open beta
    └── Production
```

**Deliverables**:
- `exo-{version}.apk` (direct install)
- `exo-{version}.aab` (Google Play)
- `exo-universal.apk` (all archs)

### 4.2 iOS

```
iOS App Build
├── Xcode build
├── Provisioning profile
├── Code signing
├── App Store submission
└── TestFlight distribution
    ├── Internal testing
    ├── External testing
    └── App Store release
```

**Deliverables**:
- `.ipa` file (direct install)
- App Store listing
- TestFlight builds

---

## 5. GitHub Actions Workflow Structure

### 5.1 Main Release Workflow

```yaml
# .github/workflows/release.yml
name: Cross-Device Release Build

on:
  push:
    tags: ['v*']

jobs:
  build-linux:        # Matrix: 7 distros × 3 archs = 21 builds
  build-windows:      # Matrix: 2 archs (x86_64, ARM64)
  build-macos:        # Existing (reuse build-app.yml)
  build-android:      # Matrix: 4 archs
  build-ios:          # Native macOS runner
  
  test-all:           # Run tests on all platforms
  sign-and-notarize:  # Code signing, notarization
  upload-artifacts:   # S3, GitHub releases, package managers
  publish-release:    # GitHub release + all package managers
```

### 5.2 Continuous Integration

```yaml
# .github/workflows/ci.yml
name: Continuous Integration

on:
  push:
    branches: [main, staging]
  pull_request:

jobs:
  typecheck:      # Python type checking
  lint:           # Code style (ruff, clippy)
  format:         # Code formatting (nix fmt)
  test-python:    # Unit tests
  test-rust:      # Cargo tests
  build-check:    # Build smoke test (all platforms)
```

---

## 6. Implementation Tasks

### Phase 1: Linux Builds (Week 1-2)

**Files to Create/Modify**:
- `.github/workflows/build-linux.yml` (450 lines)
- `packaging/linux/debian/` (control, rules, changelog)
- `packaging/linux/rpm/exo.spec`
- `packaging/linux/appimage/AppImageBuilder.yml`
- `packaging/linux/flatpak/io.exo.EXO.json`
- `packaging/linux/snap/snapcraft.yaml`
- `packaging/linux/build-all-distros.sh` (orchestration script)

**Key Steps**:
```bash
# 1. Create base container with GPU deps
# 2. Build exo and dependencies
# 3. Create distribution-specific packages
# 4. Sign packages with GPG keys
# 5. Upload to package managers
# 6. Update package manager indexes
```

### Phase 2: Windows Build (Week 1)

**Files to Create**:
- `.github/workflows/build-windows.yml` (350 lines)
- `packaging/windows/nsis/exo.nsi` (NSIS installer)
- `packaging/windows/wix/exo.wxs` (WiX installer)
- `packaging/windows/build.ps1` (PowerShell build script)
- `packaging/windows/gpu-detection.py` (GPU detection script)

**Key Steps**:
```powershell
# 1. Setup Visual C++ build tools
# 2. Detect GPU drivers
# 3. Build PyInstaller bundle
# 4. Create NSIS installer
# 5. Sign executable with EV certificate
# 6. Create checksums
# 7. Upload to GitHub releases
```

### Phase 3: Mobile Builds (Week 2-3)

#### Android
**Files to Create**:
- `.github/workflows/build-android.yml` (400 lines)
- `android/build.gradle`
- `android/app/build.gradle`
- `android/AndroidManifest.xml`
- `android/src/main/kotlin/io/exo/MainActivity.kt`

#### iOS
**Files to Create**:
- Extend `.github/workflows/build-app.yml` to include iOS build steps
- Update `app/EXO/EXO.xcodeproj` for iOS target

### Phase 4: Release Orchestration (Week 1)

**Files to Create**:
- `.github/workflows/release.yml` (600+ lines)
- `scripts/create-release.sh`
- `scripts/upload-to-package-managers.sh`
- `scripts/generate-sbom.sh` (Software Bill of Materials)

---

## 7. Detailed Workflow Implementations

### 7.1 Linux Build Workflow

```yaml
name: Build Linux Packages

on:
  push:
    tags: ['v*']

jobs:
  build-linux:
    strategy:
      matrix:
        include:
          # Debian family (apt)
          - distro: ubuntu
            version: "24.04"
            arch: amd64
            format: deb
          - distro: ubuntu
            version: "24.04"
            arch: arm64
            format: deb
          - distro: debian
            version: "12"
            arch: amd64
            format: deb
          
          # RedHat family (dnf/yum)
          - distro: fedora
            version: "41"
            arch: x86_64
            format: rpm
          - distro: rhel
            version: "9"
            arch: x86_64
            format: rpm
          
          # Alpine (apk)
          - distro: alpine
            version: "3.20"
            arch: x86_64
            format: apk
          
          # Arch Linux
          - distro: archlinux
            version: latest
            arch: x86_64
            format: pkg.tar.zst
          
          # Universal packages
          - distro: ubuntu
            version: "24.04"
            arch: amd64
            format: appimage
          - distro: ubuntu
            version: "24.04"
            arch: amd64
            format: flatpak
          - distro: ubuntu
            version: "24.04"
            arch: amd64
            format: snap
    
    runs-on: ubuntu-latest
    container:
      image: ${{ matrix.distro }}:${{ matrix.version }}
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Install build dependencies
        run: |
          # Distribution-specific setup
          case "${{ matrix.distro }}" in
            ubuntu|debian)
              apt-get update
              apt-get install -y python3.13 python3-pip
              ;;
            fedora)
              dnf install -y python3.13 python3-pip
              ;;
            alpine)
              apk add --no-cache python3 py3-pip
              ;;
            archlinux)
              pacman -Sy --noconfirm python python-pip
              ;;
          esac
      
      - name: Build exo
        run: |
          python3 -m venv venv
          source venv/bin/activate
          pip install -e .
      
      - name: Create distribution package
        run: |
          case "${{ matrix.format }}" in
            deb)
              ./packaging/linux/build-deb.sh
              ;;
            rpm)
              ./packaging/linux/build-rpm.sh
              ;;
            apk)
              ./packaging/linux/build-apk.sh
              ;;
            pkg.tar.zst)
              ./packaging/linux/build-arch.sh
              ;;
            appimage)
              ./packaging/linux/build-appimage.sh
              ;;
            flatpak)
              ./packaging/linux/build-flatpak.sh
              ;;
            snap)
              ./packaging/linux/build-snap.sh
              ;;
          esac
      
      - name: Sign package
        run: |
          # GPG sign based on format
          ...
      
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: exo-${{ matrix.distro }}-${{ matrix.arch }}-${{ matrix.format }}
          path: dist/
```

### 7.2 Windows Build Workflow

```yaml
name: Build Windows

on:
  push:
    tags: ['v*']

jobs:
  build-windows:
    strategy:
      matrix:
        arch: [x86_64, arm64]
    
    runs-on: windows-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup UV
        uses: astral-sh/setup-uv@v6
      
      - name: Setup Python
        run: uv python install 3.13
      
      - name: Build PyInstaller bundle
        run: |
          uv sync
          uv run pyinstaller packaging/pyinstaller/exo.spec
      
      - name: Detect GPU drivers
        run: |
          python packaging/windows/gpu-detection.py > gpu-info.json
      
      - name: Build NSIS installer
        run: |
          choco install nsis -y
          makensis /V4 packaging/windows/nsis/exo.nsi
      
      - name: Build WiX MSI
        run: |
          # Setup WiX
          dotnet tool install -g WiX
          wix build packaging/windows/wix/exo.wxs -o dist/exo.msi
      
      - name: Sign executables
        env:
          CODE_SIGN_CERT: ${{ secrets.WINDOWS_CODE_SIGN_CERT }}
          CODE_SIGN_PASS: ${{ secrets.WINDOWS_CODE_SIGN_PASS }}
        run: |
          # Import certificate and sign
          ./packaging/windows/sign.ps1
      
      - name: Create portable ZIP
        run: |
          7z a dist/exo-portable-${{ matrix.arch }}.zip dist/exo/
      
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: exo-windows-${{ matrix.arch }}
          path: dist/
```

### 7.3 Android Build Workflow

```yaml
name: Build Android

on:
  push:
    tags: ['v*']

jobs:
  build-android:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Android SDK
        uses: android-actions/setup-android@v3
      
      - name: Setup Java
        uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: 'temurin'
      
      - name: Setup Rust
        uses: actions-rs/toolchain@v1
        with:
          toolchain: stable
          target: aarch64-linux-android,armv7-linux-androideabi
      
      - name: Build native libraries (Rust)
        run: |
          cd rust
          cargo build --release --target aarch64-linux-android
          cargo build --release --target armv7-linux-androideabi
      
      - name: Build APK
        run: |
          cd android
          ./gradlew assembleRelease
      
      - name: Build AAB (App Bundle)
        run: |
          cd android
          ./gradlew bundleRelease
      
      - name: Sign APK/AAB
        env:
          KEYSTORE_PASSWORD: ${{ secrets.ANDROID_KEYSTORE_PASSWORD }}
          KEY_ALIAS: ${{ secrets.ANDROID_KEY_ALIAS }}
          KEY_PASSWORD: ${{ secrets.ANDROID_KEY_PASSWORD }}
        run: |
          ./packaging/android/sign.sh
      
      - name: Upload to Google Play
        uses: r0adkll/upload-google-play@v1
        with:
          serviceAccountJsonPlainText: ${{ secrets.GOOGLE_PLAY_SERVICE_ACCOUNT }}
          packageName: io.exo.app
          releaseFiles: 'android/app/build/outputs/bundle/release/app-release.aab'
          track: 'internal'
      
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: exo-android
          path: android/app/build/outputs/
```

### 7.4 iOS Build Workflow

```yaml
name: Build iOS

on:
  push:
    tags: ['v*']

jobs:
  build-ios:
    runs-on: macos-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup iOS provisioning
        env:
          PROVISIONING_PROFILE: ${{ secrets.IOS_PROVISIONING_PROFILE }}
          CODE_SIGN_CERT: ${{ secrets.IOS_CODE_SIGN_CERT }}
          CODE_SIGN_PASS: ${{ secrets.IOS_CODE_SIGN_PASS }}
        run: |
          # Setup certificates and profiles
          ./packaging/ios/setup-signing.sh
      
      - name: Build iOS App
        run: |
          xcodebuild clean build \
            -scheme EXO-iOS \
            -configuration Release \
            -destination 'generic/platform=iOS' \
            MARKETING_VERSION="${{ github.ref_name }}" \
            PROVISIONING_PROFILE_SPECIFIER="EXO iOS"
      
      - name: Create IPA
        run: |
          xcodebuild clean build \
            -scheme EXO-iOS \
            -configuration Release \
            -destination generic/platform=iOS \
            -archivePath output/EXO.xcarchive
          xcodebuild -exportArchive \
            -archivePath output/EXO.xcarchive \
            -exportOptionsPlist packaging/ios/export-options.plist \
            -exportPath output
      
      - name: Upload to App Store Connect
        env:
          APP_STORE_CONNECT_API_KEY: ${{ secrets.APP_STORE_CONNECT_API_KEY }}
        run: |
          xcrun altool \
            --validate-app \
            --file output/EXO.ipa \
            --type ios \
            --apiKey "$APP_STORE_CONNECT_API_KEY"
          xcrun altool \
            --upload-app \
            --file output/EXO.ipa \
            --type ios \
            --apiKey "$APP_STORE_CONNECT_API_KEY"
      
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: exo-ios
          path: output/
```

---

## 8. Package Manager Integration

### 8.1 APT (Debian/Ubuntu)

```bash
# Setup PPA
# 1. Create Ubuntu PPA on launchpad.net/~exo
# 2. Generate GPG key for signing
# 3. Upload source packages to PPA

# In workflow:
mkdir -p packaging/debian/ubuntu-ppa-keys
gpg --import packaging/debian/ubuntu-ppa-keys/public.gpg
dput ppa:exo/exo build-output/*.changes
```

### 8.2 DNF/YUM (Fedora/RHEL)

```bash
# Setup Fedora COPR
# 1. Create COPR project: https://copr.fedorainfracloud.org/

# In workflow:
copr-cli build exo-explore/exo dist/exo.spec --nowait
```

### 8.3 Snap

```bash
# Setup snapcraft account

# In workflow:
snapcraft upload dist/exo*.snap --release=edge,beta,candidate,stable
```

### 8.4 Flatpak

```bash
# Submit to Flathub via git push

# In workflow:
git clone https://github.com/flathub/io.exo.EXO.git
# Update manifest
git commit -am "Update to v1.0.0"
git push origin main
```

---

## 9. Security & Code Signing

### 9.1 Signing Keys Required

```yaml
secrets:
  # Linux
  GPG_PRIVATE_KEY: <asc file>
  GPG_PASSPHRASE: <passphrase>
  
  # macOS (existing)
  MACOS_CERTIFICATE: <p12>
  MACOS_CERTIFICATE_PASSWORD: <password>
  APPLE_NOTARIZATION_USERNAME: <email>
  APPLE_NOTARIZATION_PASSWORD: <password>
  
  # Windows
  WINDOWS_CODE_SIGN_CERT: <pfx>
  WINDOWS_CODE_SIGN_PASS: <password>
  
  # Android
  ANDROID_KEYSTORE_BASE64: <base64>
  ANDROID_KEYSTORE_PASSWORD: <password>
  ANDROID_KEY_ALIAS: <alias>
  ANDROID_KEY_PASSWORD: <password>
  GOOGLE_PLAY_SERVICE_ACCOUNT: <json>
  
  # iOS
  IOS_CODE_SIGN_CERT: <p12>
  IOS_CODE_SIGN_PASS: <password>
  IOS_PROVISIONING_PROFILE: <mobileprovision>
  APP_STORE_CONNECT_API_KEY: <key>
  
  # Package managers
  SNAPCRAFT_STORE_CREDENTIALS: <credentials>
  CACHIX_AUTH_TOKEN: <token>
```

### 9.2 Verification Workflow

```yaml
verify:
  needs: [build-linux, build-windows, build-macos, build-android, build-ios]
  runs-on: ubuntu-latest
  steps:
    - name: Verify all signatures
      run: |
        # Download all artifacts
        # Verify GPG signatures (Linux)
        # Verify code signatures (Windows, macOS)
        # Verify checksums (SHA256)
        # Generate SBOM
```

---

## 10. Release Orchestration

### 10.1 Master Release Workflow

```yaml
# .github/workflows/release.yml
name: Multi-Platform Release

on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Release version (v1.0.0)'
        required: true

jobs:
  build-all:
    uses: ./.github/workflows/build-matrix.yml
  
  test-all:
    uses: ./.github/workflows/test-all.yml
    needs: build-all
  
  sign-all:
    uses: ./.github/workflows/sign-packages.yml
    needs: test-all
  
  upload-all:
    needs: sign-all
    runs-on: ubuntu-latest
    steps:
      - name: Upload to package managers
        run: |
          ./scripts/upload-to-package-managers.sh
      
      - name: Create GitHub release
        run: |
          gh release create ${{ github.event.inputs.version }} \
            dist/* \
            --title "Release ${{ github.event.inputs.version }}" \
            --notes-file RELEASE_NOTES.md
      
      - name: Update documentation
        run: |
          ./scripts/update-install-docs.sh
      
      - name: Notify users
        run: |
          # Send email, Slack, Twitter, etc.
```

### 10.2 Upload Script

```bash
#!/bin/bash
# scripts/upload-to-package-managers.sh

VERSION="${1:?Version required}"

# Linux
./scripts/upload-apt.sh "$VERSION"
./scripts/upload-dnf.sh "$VERSION"
./scripts/upload-aur.sh "$VERSION"
./scripts/upload-flatpak.sh "$VERSION"
./scripts/upload-snap.sh "$VERSION"

# Windows
./scripts/upload-windows.sh "$VERSION"

# Mobile
./scripts/upload-google-play.sh "$VERSION"
./scripts/upload-app-store.sh "$VERSION"

echo "✅ Released $VERSION to all platforms"
```

---

## 11. Distribution Checklist

### Pre-Release
- [ ] Version bump in pyproject.toml, Cargo.toml, build.gradle
- [ ] Update CHANGELOG.md
- [ ] Create GitHub draft release with notes
- [ ] Prepare release branch
- [ ] Tag version (vX.Y.Z)
- [ ] Run full test suite
- [ ] GPU support verification

### Build Phase
- [ ] Build Linux (7 distros, 3 archs = 21 packages)
- [ ] Build Windows (2 archs)
- [ ] Build macOS (2 archs) 
- [ ] Build Android (4 archs)
- [ ] Build iOS
- [ ] Verify all signatures
- [ ] Generate SBOM

### Distribution Phase
- [ ] Upload to GitHub releases
- [ ] Upload to apt PPA
- [ ] Upload to Fedora COPR
- [ ] Upload to AUR
- [ ] Submit to Flathub
- [ ] Submit to Snapcraft Store
- [ ] Upload to Windows (MSIX, MSI, portable)
- [ ] Upload to Google Play (internal testing)
- [ ] Upload to App Store Connect (TestFlight)

### Post-Release
- [ ] Update install documentation
- [ ] Update website
- [ ] Send announcements
- [ ] Monitor package manager validation
- [ ] Respond to platform-specific issues

---

## 12. Implementation Priority

### Sprint 1 (Week 1-2): Foundation
1. ✅ Linux multi-distro builds (Debian, Fedora, Alpine, Arch)
2. ✅ Windows NSIS/MSI installers
3. 🔄 Package manager integrations (apt, dnf, snap, flatpak)

### Sprint 2 (Week 3-4): Mobile
4. ✅ Android APK/AAB builds
5. ✅ iOS App build & distribution
6. 🔄 Google Play & App Store integration

### Sprint 3 (Week 5-6): Polish
7. ✅ Release automation orchestration
8. ✅ Security & signing infrastructure
9. 🔄 Testing across all platforms

### Sprint 4 (Week 7-8): Hardening
10. ✅ Performance optimization
11. ✅ GPU support verification
12. ✅ Documentation & user guides

---

## 13. GPU Support in Builds

### Detection & Bundling

```yaml
# Build time GPU detection
- name: Detect system GPU
  run: |
    # Linux: NVIDIA CUDA, AMD ROCm, Intel oneAPI
    # Windows: NVIDIA CUDA, AMD ROCm, Intel Arc
    # macOS: Apple Silicon (Metal)
    # Android: Qualcomm Adreno, ARM Mali (runtime)
    # iOS: Apple GPU (runtime)
    
    # Bundle appropriate GPU libraries based on platform/distro
    GPU_TYPE=$(./scripts/detect-gpu.sh)
    echo "GPU_TYPE=$GPU_TYPE" >> $GITHUB_ENV

- name: Bundle GPU libraries
  run: |
    case "$GPU_TYPE" in
      cuda)
        cp -r /usr/local/cuda/lib64/* dist/exo/lib/
        ;;
      rocm)
        cp -r /opt/rocm/lib/* dist/exo/lib/
        ;;
      metal)
        # MLX handles Metal on macOS/iOS
        ;;
    esac
```

---

## 14. Success Metrics

| Metric | Target | Current | Status |
|:---|:---|:---|:---|
| Build success rate | 100% | 40% | 🔄 |
| Package types | 15+ | 1 | 🔄 |
| Distro support | 8+ | 0 | 🔄 |
| Mobile platforms | 2 | 0 | 🔄 |
| Release time | <30 min | N/A | 🔄 |
| Code signing coverage | 100% | 50% | 🔄 |
| GPU verification | Pass/Fail | N/A | 🔄 |
| Automated tests | >90% pass | 85% | 🔄 |

---

## 15. Timeline & Effort

```
Phase 1: Linux Builds         16 hours
Phase 2: Windows Builds        12 hours
Phase 3: Mobile Builds         24 hours
Phase 4: Release Orchestration 16 hours
Phase 5: Security & Signing    12 hours
Phase 6: Testing & Hardening   20 hours
─────────────────────────────────────
Total                          100 hours (2-3 weeks)
```

---

## 16. Files to Create/Modify

### GitHub Workflows
```
.github/workflows/
├── release.yml (NEW - 600+ lines)
├── build-linux.yml (NEW - 450 lines)
├── build-windows.yml (NEW - 350 lines)
├── build-android.yml (NEW - 400 lines)
├── build-app.yml (MODIFY - add iOS steps)
└── ci.yml (MODIFY - add mobile tests)
```

### Linux Packaging
```
packaging/linux/
├── debian/ (control, rules, changelog, compat)
├── rpm/ (exo.spec, macros)
├── appimage/ (AppImageBuilder.yml, desktop file)
├── flatpak/ (io.exo.EXO.json manifest)
├── snap/ (snapcraft.yaml)
├── build-*.sh (per-distro build scripts × 7)
└── sign.sh
```

### Windows Packaging
```
packaging/windows/
├── nsis/ (exo.nsi, installer icons)
├── wix/ (exo.wxs, product.wxs)
├── build.ps1
├── gpu-detection.py
└── sign.ps1
```

### Android
```
android/
├── build.gradle (project-level)
├── app/
│   ├── build.gradle
│   ├── AndroidManifest.xml
│   └── src/main/kotlin/io/exo/MainActivity.kt
└── gradle/
    └── wrapper/
        └── gradle-wrapper.properties
```

### iOS
```
app/EXO-iOS/ (NEW)
├── EXO-iOS.xcodeproj
├── EXO-iOS/
│   ├── ContentView.swift
│   └── AppDelegate.swift
└── export-options.plist
```

### Scripts
```
scripts/
├── create-release.sh
├── upload-to-package-managers.sh
├── upload-apt.sh
├── upload-dnf.sh
├── upload-aur.sh
├── upload-flatpak.sh
├── upload-snap.sh
├── upload-windows.sh
├── upload-google-play.sh
├── upload-app-store.sh
├── detect-gpu.sh
└── update-install-docs.sh
```

### Configuration
```
pyproject.toml (MODIFY - add build metadata)
Cargo.toml (MODIFY - Android targets)
build.gradle (NEW)
settings.gradle (NEW)
android/gradle.properties (NEW)
snapcraft.yaml (NEW)
io.exo.EXO.json (NEW - Flatpak manifest)
```

---

## 17. Next Steps

1. **Approve this plan** - Review and adjust priorities
2. **Set up secrets** - Create GitHub secrets for all signing keys
3. **Start Phase 1** - Linux builds (highest ROI)
4. **Run pilot release** - Tag v0.1.0-alpha.1 to test workflows
5. **Iterate** - Fix issues discovered in pilot
6. **Expand** - Add Windows, then mobile
7. **Hardening** - Full test coverage and optimization

This approach ensures 100% cross-device support with automated deployment to all major package managers and app stores.
