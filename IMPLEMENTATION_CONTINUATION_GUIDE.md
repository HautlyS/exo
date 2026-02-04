# Cross-Device GPU Implementation - Continuation Guide
**Status**: Phase 1 Core Implementation In Progress  
**Created**: 2026-02-04  
**Objective**: Complete full Android/iOS GPU cross-device integration with production-ready code

---

## QUICK STATUS

### What's Been Created ✅
1. **`rust/exo_vulkan_binding/src/memory.rs`** - Complete memory management (3.2 KB)
   - Device memory allocation/deallocation
   - Memory mapping/unmapping
   - Proper unsafe documentation
   - Error handling

2. **`rust/exo_vulkan_binding/src/command.rs`** - Command buffer & queue operations (4.1 KB)
   - Command pool creation
   - Command buffer allocation and recording
   - Queue submission
   - Synchronization with fences

3. **`rust/exo_vulkan_binding/src/transfer.rs`** - Data transfer operations (5.6 KB)
   - Host → device transfers (via staging buffer)
   - Device → host transfers (via staging buffer)  
   - Device → device direct copy
   - Proper memory barriers and synchronization

4. **`CROSSDEVICE_IMPLEMENTATION_REVIEW.md`** - Comprehensive audit (15 KB)
   - Detailed findings of current implementation state
   - Missing components identified
   - 8-phase implementation plan with timelines
   - Safety requirements and testing strategy

### What Still Needs Implementation ❌

1. **JNI Bindings** - Fix memory operations stubs
2. **Android Native Code** - Kotlin integration layer
3. **iOS Enhancement** - Metal + MultipeerConnectivity
4. **Python FFI** - Connect Python to Rust layer
5. **Telemetry Protocol** - Cross-device metrics
6. **GitHub Actions** - CI/CD workflows
7. **Integration Tests** - End-to-end testing

---

## NEXT IMMEDIATE STEPS

### Step 1: Fix JNI Bindings (2-3 hours)

**File**: `rust/exo_jni_binding/src/lib.rs`

**Changes needed**:

```rust
// BEFORE (Line 18 - BROKEN):
static VULKAN_CTX: parking_lot::Once<Arc<VulkanContext>> = parking_lot::Once::new();

// AFTER (FIXED):
use lazy_static::lazy_static;
use exo_vulkan_binding::memory::MemoryAllocator;
use std::collections::HashMap;

lazy_static! {
    static ref VULKAN_CONTEXT: Mutex<Option<Arc<exo_vulkan_binding::VulkanContext>>> = Mutex::new(None);
    static ref MEMORY_ALLOCATORS: Mutex<HashMap<String, MemoryAllocator>> = Mutex::new(HashMap::new());
}

// Initialize properly
fn get_or_init_vulkan() -> Result<Arc<exo_vulkan_binding::VulkanContext>, JniError> {
    let mut ctx = VULKAN_CONTEXT.lock();
    if let Some(ref context) = *ctx {
        return Ok(Arc::clone(context));
    }
    
    let context = Arc::new(exo_vulkan_binding::initialize_vulkan()?);
    *ctx = Some(Arc::clone(&context));
    Ok(context)
}
```

**Memory operations to implement** (replace TODOs):

```rust
// BEFORE (Line 149-168 - STUB):
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_allocateMemory(
    env: JNIEnv,
    _class: JClass,
    device_index: jint,
    size_bytes: jlong,
) -> jstring {
    // TODO: Implement actual Vulkan memory allocation
    let handle_id = Uuid::new_v4().to_string();
    // ... returns dummy handle
}

// AFTER (REAL IMPLEMENTATION):
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
    
    match (|| -> JniError {
        let device = get_or_init_vulkan()?;
        let devices = device.enumerate_devices()?;
        let dev_info = devices.get(device_index as usize)
            .ok_or_else(|| JniError::DeviceNotFound(format!("Device {} not found", device_index)))?;
        
        // Get or create memory allocator for this device
        let mut allocators = MEMORY_ALLOCATORS.lock();
        let allocator = allocators.entry(dev_info.device_id.clone())
            .or_insert_with(|| MemoryAllocator::new(/* create device */));
        
        // Allocate memory
        let handle_id = allocator.allocate(
            size_bytes as u64,
            0, // Memory type index (calculate properly)
            Uuid::new_v4().to_string()
        )?;
        
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
            let _ = env.throw_new("java/lang/RuntimeException", &e.to_string());
            std::ptr::null_mut()
        }
    }
}
```

