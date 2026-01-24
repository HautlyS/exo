# Android & iOS GPU Clustering - Quick Start Guide

**Status**: Implementation Plan Ready  
**Next Step**: Execute `docs/plans/2025-01-24-android-ios-gpu-sharing.md`  
**Timeline**: 3-4 weeks for 1 developer, 1 week for team

---

## What We're Building

```
Current exo (macOS only)
├── Metal GPU backend (working)
├── MLX inference (working)
└── Dashboard (working)

Target exo (all platforms)
├── Metal (macOS/iOS) ✅ exists, needs iOS extension
├── Vulkan (Android) ❌ TODO (16 hours)
├── CUDA (Linux) ✅ future work
├── Unified discovery ❌ TODO (14 hours)
├── Cross-platform telemetry ❌ TODO (6 hours)
├── Unified build system 🟡 PARTIAL (needs 4h)
└── Multi-platform clustering ❌ TODO (testing)
```

**What You'll Achieve**:
- Android phones/tablets with GPU will join exo clusters
- iPhone/iPad will discover and join clusters via MultipeerConnectivity
- Single GitHub Actions workflow builds all platforms
- Tensor parallelism works across heterogeneous devices

---

## Quick Wins (Do First - 4 hours)

These give immediate value and unblock other work:

### 1. Update Build Workflow Syntax (30 min)
**File**: `.github/workflows/release-all-optimized.yml`

**Change**:
```diff
- echo "version=$VERSION" >> $GITHUB_OUTPUT
+ echo "version=$VERSION" | tee -a $GITHUB_OUTPUT
```

**Why**: Modernize deprecated `set-output` command

**Test**: 
```bash
cd .github/workflows
yamllint release-all-optimized.yml  # Should pass
```

### 2. Add Android Architecture Matrix (1 hour)
**File**: `.github/workflows/release-all-optimized.yml` line 480

**Add after `build-macos` job**:
```yaml
  build-android:
    name: 📱 Build Android (${{ matrix.arch }})
    needs: detect-changes
    runs-on: ubuntu-latest
    if: needs.detect-changes.outputs.build_android == 'true'
    strategy:
      matrix:
        arch: [arm64-v8a, armeabi-v7a, x86_64]
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          java-version: "21"
          distribution: "temurin"
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: aarch64-linux-android,armv7-linux-androideabi,x86_64-linux-android
      
      - name: Build for ${{ matrix.arch }}
        run: |
          cd rust
          case "${{ matrix.arch }}" in
            arm64-v8a) target="aarch64-linux-android" ;;
            armeabi-v7a) target="armv7-linux-androideabi" ;;
            x86_64) target="x86_64-linux-android" ;;
          esac
          cargo build --release --target "$target" || echo "Skipping Android build"
      
      - uses: actions/upload-artifact@v4
        with:
          name: exo-android-${{ matrix.arch }}
          path: rust/target/*/release/*.so
```

**Test**: Push to branch → watch workflow run

### 3. Add iOS to Detect Changes (30 min)
**File**: `.github/workflows/release-all-optimized.yml` line 72

**Change**:
```yaml
outputs:
  # ... existing outputs ...
  build_ios: ${{ steps.changes.outputs.build_ios }}  # ADD THIS
```

**Then in the `detect-changes` step** (line 150), add:
```bash
BUILD_IOS="true"  # iOS always builds when on tag
echo "build_ios=$BUILD_IOS" >> $GITHUB_OUTPUT
```

### 4. Create Build Guide Doc (1.5 hours)
**File**: `.github/workflows/ANDROID_IOS_BUILD_GUIDE.md` (see below)

Copy template:
```markdown
# Android & iOS Build Guide

## Prerequisites

### Android
- Android SDK 34+
- Android NDK r26d
- Java 21 (Temurin)

```bash
rustup target add aarch64-linux-android armv7-linux-androideabi x86_64-linux-android
```

### iOS
- macOS 13.5+
- Xcode 15+

## Building

### Android APK (manual)
```bash
cd rust && cargo build --release --target aarch64-linux-android
cd ../android && ./gradlew assembleRelease
# Output: app/build/outputs/apk/release/
```

### iOS Framework (manual)
```bash
xcodebuild -project app/EXO/EXO.xcodeproj -scheme EXO -configuration Release -sdk iphoneos
```

## CI/CD

Push tag to trigger automated builds:
```bash
git tag v1.0.0
git push origin v1.0.0
# GitHub Actions handles the rest
```
```

---

## Core Work (Week 1-2)

### Phase 1: Vulkan for Android (16 hours)

**Objective**: Enable Android GPU compute via Vulkan

**Files to Create**:
1. `rust/exo_vulkan_binding/Cargo.toml` (dependencies)
2. `rust/exo_vulkan_binding/src/lib.rs` (Vulkan FFI)
3. `src/exo/gpu/backends/vulkan_backend.py` (Python wrapper)
4. `src/exo/gpu/tests/test_vulkan_backend.py` (tests)

**Milestones**:
- [ ] Vulkan device enumeration works
- [ ] Memory allocation/deallocation works
- [ ] Data copy to/from device works
- [ ] Unit tests pass on Linux
- [ ] Integration test passes (if Vulkan available)

