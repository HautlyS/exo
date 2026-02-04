# Android/iOS Cross-Device GPU Implementation Plan
**Status**: Ready for execution  
**Session Start**: 2026-02-04  
**Total Scope**: 7 batches, ~85 hours

---

## Overview
Implement cross-device GPU clustering for Android/iOS devices to participate in exo's distributed AI inference system. This includes:
1. Vulkan backend for Android GPU support
2. iOS Metal enhancement with MultipeerConnectivity
3. Cross-platform GPU telemetry protocol
4. Unified GitHub Actions CI/CD
5. Integration testing suite

---

## Batch 1: Critical Fixes & Vulkan Foundation (Batch 1-2)
### Tasks
1. Create Vulkan Rust FFI bindings (`rust/exo_vulkan_binding/`)
2. Create Python wrapper layer (`src/exo/gpu/backends/vulkan_backend.py`)
3. Test device enumeration

### Files to Create
- `rust/Cargo.toml` - Update to include vulkan crate
- `rust/exo_vulkan_binding/Cargo.toml` - New Vulkan FFI
- `rust/exo_vulkan_binding/src/lib.rs` - Vulkan initialization
- `src/exo/gpu/backends/vulkan_backend.py` - Python wrapper
- Tests for Vulkan discovery

### Verifications
- ✅ `cargo build --release` succeeds
- ✅ Vulkan device enumeration works
- ✅ Python imports work
- ✅ Type checking passes (0 errors)

---

## Batch 2: Vulkan Memory Operations
### Tasks
1. Implement memory allocation/deallocation
2. Implement data copy operations (host->device, device->host)
3. Add memory info querying

### Files to Modify
- `rust/exo_vulkan_binding/src/lib.rs` - Memory functions
- `src/exo/gpu/backends/vulkan_backend.py` - Memory API wrapper

### Verifications
- ✅ Memory allocation returns valid handles
- ✅ Copy operations work bidirectionally
- ✅ Memory queries return correct info

---

## Batch 3: Android JNI Integration
### Tasks
1. Create JNI bindings for Vulkan backend
2. Create Android app integration layer
3. Add Android device discovery

### Files to Create
- `rust/exo_jni_binding/Cargo.toml` - New JNI crate
- `rust/exo_jni_binding/src/lib.rs` - JNI bindings
- `app/android/kotlin/ExoVulkanManager.kt` - Android layer
- `app/android/kotlin/DeviceDiscovery.kt` - NSD discovery

### Verifications
- ✅ JNI calls from Kotlin succeed
- ✅ Device discovery finds peers
- ✅ No resource leaks on exit

---

## Batch 4: iOS Metal Enhancement
### Tasks
1. Create MultipeerConnectivity manager
2. Implement iOS device discovery  
3. Enhance Metal backend for cross-device

### Files to Create
- `app/ios/ExoMultipeerManager.swift` - MultipeerConnectivity
- `app/ios/DeviceDiscovery.swift` - mDNS discovery
- `src/exo/networking/ios_bridge.py` - iOS integration

### Verifications
- ✅ iOS advertises on network
- ✅ iOS discovers other devices
- ✅ Connections established cleanly

---

## Batch 5: Cross-Platform Telemetry Protocol
### Tasks
1. Define GPU telemetry protocol (message formats)
2. Implement telemetry collector
3. Add device scoring with metrics

### Files to Create/Modify
- `src/exo/gpu/telemetry_protocol.py` - Protocol definition
- `src/exo/gpu/telemetry_collector.py` - Collection service
- `src/exo/gpu/device_scorer.py` - Device scoring

### Verifications
- ✅ Metrics collected from all backends
- ✅ Master receives and aggregates telemetry
- ✅ Device scoring reflects metrics

---

## Batch 6: Unified GitHub Actions CI/CD
### Tasks
1. Create unified workflow matrix for all platforms
2. Add Android APK/AAB build
3. Add iOS framework build
4. Configure artifact signing/release

### Files to Create/Modify
- `.github/workflows/build-all-platforms.yml` - Main workflow
- `.github/workflows/test-cross-device.yml` - Test workflow
- `packaging/android/build.gradle` - Android build config
- `packaging/ios/build-framework.sh` - iOS build script

### Verifications
- ✅ Workflow syntax valid
- ✅ Android APK builds successfully
- ✅ iOS framework compiles
- ✅ Tests run in matrix

---

## Batch 7: Integration Testing & Finalization
### Tasks
1. Create cross-device integration tests
2. Test device discovery end-to-end
3. Test heterogeneous clustering  
4. Performance benchmarking
5. Documentation updates

### Files to Create
- `tests/integration/test_cross_device_discovery.py`
- `tests/integration/test_heterogeneous_clustering.py`
- `tests/integration/test_network_resilience.py`
- `docs/CROSS_DEVICE_GUIDE.md`

### Verifications
- ✅ All integration tests pass
- ✅ Cross-platform discovery works
- ✅ Tensor parallelism across devices works
- ✅ Performance benchmarks pass

---

## Pre-Batch Checklist
Before starting each batch:
- [ ] Current branch is `feature/android-ios-gpu`
- [ ] Latest main merged in
- [ ] All checks passing before batch starts
- [ ] Plan for batch read and understood

## Per-Batch Exit Criteria
After each batch:
- [ ] `cargo build --release` succeeds
- [ ] `uv run basedpyright` passes (0 errors)
- [ ] `uv run ruff check` passes
- [ ] `nix fmt` applied
- [ ] `pytest` passes (relevant subset)
- [ ] Git commit with clear message
- [ ] Report ready for review

---

## Ready to Start Batch 1?