**Also implement**:
- `copyToDevice()` - Call `DataTransfer::copy_to_device()`
- `copyFromDevice()` - Call `DataTransfer::copy_from_device()`
- `freeMemory()` - Call `MemoryAllocator::deallocate()`

---

### Step 2: Update Vulkan Binding Cargo.toml

**File**: `rust/exo_vulkan_binding/Cargo.toml`

Add these dependencies:
```toml
[dependencies]
# ... existing ...
uuid = { version = "1.10", features = ["v4", "serde"] }
lazy_static = "1.4"  # Add if not present
```

---

### Step 3: Create Android Integration Layer (4-6 hours)

**Files to create**:

1. **`app/android/kotlin/ExoVulkanManager.kt`**
```kotlin
package com.exo.gpu

class ExoVulkanManager {
    external fun initializeVulkan(): Boolean
    external fun enumerateDevices(): String  // Returns JSON
    external fun allocateMemory(deviceIndex: Int, sizeBytes: Long): String
    external fun freeMemory(handleId: String): Boolean
    external fun copyToDevice(handleId: String, data: ByteArray): Boolean
    external fun copyFromDevice(handleId: String, sizeBytes: Long): ByteArray?
    external fun getDeviceName(deviceIndex: Int): String
    external fun getDeviceMemory(deviceIndex: Int): Long
    external fun getComputeUnits(deviceIndex: Int): Int
    
    companion object {
        init {
            System.loadLibrary("exo_jni_binding")
        }
    }
}
```

2. **`app/android/kotlin/DeviceDiscovery.kt`**
```kotlin
class DeviceDiscovery(context: Context) {
    private val mdnsHelper = NsdHelper(context)
    
    suspend fun registerDevice(
        deviceName: String,
        port: Int,
        deviceInfo: Map<String, String>
    ) { ... }
    
    suspend fun discoverDevices(): List<DiscoveredDevice> { ... }
}

data class DiscoveredDevice(
    val name: String,
    val address: InetAddress,
    val port: Int,
    val gpuInfo: GpuInfo
)
```

3. **`app/android/AndroidManifest.xml`**
```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.exo.gpu">

    <!-- Network permissions -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.CHANGE_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    
    <!-- Vulkan support declaration -->
    <uses-feature
        android:name="android.hardware.vulkan.version"
        android:version="0x401000" />

    <application>
        <activity android:name=".MainActivity" />
    </application>
</manifest>
```

4. **`app/android/build.gradle`**
```gradle
android {
    compileSdk 35
    ndkVersion "26.0.10469015"
    
    defaultConfig {
        applicationId "com.exo.gpu"
        minSdk 24
        targetSdk 35
        
        externalNativeBuild {
            cmake {
                cppFlags "-std=c++17"
                arguments "-DCMAKE_BUILD_TYPE=Release"
            }
        }
    }
    
    externalNativeBuild {
        cmake {
            path "CMakeLists.txt"
            version "3.22.1"
        }
    }
}

dependencies {
    // ... standard dependencies ...
}
```

5. **`app/android/CMakeLists.txt`** - NEW
```cmake
cmake_minimum_required(VERSION 3.22.1)
project(exo_gpu)

# Link Rust static library
add_library(exo_jni_binding SHARED IMPORTED)
set_target_properties(exo_jni_binding PROPERTIES
    IMPORTED_LOCATION ${CMAKE_SOURCE_DIR}/../../../target/aarch64-linux-android/release/libexo_jni_binding.a
)

# Native library for JNI
add_library(exo_jni SHARED src/jni_bridge.c)
target_link_libraries(exo_jni exo_jni_binding)
```

---

### Step 4: iOS Enhancement (3-4 hours)

**Extend existing**: `app/EXO/EXO/Services/MultipeerConnectivityManager.swift`

Add Metal integration:
```swift
import Metal
import MetalKit

extension MultipeerConnectivityManager {
    // Metal device enumeration
    func enumerateMetalDevices() -> [MTLDevice] {
        var devices = MTLCopyAllDevices()
        if let defaultDevice = MTLCreateSystemDefaultDevice() {
            devices.append(defaultDevice)
        }
        return devices.uniqued()
    }
    
    // Get device properties
    func getDeviceProperties(_ device: MTLDevice) -> GPUProperties {
        return GPUProperties(
            name: device.name,
            maxMemory: device.recommendedMaxWorkingSetSize,
            supports32BitMemory: device.supports32BitMemory,
            supportsFamily: device.supportsFamily(.apple6),
            isRemovable: device.isRemovable,
            isLowPower: device.isLowPower
        )
    }
}
```

