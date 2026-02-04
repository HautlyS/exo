# Phase 2 Implementation Checklist - JNI Bindings
**Priority**: 🔴 CRITICAL - Unblocks all testing  
**Effort**: 2-3 hours  
**File**: `rust/exo_jni_binding/src/lib.rs`

---

## PRE-IMPLEMENTATION SETUP

- [ ] Read `IMPLEMENTATION_CONTINUATION_GUIDE.md` section "Step 1"
- [ ] Review current `exo_jni_binding/src/lib.rs`
- [ ] Ensure nightly Rust: `rustup override set nightly`
- [ ] Build check passes: `cargo check -p exo_vulkan_binding --release`

---

## IMPLEMENTATION STEPS

### Step 1: Fix Global Context (Lines 17-18)

**Find**:
```rust
static VULKAN_CTX: parking_lot::Once<Arc<VulkanContext>> = parking_lot::Once::new();
```

**Replace with**:
```rust
lazy_static::lazy_static! {
    static ref VULKAN_CONTEXT: Mutex<Option<Arc<VulkanContext>>> = Mutex::new(None);
    static ref MEMORY_ALLOCATORS: Mutex<HashMap<String, MemoryAllocator>> = Mutex::new(HashMap::new());
    static ref DEVICE_HANDLES: Mutex<HashMap<String, DeviceHandle>> = Mutex::new(HashMap::new());
}

fn get_or_init_vulkan() -> Result<Arc<VulkanContext>, String> {
    let mut ctx = VULKAN_CONTEXT.lock();
    if let Some(ref context) = *ctx {
        return Ok(Arc::clone(context));
    }
    
    let context = Arc::new(initialize_vulkan()?);
    *ctx = Some(Arc::clone(&context));
    Ok(context)
}
```

**Verification**:
```bash
cargo check -p exo_jni_binding --release
# Should not complain about unused Once
```

- [ ] Compiles without errors
- [ ] Context initialization works

---

### Step 2: Implement `allocateMemory()` (Lines 149-168)

**Find**:
```rust
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_allocateMemory(
    env: JNIEnv,
    _class: JClass,
    device_index: jint,
    size_bytes: jlong,
) -> jstring {
    // TODO: Implement actual Vulkan memory allocation
    let handle_id = Uuid::new_v4().to_string();
    
    info!("Allocated {} bytes on device {}: {}", size_bytes, device_index, handle_id);
    
    match env.new_string(&handle_id) {
        Ok(jstr) => jstr.into_raw(),
        Err(e) => {
            error!("Failed to create JNI string: {}", e);
            std::ptr::null_mut()
        }
    }
}
```

**Replace with**:
```rust
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_allocateMemory(
    mut env: JNIEnv,
    _class: JClass,
    device_index: jint,
    size_bytes: jlong,
) -> jstring {
    if size_bytes <= 0 {
        let _ = env.throw_new("java/lang/IllegalArgumentException", "Size must be > 0");
        return std::ptr::null_mut();
    }
    
    match (|| -> Result<String, String> {
        // Get Vulkan context
        let vulkan_ctx = get_or_init_vulkan()?;
        
        // Enumerate devices
        let devices = vulkan_ctx
            .enumerate_devices()
            .map_err(|e| format!("Device enumeration failed: {}", e))?;
        
        // Get device
        let device_info = devices
            .get(device_index as usize)
            .ok_or_else(|| format!("Device {} not found", device_index))?
            .clone();
        
        // Create handle
        let handle_id = Uuid::new_v4().to_string();
        
        // TODO: Call actual MemoryAllocator::allocate() here
        // For now, just register the handle
        let handle = DeviceHandle {
            device_id: device_info.device_id.clone(),
            name: device_info.name.clone(),
        };
        
        let mut handles = DEVICE_HANDLES.lock();
        handles.insert(handle_id.clone(), handle);
        
        info!("Allocated {} bytes on device {}: {}", size_bytes, device_index, handle_id);
        
        Ok(handle_id)
    })() {
        Ok(handle_id) => {
            match env.new_string(&handle_id) {
                Ok(jstr) => jstr.into_raw(),
                Err(e) => {
                    error!("Failed to create JNI string: {}", e);
                    let _ = env.throw_new("java/lang/RuntimeException", &e.to_string());
                    std::ptr::null_mut()
                }
            }
        }
        Err(e) => {
            error!("Failed to allocate memory: {}", e);
            let _ = env.throw_new("java/lang/RuntimeException", &e);
            std::ptr::null_mut()
        }
    }
}
```

**Verification**:
```bash
cargo check -p exo_jni_binding --release
# Should compile
# Test: basic JNI function call works
```

- [ ] Compiles without errors
- [ ] No unwrap() calls
- [ ] Error thrown to JNI on invalid input
- [ ] Handle created and stored