**Estimated Time**:
- Implementation: 10 hours (follow plan in docs/plans/)
- Testing & debugging: 6 hours

**How to Start**:
```bash
# Create worktree
git worktree add feature/vulkan-backend

# Follow Phase 1, Task 1 in the implementation plan
# File: docs/plans/2025-01-24-android-ios-gpu-sharing.md
```

### Phase 2: Android JNI Bridge (8 hours)

**Objective**: Connect Kotlin to Rust Vulkan bindings

**Files to Create**:
1. `android/app/src/main/kotlin/io/exo/gpu/VulkanGPUManager.kt`
2. `android/app/src/main/jni/vulkan_jni.rs`
3. Android build configuration

**Milestones**:
- [ ] JNI compilation succeeds
- [ ] Native library (.so) generated
- [ ] Kotlin can call native methods
- [ ] Memory operations work

**Estimated Time**: 8 hours

### Phase 3: Cross-Platform Telemetry (6 hours)

**Objective**: Collect GPU metrics from all platforms

**Files to Create**:
1. `src/exo/network/gpu_telemetry_protocol.py` (message definitions)
2. Update `src/exo/worker/gpu_telemetry.py` (integration)

**Milestones**:
- [ ] Message schemas defined
- [ ] Collection works on Metal
- [ ] Collection works on Vulkan
- [ ] Master aggregates metrics

**Estimated Time**: 6 hours

---

## Integration Work (Week 3-4)

### Phase 4: iOS MultipeerConnectivity (6 hours)

**Objective**: Enable iOS device discovery without App Sandbox restrictions

**Files to Create**:
1. `app/EXO/EXO/Services/MultipeerConnectivityManager.swift`
2. `app/EXO/EXO/Models/PeerDevice.swift`

**Milestones**:
- [ ] iOS can advertise itself
- [ ] iOS can find other devices
- [ ] Connections established
- [ ] UI shows connected peers

**Estimated Time**: 6 hours

### Phase 5: Build System Integration (4 hours)

**Objective**: Consolidate all platform builds into unified workflow

**Files to Modify**:
1. `.github/workflows/release-all-optimized.yml`
2. `Cargo.toml` (Android targets)
3. `pyproject.toml` (platform metadata)

**Milestones**:
- [ ] Workflow syntax valid
- [ ] Android job runs successfully
- [ ] iOS job runs successfully
- [ ] Artifacts uploaded correctly

**Estimated Time**: 4 hours

### Phase 6: Integration Testing (12 hours)

**Objective**: Validate cross-device clustering works

**Files to Create**:
1. `tests/integration/test_cross_device_gpu_clustering.py`
2. `.github/workflows/cross-device-test.yml`

**Test Scenarios**:
- [ ] Device discovery across platforms
- [ ] GPU telemetry collection
- [ ] Heterogeneous tensor parallelism
- [ ] Network resilience

**Estimated Time**: 12 hours

---

## Implementation Checklist

### Before You Start
- [ ] Review `docs/plans/2025-01-24-android-ios-gpu-sharing.md`
- [ ] Review this file
- [ ] Create isolated git worktree: `git worktree add feature/android-ios`
- [ ] Install dependencies: Rust, Android NDK, Xcode
- [ ] Verify existing tests pass: `uv run pytest`

### Week 1
- [ ] Complete Quick Wins (4h)
- [ ] Implement Vulkan backend (16h)
- [ ] Implement Android JNI (8h)
- [ ] Commit: `git commit -m "feat: add Android Vulkan GPU support"`

### Week 2
- [ ] Implement Cross-platform telemetry (6h)
- [ ] Update build workflow (4h)
- [ ] Commit: `git commit -m "feat: GPU telemetry collection + build system"`

### Week 3
- [ ] Implement iOS MultipeerConnectivity (6h)
- [ ] Implement mobile networking (8h)
- [ ] Commit: `git commit -m "feat: iOS discovery and mobile networking"`

### Week 4
- [ ] Create integration tests (12h)
- [ ] Fix any failures from testing
- [ ] Update documentation
- [ ] Create final PR for review

### Verification
- [ ] All tests pass: `uv run pytest`
- [ ] Type checking passes: `uv run basedpyright`
- [ ] Linting passes: `uv run ruff check`
- [ ] Code formatted: `nix fmt`
- [ ] GitHub workflow validates
- [ ] Can build all platforms locally

---

## Testing Strategy

### Unit Tests (Run Always)
```bash
# Test Vulkan backend
uv run pytest src/exo/gpu/tests/test_vulkan_backend.py -v

# Test telemetry
uv run pytest src/exo/network/tests/test_gpu_telemetry.py -v

# Test iOS components
uv run pytest app/EXO/EXOTests/ -v
```

### Integration Tests (Run Before Release)
```bash
# Cross-device clustering
EXO_INTEGRATION_TESTS=1 uv run pytest tests/integration/ -v

# Performance benchmarks
uv run pytest tests/bench/ -v --benchmark-only
```