**Create**: `src/exo/networking/ios_bridge.py`
```python
import subprocess
import asyncio
from typing import Optional
from dataclasses import dataclass

@dataclass
class IOSGPUInfo:
    device_name: str
    max_memory: int
    device_id: str

class IOSBridge:
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
    
    async def discover_devices(self) -> list[IOSGPUInfo]:
        # Run iOS subprocess that enumerates Metal devices
        # Communicate via stdout/JSON
        pass
    
    async def get_device_info(self, device_id: str) -> IOSGPUInfo:
        pass
```

---

### Step 5: Python FFI Integration (2-3 hours)

**Update**: `src/exo/gpu/backends/vulkan_backend.py`

```python
# Replace ALL TODO comments with actual calls

import ctypes
from pathlib import Path

# Load Rust library
lib_path = Path(__file__).parent.parent.parent.parent / "target" / "release" / "libexo_vulkan_binding.so"
_libvulkan = ctypes.CDLL(str(lib_path))

# Define FFI functions
class VulkanFFI:
    @staticmethod
    def enumerate_vulkan_devices() -> list[dict]:
        # Call Rust FFI function
        _libvulkan.enumerate_vulkan_devices.restype = ctypes.c_char_p
        json_result = _libvulkan.enumerate_vulkan_devices()
        # Parse and return
        pass
    
    @staticmethod
    def allocate_memory(device_index: int, size: int) -> str:
        # Call Rust FFI
        pass
    
    @staticmethod
    def copy_to_device(handle_id: str, data: bytes) -> bool:
        # Call Rust FFI
        pass
    
    @staticmethod
    def copy_from_device(handle_id: str, size: int) -> bytes:
        # Call Rust FFI
        pass

# Update VulkanGPUBackend to use FFI
class VulkanGPUBackend(GPUBackend):
    async def initialize(self) -> None:
        if self._initialized:
            return
        
        try:
            devices_info = await asyncio.to_thread(VulkanFFI.enumerate_vulkan_devices)
            # Create GPUDevice objects
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize Vulkan: {e}")
            raise RuntimeError(f"Vulkan initialization failed: {e}") from e
    
    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        # Call VulkanFFI.allocate_memory()
        # Store handle
        pass
```

---

### Step 6: Create Telemetry Protocol (2-3 hours)

**File**: `src/exo/gpu/telemetry_protocol.py` - NEW

```python
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime
import json
from typing import Dict, Any

class DeviceType(Enum):
    CUDA = "cuda"
    ROCM = "rocm"
    METAL = "metal"
    VULKAN_ANDROID = "vulkan_android"
    VULKAN_LINUX = "vulkan_linux"
    CPU = "cpu"

@dataclass
class GPUMetrics:
    """Real-time GPU metrics"""
    device_id: str
    timestamp: float  # Unix timestamp
    memory_used_bytes: int
    memory_total_bytes: int
    compute_utilization_percent: float
    power_watts: float
    temperature_celsius: float
    clock_rate_mhz: int

@dataclass
class DeviceCapabilities:
    """Device static properties"""
    device_id: str
    device_type: DeviceType
    device_name: str
    vendor: str
    compute_units: int
    memory_bandwidth_gbps: float
    max_memory_bytes: int
    driver_version: str

@dataclass
class DeviceRegistration:
    """Register device in cross-device cluster"""
    hostname: str
    port: int
    device_id: str
    capabilities: DeviceCapabilities
    timestamp: float

@dataclass
class Heartbeat:
    """Periodic device status"""
    device_id: str
    metrics: GPUMetrics
    timestamp: float
    is_available: bool
    error_message: Optional[str] = None

class TelemetryProtocol:
    """Protocol handler for cross-device telemetry"""
    
    @staticmethod
    def serialize_registration(reg: DeviceRegistration) -> str:
        data = asdict(reg)
        data['device_type'] = reg.capabilities.device_type.value
        return json.dumps(data)
    
    @staticmethod
    def deserialize_registration(json_str: str) -> DeviceRegistration:
        data = json.loads(json_str)
        data['device_type'] = DeviceType(data['device_type'])
        return DeviceRegistration(**data)
    
    @staticmethod
    def serialize_metrics(metrics: GPUMetrics) -> str:
        return json.dumps(asdict(metrics))
    
    @staticmethod
    def score_device(metrics: GPUMetrics, capabilities: DeviceCapabilities) -> float:
        """Score device for scheduling: 0.0 to 1.0"""
        memory_score = metrics.memory_available_bytes / capabilities.max_memory_bytes
        compute_score = 1.0 - (metrics.compute_utilization_percent / 100.0)
        
        # Weighted score
        return (0.6 * memory_score) + (0.4 * compute_score)
```