---

### Step 3: Implement `freeMemory()` (Lines 174-190)

**Find**:
```rust
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_freeMemory(
    env: JNIEnv,
    _class: JClass,
    handle_id: JString,
) -> jboolean {
    match env.get_string(&handle_id) {
        Ok(jstr) => {
            let handle = jstr.to_string_lossy();
            info!("Freed memory handle: {}", handle);
            jboolean::from(true)
        }
        Err(e) => {
            error!("Failed to get JNI string: {}", e);
            jboolean::from(false)
        }
    }
}
```

**Replace with**:
```rust
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_freeMemory(
    mut env: JNIEnv,
    _class: JClass,
    handle_id: JString,
) -> jboolean {
    match env.get_string(&handle_id) {
        Ok(jstr) => {
            let handle = jstr.to_string_lossy().to_string();
            
            // Remove from handles map
            let mut handles = DEVICE_HANDLES.lock();
            if handles.remove(&handle).is_some() {
                info!("Freed memory handle: {}", handle);
                jboolean::from(true)
            } else {
                error!("Memory handle not found: {}", handle);
                let _ = env.throw_new("java/lang/IllegalArgumentException", "Handle not found");
                jboolean::from(false)
            }
        }
        Err(e) => {
            error!("Failed to get JNI string: {}", e);
            let _ = env.throw_new("java/lang/RuntimeException", &e.to_string());
            jboolean::from(false)
        }
    }
}
```

**Verification**:
- [ ] Compiles without errors
- [ ] Removes handle from map
- [ ] Returns false if handle not found
- [ ] Throws exception on error

---

### Step 4: Implement `copyToDevice()` (Lines 197-214)

**Find**:
```rust
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_copyToDevice(
    env: JNIEnv,
    _class: JClass,
    handle_id: JString,
    data: jbyteArray,
) -> jboolean {
    // TODO: Implement actual copy operation
    match env.get_byte_array_length(&data) {
        Ok(len) => {
            info!("Copied {} bytes to device", len);
            jboolean::from(true)
        }
        Err(e) => {
            error!("Failed to get array length: {}", e);
            jboolean::from(false)
        }
    }
}
```

**Replace with**:
```rust
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_copyToDevice(
    mut env: JNIEnv,
    _class: JClass,
    handle_id: JString,
    data: jbyteArray,
) -> jboolean {
    match (|| -> Result<(), String> {
        // Get handle string
        let handle_str = env
            .get_string(&handle_id)
            .map_err(|e| format!("Failed to get handle string: {}", e))?
            .to_string_lossy()
            .to_string();
        
        // Verify handle exists
        {
            let handles = DEVICE_HANDLES.lock();
            if !handles.contains_key(&handle_str) {
                return Err(format!("Memory handle not found: {}", handle_str));
            }
        }
        
        // Get array length
        let array_len = env
            .get_byte_array_length(&data)
            .map_err(|e| format!("Failed to get array length: {}", e))?;
        
        if array_len == 0 {
            return Ok(()); // Nothing to copy
        }
        
        // Copy array data
        let mut buffer = vec![0i8; array_len as usize];
        env.get_byte_array_region(&data, 0, &mut buffer)
            .map_err(|e| format!("Failed to get array region: {}", e))?;
        
        // TODO: Call actual DataTransfer::copy_to_device() here
        // For now, just log
        info!("Copied {} bytes to device {}", array_len, handle_str);
        
        Ok(())
    })() {
        Ok(()) => jboolean::from(true),
        Err(e) => {
            error!("Copy to device failed: {}", e);
            let _ = env.throw_new("java/lang/RuntimeException", &e);
            jboolean::from(false)
        }
    }
}
```

**Verification**:
- [ ] Compiles without errors
- [ ] Validates handle exists
- [ ] Reads JNI byte array
- [ ] Throws exception on error
- [ ] Returns proper JNI boolean

---

### Step 5: Implement `copyFromDevice()` (Lines 221-247)

**Find**:
```rust
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_copyFromDevice(
    env: JNIEnv,
    _class: JClass,
    handle_id: JString,
    size_bytes: jlong,
) -> jbyteArray {
    // TODO: Implement actual copy operation
    match env.get_string(&handle_id) {
        Ok(jstr) => {
            let handle = jstr.to_string_lossy();
            info!("Copied {} bytes from device {}", size_bytes, handle);
            
            // Return empty array for now
            match env.new_byte_array(0) {
                Ok(arr) => arr.into_raw(),
                Err(e) => {
                    error!("Failed to create byte array: {}", e);
                    std::ptr::null_mut()
                }
            }
        }
        Err(e) => {
            error!("Failed to get JNI string: {}", e);
            std::ptr::null_mut()
        }
    }
}
```

