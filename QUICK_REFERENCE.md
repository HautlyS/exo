# Quick Reference Card - Cross-Device GPU Implementation
**Keep this handy while implementing**

---

## 📖 WHAT TO READ FIRST

```
START HERE ↓
EXECUTION_SUMMARY.md (5 min)
        ↓
PHASE2_JNI_CHECKLIST.md (10 min)
        ↓
START IMPLEMENTING
```

---

## 🔧 IMMEDIATE COMMANDS

```bash
# Check current state
cd /home/hautly/exo
rustup override set nightly
cargo check --release

# Build Phase 1 (Vulkan)
cargo build -p exo_vulkan_binding --release

# Test Phase 1
cargo test -p exo_vulkan_binding --release

# Start Phase 2 (JNI)
cargo check -p exo_jni_binding --release

# After Phase 2, test Python
pytest tests/ -k vulkan -v

# Final verification
cargo build --release && cargo clippy --all
```

---

## 📂 FILES YOU NEED TO KNOW ABOUT

### Just Implemented ✅
```
rust/exo_vulkan_binding/src/
├── lib.rs          (updated - added module exports)
├── memory.rs       (NEW - 3.2 KB)
├── command.rs      (NEW - 4.1 KB)
└── transfer.rs     (NEW - 5.6 KB)
```

### To Implement Next ⏳
```
Phase 2 (JNI - HIGH PRIORITY):
rust/exo_jni_binding/src/lib.rs (modify - follow PHASE2_JNI_CHECKLIST.md)

Phase 5 (Python FFI):
src/exo/gpu/backends/vulkan_backend.py (modify - replace TODO comments)

Phase 3 (Android):
app/android/kotlin/ExoVulkanManager.kt (create)
app/android/kotlin/DeviceDiscovery.kt (create)
app/android/build.gradle (create)
app/android/AndroidManifest.xml (create)
app/android/CMakeLists.txt (create)

Phase 4 (iOS):
app/EXO/EXO/Services/MultipeerConnectivityManager.swift (extend)
src/exo/networking/ios_bridge.py (create)

Phase 6 (Telemetry):
src/exo/gpu/telemetry_protocol.py (create)

Phase 7 (CI/CD):
.github/workflows/build-android.yml (create)
.github/workflows/build-ios.yml (create)
.github/workflows/test-cross-device.yml (create)

Phase 8 (Tests):
tests/integration/test_cross_device_discovery.py (create)
tests/integration/test_vulkan_memory.py (create)
tests/integration/test_heterogeneous_clustering.py (create)
```

---

## 🎯 CURRENT PHASE STATUS

**Phase 1**: ✅ COMPLETE
- Vulkan device enumeration
- Memory management
- Command buffers
- Data transfer (all directions)
- 450+ lines of production code
- All unsafe documented

**Phase 2**: ⏳ READY TO START
- **Priority**: 🔴 CRITICAL
- **Time**: 2-3 hours
- **Blocker**: Unblocks Android, iOS, Python
- **Guide**: PHASE2_JNI_CHECKLIST.md
- **What to do**: Fix JNI global context and implement memory ops

**Phases 3-8**: ⏳ PLANNED
- See IMPLEMENTATION_CONTINUATION_GUIDE.md for details

---

## 🚨 CRITICAL ISSUES TO REMEMBER

### Current Vulnerabilities (Fixed in Phase 1)
1. ✅ No actual memory allocation (Phase 1 fixed)
2. ✅ No data transfer (Phase 1 fixed)
3. ✅ No command buffer management (Phase 1 fixed)
4. ✅ Unsafe code without documentation (Phase 1 fixed)

### What Still Needs Fixing (Phase 2+)
1. ⚠️ JNI context management - NEXT (Phase 2)
2. ⚠️ JNI memory ops all stub - NEXT (Phase 2)
3. ⚠️ Python FFI not calling Rust - (Phase 5)
4. ⚠️ Android native missing - (Phase 3)
5. ⚠️ iOS integration incomplete - (Phase 4)

---

## 📊 PROGRESS TRACKING

Copy this matrix and update as you go:

```
PHASE | COMPONENT        | STATUS    | TIME | VERIFY
------|------------------|-----------|------|------------
1     | Vulkan FFI       | ✅ DONE   | 5h   | cargo build
2     | JNI Bindings     | ⏳ TODO   | 2-3h | jni tests
3     | Android          | ⏳ TODO   | 6-8h | apk builds
4     | iOS              | ⏳ TODO   | 3-5h | xcode builds
5     | Python FFI       | ⏳ TODO   | 2-3h | pytest
6     | Telemetry        | ⏳ TODO   | 2-3h | import works
7     | CI/CD            | ⏳ TODO   | 2-3h | workflow runs
8     | Tests            | ⏳ TODO   | 2-3h | all pass
```

---

## 🔍 HOW TO DEBUG

### Rust Compilation Issues
```bash
cargo build --release 2>&1 | head -50
# Look for actual error, not the cascade
cargo check -p exo_jni_binding --release
# Single out the problematic crate
```

### JNI Issues
- Check PHASE2_JNI_CHECKLIST.md for specific function signatures
- Verify env.throw_new() calls are correct
- Check return types match JNI spec

### Python Import Errors
```bash
cd /home/hautly/exo
python3 -c "from src.exo.gpu.backends import vulkan_backend; print('OK')"
# Should import without error
```

### Type Checking
```bash
uv run basedpyright src/exo/gpu/backends/vulkan_backend.py
# Should show 0 errors
```

---

## ✅ VALIDATION BEFORE COMMIT

**For each phase**:
```
Rust:
☐ cargo check --release passes
☐ cargo clippy --all shows no warnings
☐ cargo test --release passes
☐ No unsafe blocks without SAFETY comments
☐ No unwrap() in library code

Python:
☐ uv run basedpyright passes (0 errors)
☐ uv run ruff check passes
☐ pytest tests/ passes

Cross-compile:
☐ cargo build --target aarch64-linux-android
☐ cargo build --target aarch64-apple-ios
```

---

## 📝 COMMON PATTERNS

### Safe Unsafe Block
```rust
// SAFETY: Explanation of why this is safe
// - ptr is valid because we just created it
// - lifetime is correct because we hold the Arc
// - no concurrent access because protected by Mutex
unsafe {
    self.device.destroy_instance(None);
}
```

### Error Handling
```rust
match operation() {
    Ok(result) => handle_success(result),
    Err(e) => {
        error!("Operation failed: {}", e);
        // Don't panic - return Result
        return Err(e);
    }
}
```

### Resource Cleanup
```rust
impl Drop for Resource {
    fn drop(&mut self) {
        unsafe {
            // SAFETY: resource is valid, we own it
            destroy_resource(self.handle);
        }
    }
}
```

---

## 🎓 KEY CONCEPTS

### Vulkan Layers (Bottom to Top)
```
Rust FFI (exo_vulkan_binding)
    ↑
JNI Bridge (exo_jni_binding)
    ↑
Kotlin/Swift (Native apps)
    ↑
Python FFI (vulkan_backend.py)
    ↑
exo framework (distributed ML)
    ↑
User applications
```

### Memory Operations Flow
```
Host Memory
    ↓
Staging Buffer (Host-Visible)
    ↓ (DMA copy)
Device Memory (GPU-Local)
    ↓
GPU Computation
    ↓
Device Memory
    ↓ (DMA copy)
Staging Buffer (Host-Visible)
    ↓
Host Memory
```

### Synchronization
```
Record Commands → Submit → Wait (Fence) → Read Results
                            ↑ (Queue synchronization)
```

---

## 🆘 WHEN STUCK

1. **Build fails**: Read error message completely, don't just fix first error
2. **Type error**: Check function signatures against docs
3. **Test fails**: Add debug prints, run with `--nocapture`
4. **Not sure**: Check IMPLEMENTATION_CONTINUATION_GUIDE.md examples

---

## 🎬 START HERE

1. **Right now**: `EXECUTION_SUMMARY.md` (5 min)
2. **Next**: `PHASE2_JNI_CHECKLIST.md` (10 min)
3. **Then**: Implement Phase 2 (2-3 hours)
4. **Verify**: `cargo build --release && cargo test --release`
5. **Next**: Phase 5 (Python FFI) - 2-3 hours

---

**Last Updated**: 2026-02-04  
**Status**: Phase 1 Complete, Phase 2 Ready  
**Keep This Handy**: Yes - Referenced during implementation