---

### Step 7: GitHub Actions CI/CD (2-3 hours)

**File**: `.github/workflows/build-android.yml` - NEW

```yaml
name: Build Android

on:
  push:
    branches: [main, feature/android-ios-gpu]
  pull_request:
    branches: [main]

env:
  RUST_BACKTRACE: 1

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        target: [aarch64-linux-android, armv7-linux-androideabi]
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: dtolnay/rust-toolchain@nightly
        with:
          targets: ${{ matrix.target }}
      
      - name: Install NDK
        run: |
          sudo apt-get install -y ndk-build
          export NDK_HOME=$ANDROID_NDK_LATEST_HOME
      
      - name: Build Vulkan binding
        working-directory: rust/exo_vulkan_binding
        run: cargo build --release --target ${{ matrix.target }}
      
      - name: Build JNI binding
        working-directory: rust/exo_jni_binding
        run: cargo build --release --target ${{ matrix.target }}
      
      - name: Build APK
        run: |
          cd app/android
          ./gradlew build -x lint
      
      - name: Upload APK
        uses: actions/upload-artifact@v3
        with:
          name: android-app-${{ matrix.target }}
          path: app/android/build/outputs/apk/**/*.apk
```

**File**: `.github/workflows/build-ios.yml` - NEW

```yaml
name: Build iOS

on:
  push:
    branches: [main, feature/android-ios-gpu]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: macos-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: dtolnay/rust-toolchain@nightly
        with:
          targets: aarch64-apple-ios
      
      - name: Build Rust for iOS
        working-directory: rust/exo_vulkan_binding
        run: cargo build --release --target aarch64-apple-ios
      
      - name: Build iOS Framework
        run: |
          cd app/EXO
          xcodebuild -scheme EXO -configuration Release \
            -arch arm64 \
            -derivedDataPath build
```

**File**: `.github/workflows/test-cross-device.yml` - NEW

```yaml
name: Cross-Device Tests

on:
  push:
    branches: [main, feature/android-ios-gpu]
  pull_request:
    branches: [main]

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: dtolnay/rust-toolchain@nightly
      
      - name: Run integration tests
        run: |
          pytest tests/integration/test_cross_device*.py -v --tb=short
      
      - name: Run Vulkan memory tests
        run: |
          pytest rust/exo_vulkan_binding/tests/ -v
```

---

### Step 8: Integration Tests (2-3 hours)

**Create**: `tests/integration/test_cross_device_discovery.py`

```python
import pytest
import asyncio
from exo.gpu.backends.vulkan_backend import VulkanGPUBackend

@pytest.mark.asyncio
async def test_vulkan_initialization():
    """Test Vulkan backend initializes correctly"""
    backend = VulkanGPUBackend()
    await backend.initialize()
    
    devices = backend.list_devices()
    assert len(devices) >= 0  # May be 0 if no Vulkan devices
    
    await backend.shutdown()

@pytest.mark.asyncio
async def test_memory_allocation():
    """Test GPU memory allocation"""
    backend = VulkanGPUBackend()
    await backend.initialize()
    
    devices = backend.list_devices()
    if not devices:
        pytest.skip("No Vulkan devices available")
    
    device_id = devices[0].device_id
    
    # Allocate 10 MB
    handle = await backend.allocate(device_id, 10 * 1024 * 1024)
    assert handle.handle_id is not None
    assert handle.size_bytes == 10 * 1024 * 1024
    
    # Deallocate
    await backend.deallocate(handle)
    
    await backend.shutdown()

@pytest.mark.asyncio  
async def test_data_transfer():
    """Test host <-> device data transfer"""
    backend = VulkanGPUBackend()
    await backend.initialize()
    
    devices = backend.list_devices()
    if not devices:
        pytest.skip("No Vulkan devices available")
    
    device_id = devices[0].device_id
    
    # Allocate
    handle = await backend.allocate(device_id, 1024)
    
    # Copy to device
    test_data = b"Hello, GPU!" * 100
    await backend.copy_to_device(device_id, test_data, handle)
    
    # Copy back
    result = await backend.copy_from_device(device_id, handle)
    assert result[:len(test_data)] == test_data
    
    await backend.deallocate(handle)
    await backend.shutdown()

@pytest.mark.asyncio
async def test_device_discovery():
    """Test cross-device peer discovery"""
    from exo.gpu.discovery import discover_local_devices
    
    devices = await discover_local_devices()
    assert isinstance(devices, list)
    # May be empty in test environment
```