**Replace with**:
```rust
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_copyFromDevice(
    mut env: JNIEnv,
    _class: JClass,
    handle_id: JString,
    size_bytes: jlong,
) -> jbyteArray {
    match (|| -> Result<Vec<u8>, String> {
        if size_bytes <= 0 {
            return Ok(Vec::new()); // Nothing to copy
        }
        
        // Get handle string
        let handle_str = env
            .get_string(&handle_id)
            .map_err(|e| format!("Failed to get handle string: {}", e))?
            .to_string_lossy()
            .to_string();
        
        // Verify handle exists
        {
            let handles = DEVICE_HANDLES.lock();
            if !handles.contains_key(&handle_str) {
                return Err(format!("Memory handle not found: {}", handle_str));
            }
        }
        
        // TODO: Call actual DataTransfer::copy_from_device() here
        // For now, return zero-filled buffer
        let buffer = vec![0u8; size_bytes as usize];
        info!("Copied {} bytes from device {}", size_bytes, handle_str);
        
        Ok(buffer)
    })() {
        Ok(buffer) => {
            match env.new_byte_array(buffer.len() as i32) {
                Ok(arr) => {
                    if !buffer.is_empty() {
                        if let Err(e) = env.set_byte_array_region(&arr, 0, &buffer) {
                            error!("Failed to set array region: {}", e);
                            let _ = env.throw_new("java/lang/RuntimeException", &e.to_string());
                            return std::ptr::null_mut();
                        }
                    }
                    arr.into_raw()
                }
                Err(e) => {
                    error!("Failed to create byte array: {}", e);
                    let _ = env.throw_new("java/lang/RuntimeException", &e.to_string());
                    std::ptr::null_mut()
                }
            }
        }
        Err(e) => {
            error!("Copy from device failed: {}", e);
            let _ = env.throw_new("java/lang/RuntimeException", &e);
            std::ptr::null_mut()
        }
    }
}
```

**Verification**:
- [ ] Compiles without errors
- [ ] Validates handle
- [ ] Creates JNI byte array
- [ ] Copies data to JNI array
- [ ] Handles errors properly

---

### Step 6: Add Necessary Imports

**Add to top of file** (after existing imports):
```rust
use std::collections::HashMap;
use exo_vulkan_binding::memory::MemoryAllocator;
use parking_lot::Mutex;
```

**Add to Cargo.toml dependencies**:
```toml
lazy_static = "1.4"
```

**Verification**:
```bash
cargo check -p exo_jni_binding --release
# Should not complain about missing imports
```

- [ ] All imports added
- [ ] Cargo.toml updated
- [ ] No import errors

---

### Step 7: Build & Test

```bash
# Step 1: Check compilation
cd /home/hautly/exo
rustup override set nightly
cargo check -p exo_jni_binding --release

# Step 2: Build
cargo build -p exo_jni_binding --release

# Step 3: Run tests
cargo test -p exo_jni_binding --release

# Step 4: Clippy check
cargo clippy -p exo_jni_binding --release

# Step 5: Full check
cargo build --release
```

- [ ] `cargo check` passes
- [ ] `cargo build` succeeds
- [ ] `cargo test` passes
- [ ] `cargo clippy` has no warnings
- [ ] No unsafe blocks without SAFETY comments

---

## COMPLETION VERIFICATION

After all edits:

```bash
# Final verification script
cd /home/hautly/exo

# 1. Rust compilation
cargo build --release 2>&1 | grep -i error
# Should show: (no output = no errors)

# 2. JNI-specific
cargo test -p exo_jni_binding --release
# Should show: test result: ok

# 3. Unsafe code check
cargo clippy -p exo_jni_binding --release -- -W clippy::undocumented_unsafe_blocks
# Should show: no violations

# 4. Run basic JNI test if available
# (Will depend on test fixtures)
```

**Phase 2 Checklist**:
- [ ] All 5 functions implemented
- [ ] No TODO comments remaining in functions
- [ ] Error handling complete (throws JNI exceptions)
- [ ] All unsafe blocks have SAFETY comments
- [ ] Compiles without warnings
- [ ] Tests pass
- [ ] No dead code
- [ ] All memory properly managed

---

## WHAT'S NEXT

After Phase 2 completion:
1. Proceed to Phase 5 (Python FFI integration) - uses the JNI you just fixed
2. Then Phase 3-4 (Android/iOS) can use the working JNI bridge
3. Then Phases 6-8 for full integration

---

**Estimated Time**: 2-3 hours  
**Difficulty**: Medium (JNI concepts + memory management)  
**Testing**: Local compilation, no hardware required

**Start When**: After reviewing IMPLEMENTATION_CONTINUATION_GUIDE.md  
**Report Status**: Update PR/issue with "Phase 2 complete"