### Manual Testing (On Real Devices)
```bash
# Android: Install and run
adb install android/app/build/outputs/apk/release/*.apk
adb shell am start -n io.exo/.MainActivity

# iOS: Build and run
xcodebuild -project app/EXO/EXO.xcodeproj -scheme EXO -configuration Release -sdk iphoneos
# Then open with Xcode -> Run on device
```

---

## Common Issues & Fixes

### Android NDK Not Found
```bash
# Install NDK
sdkmanager "ndk;26.0.10792818"

# Add to PATH
export NDK_HOME=$ANDROID_HOME/ndk/26.0.10792818
export PATH=$PATH:$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin
```

### iOS Code Signing Fails
```bash
# List available certificates
security find-identity -v -p codesigning

# Set Xcode team ID in build settings
xcodebuild -project app/EXO/EXO.xcodeproj \
  -scheme EXO \
  DEVELOPMENT_TEAM=<YOUR_TEAM_ID>
```

### Vulkan Not Available on Linux
```bash
# Install Vulkan development files
sudo apt install libvulkan-dev vulkan-tools  # Ubuntu/Debian
sudo dnf install vulkan-devel vulkan-tools   # Fedora

# Verify
vulkaninfo
```

### Build Cache Issues
```bash
# Clear Rust cache
cargo clean

# Clear GitHub Actions cache
gh actions-cache delete <cache-key> --all

# Rebuild everything
uv run pytest --cache-clear
```

---

## Reference Documentation

**Main Implementation Plan**:
- File: `docs/plans/2025-01-24-android-ios-gpu-sharing.md`
- Length: 15KB, 300+ lines
- Contains: Phase-by-phase breakdown, code examples, tests

**Project Review**:
- File: `CROSS_DEVICE_PROJECT_REVIEW.md`
- Length: 20KB, 400+ lines
- Contains: Gap analysis, risk assessment, recommendations

**Existing Foundation Docs**:
- `CROSS-DEVICE-INTEGRATION.md` (GPU architecture)
- `CROSS_DEVICE_BUILD_AUTOMATION.md` (build system design)
- `CROSS_DEVICE_COMPLETION_STATUS.md` (current progress)

**GPU Integration**:
- `README_GPU_INTEGRATION.md` (existing GPU backends)

---

## Success Criteria

### Technical
- ✅ Android can enumerate Vulkan GPU
- ✅ Android can allocate and deallocate GPU memory
- ✅ Android can copy data to/from device
- ✅ iOS can discover other devices via MultipeerConnectivity
- ✅ Cross-platform GPU telemetry collected
- ✅ Heterogeneous device scoring works
- ✅ Tensor parallelism across platforms

### Build & Release
- ✅ GitHub Actions builds all platforms
- ✅ Android APK/AAB created
- ✅ iOS framework builds
- ✅ All tests pass
- ✅ Code signing works

### Quality
- ✅ Type checking (0 errors)
- ✅ Linting (0 errors)
- ✅ Code formatting (100%)
- ✅ Test coverage >80%
- ✅ Integration tests pass

---

## Next Steps

1. **Review the implementation plan**:
   ```bash
   cat docs/plans/2025-01-24-android-ios-gpu-sharing.md | less
   ```

2. **Create isolated worktree**:
   ```bash
   git worktree add feature/android-ios-gpu
   cd feature/android-ios-gpu
   ```

3. **Start with Quick Wins** (4 hours):
   - Update workflow syntax
   - Add Android matrix
   - Add iOS detection
   - Create build guide

4. **Proceed with Phase 1** (Week 1):
   - Follow `Task 1.1` in implementation plan
   - Work through bite-sized steps
   - Commit frequently

5. **Request code review** before merging:
   - Use `requesting-code-review` skill
   - Push to `feature/android-ios-gpu` branch
   - Create PR for human review

---

## Support

**Questions about implementation?**
- Check the detailed plan: `docs/plans/2025-01-24-android-ios-gpu-sharing.md`
- Review the project assessment: `CROSS_DEVICE_PROJECT_REVIEW.md`

**Need help with specific technology?**
- Vulkan: https://www.khronos.org/vulkan/
- JNI: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/
- MultipeerConnectivity: https://developer.apple.com/documentation/multipeerconnectivity

**Want to run integration tests?**
- Set `EXO_INTEGRATION_TESTS=1` environment variable
- Tests will skip gracefully if GPU not available
- See `tests/integration/conftest.py` for fixtures

---

## Timeline Summary

| Week | Focus | Hours | Status |
|:---|:---|---:|:---|
| 1 | Vulkan + JNI | 28 | 🟡 Implementation |
| 2 | Telemetry + Build | 10 | 🟡 Implementation |
| 3 | iOS + Networking | 14 | 🟡 Implementation |
| 4 | Testing + Polish | 12 | 🟡 Testing |
| **Total** | **All Platforms** | **64** | ✅ Ready |

**For team of 2-3**: Can be done in 1-2 weeks  
**For solo developer**: 3-4 weeks with focused effort

---

**Ready to begin? Start with the implementation plan: `docs/plans/2025-01-24-android-ios-gpu-sharing.md`**