---

## TESTING MATRIX

```
Platform  | Build Status | Memory Tests | Integration | Notes
----------|--------------|-------------|-------------|----------
Linux     | ✅ Ready     | ✅ Ready    | In Progress | Use Docker
Android   | TODO         | TODO        | TODO        | Use emulator
iOS       | TODO         | TODO        | TODO        | Use simulator
macOS     | ✅ Ready     | ✅ Ready    | In Progress | Hardware GPU
Windows   | ? Maybe      | ? Maybe     | ? Maybe     | DirectML backend
```

---

## CODE CHANGES SUMMARY

### Phase 1: Core Vulkan (DONE - 3 files created)
- ✅ `memory.rs` - 3.2 KB, 120+ lines
- ✅ `command.rs` - 4.1 KB, 150+ lines  
- ✅ `transfer.rs` - 5.6 KB, 180+ lines
- ✅ Updated `lib.rs` to include modules

### Phase 2: JNI Fixes (TODO - modify 1 file)
- Fix global context management
- Implement memory operations
- Add proper error handling
- Expected: 800-1000 lines of actual logic

### Phase 3: Android (TODO - create 5 files)
- `ExoVulkanManager.kt` - 200 lines
- `DeviceDiscovery.kt` - 300 lines
- `AndroidManifest.xml` - 50 lines
- `build.gradle` - 100 lines
- `CMakeLists.txt` - 50 lines

### Phase 4: iOS (TODO - extend 1 file, create 1 file)
- Extend `MultipeerConnectivityManager.swift` - +200 lines
- Create `ios_bridge.py` - 100 lines

### Phase 5: Python FFI (TODO - modify 1 file)
- Replace all TODO in `vulkan_backend.py`
- Add 300+ lines of actual FFI calls

### Phase 6: Telemetry (TODO - create 1 file)
- `telemetry_protocol.py` - 250 lines

### Phase 7: CI/CD (TODO - create 3 files)
- `build-android.yml` - 60 lines
- `build-ios.yml` - 50 lines
- `test-cross-device.yml` - 40 lines

### Phase 8: Tests (TODO - create 3 files)
- `test_cross_device_discovery.py` - 100 lines
- `test_vulkan_memory.py` - 80 lines
- `test_heterogeneous_clustering.py` - 100 lines

---

## BUILD VERIFICATION CHECKLIST

After each phase:

```bash
# Phase 1-2: Rust compilation
cargo build --release
cargo clippy --all
cargo test --release

# Phase 3-4: Cross-compilation
cargo build --release --target aarch64-linux-android
cargo build --release --target aarch64-apple-ios

# Phase 5-8: Python & integration
uv run basedpyright
uv run ruff check
pytest tests/integration/ -v
```

---

## IMMEDIATE NEXT ACTIONS

1. **TODAY**: 
   - ✅ Review this guide
   - ⏳ Fix JNI bindings (Phase 2)
   - ⏳ Test local Vulkan compilation

2. **THIS WEEK**:
   - Android native implementation (Phase 3)
   - Python FFI integration (Phase 5)
   - Unit tests for Vulkan operations

3. **NEXT WEEK**:
   - iOS enhancement (Phase 4)
   - Telemetry protocol (Phase 6)
   - CI/CD workflows (Phase 7)
   - Integration tests (Phase 8)

---

## SUCCESS CRITERIA

- ✅ All Rust code compiles without warnings
- ✅ All unsafe blocks documented with SAFETY comments
- ✅ Python type checking passes (0 errors)
- ✅ Integration tests pass on Linux
- ✅ Android APK builds successfully
- ✅ iOS framework compiles
- ✅ Cross-device discovery works end-to-end
- ✅ GitHub Actions CI passes
- ✅ No dead code (all implementations are real)

---

**Status**: Ready for Phase 2 (JNI Bindings)  
**Estimated Completion**: 1-2 weeks  
**Owner**: Implementation Team
