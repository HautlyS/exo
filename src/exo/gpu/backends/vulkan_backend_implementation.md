# Vulkan Backend Implementation Guide

This document outlines the implementation of the Vulkan GPU backend for Android support.

## Architecture Overview

```
Python Layer (exo/gpu/backends/vulkan_backend.py)
    ↓
Rust FFI Layer (exo_vulkan_bindings/src/lib.rs)
    ↓
Vulkan SDK (ash crate - Rust Vulkan bindings)
    ↓
Hardware GPUs (Adreno, Mali, PowerVR)
```

## Phase 1: Core Implementation (16 hours)

### 1.1 Rust FFI Layer (4 hours)

**File**: `rust/exo_vulkan_bindings/src/lib.rs`

Core operations to implement:

```rust
pub struct VulkanInstance {
    instance: ash::Instance,
    devices: Vec<PhysicalDevice>,
}

pub struct VulkanDevice {
    device: ash::Device,
    physical_device: vk::PhysicalDevice,
    graphics_queue: vk::Queue,
}

pub struct VulkanBuffer {
    buffer: vk::Buffer,
    memory: vk::DeviceMemory,
    size: vk::DeviceSize,
}

// Core functions to implement:
pub unsafe fn create_instance() -> Result<VulkanInstance>
pub unsafe fn enumerate_devices(instance: &VulkanInstance) -> Result<Vec<DeviceInfo>>
pub unsafe fn create_device(instance: &VulkanInstance, physical_device: vk::PhysicalDevice) -> Result<VulkanDevice>
pub unsafe fn allocate_buffer(device: &VulkanDevice, size: vk::DeviceSize) -> Result<VulkanBuffer>
pub unsafe fn copy_buffer(device: &VulkanDevice, src: &VulkanBuffer, dst: &VulkanBuffer, size: vk::DeviceSize) -> Result<()>
pub unsafe fn submit_work(device: &VulkanDevice, command_buffer: vk::CommandBuffer) -> Result<()>
```

### 1.2 Device Enumeration (2 hours)

Implement physical device detection:

```rust
fn get_device_name(instance: &ash::Instance, device: vk::PhysicalDevice) -> String
fn get_device_memory(instance: &ash::Instance, device: vk::PhysicalDevice) -> vk::DeviceSize
fn get_device_properties(instance: &ash::Instance, device: vk::PhysicalDevice) -> DeviceProperties
```

Steps:
1. Create Vulkan instance with validation layers
2. Enumerate physical devices
3. Get device properties (name, memory, compute capability)
4. Filter for compute-capable devices
5. Store device information

### 1.3 Memory Management (3 hours)

Implement buffer allocation/deallocation:

```rust
fn allocate_device_memory(
    device: &VulkanDevice,
    size: vk::DeviceSize,
    memory_type: u32,
) -> Result<vk::DeviceMemory>

fn free_device_memory(
    device: &VulkanDevice,
    memory: vk::DeviceMemory,
) -> Result<()>

fn copy_host_to_device(
    device: &VulkanDevice,
    host_data: &[u8],
    device_buffer: vk::Buffer,
    offset: vk::DeviceSize,
) -> Result<()>

fn copy_device_to_host(
    device: &VulkanDevice,
    device_buffer: vk::Buffer,
    offset: vk::DeviceSize,
    size: vk::DeviceSize,
) -> Result<Vec<u8>>
```

Key considerations:
- Vulkan requires memory staging for host↔device transfers
- Implement staging buffer pool for efficiency
- Handle memory type selection (device-local, host-visible, etc.)
- Proper memory barrier handling for coherency

### 1.4 Compute Operations (4 hours)

Implement command buffer recording and execution:

```rust
fn create_command_buffer(device: &VulkanDevice) -> Result<vk::CommandBuffer>

fn record_copy_command(
    device: &VulkanDevice,
    command_buffer: vk::CommandBuffer,
    src_buffer: vk::Buffer,
    dst_buffer: vk::Buffer,
    size: vk::DeviceSize,
) -> Result<()>

fn submit_command_buffer(
    device: &VulkanDevice,
    command_buffer: vk::CommandBuffer,
) -> Result<()>

fn wait_for_queue(device: &VulkanDevice, queue: vk::Queue) -> Result<()>
```

Key considerations:
- Command pool management
- Queue submission and synchronization
- Fence/semaphore handling
- Proper command buffer resets

### 1.5 Error Handling (2 hours)

Implement proper Vulkan error handling:

```rust
pub enum VulkanError {
    DeviceNotFound,
    OutOfMemory,
    AllocationFailed,
    SubmissionFailed,
    TimeoutError,
    DeviceLost,
}

impl From<vk::Result> for VulkanError {
    fn from(result: vk::Result) -> Self {
        match result {
            vk::Result::SUCCESS => /* ok */,
            vk::Result::ERROR_OUT_OF_HOST_MEMORY => VulkanError::OutOfMemory,
            vk::Result::ERROR_OUT_OF_DEVICE_MEMORY => VulkanError::OutOfMemory,
            vk::Result::ERROR_DEVICE_LOST => VulkanError::DeviceLost,
            _ => VulkanError::AllocationFailed,
        }
    }
}
```

### 1.6 Python Wrapper (3 hours)

Implement `src/exo/gpu/backends/vulkan_backend.py`:

```python
class VulkanBackend(GPUBackend):
    async def initialize(self) -> None:
        # Load Rust library
        # Call create_instance()
        # Enumerate devices
        # Store device info
    
    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        # Call allocate_buffer()
        # Track memory handle
    
    async def copy_to_device(self, src: bytes, dst_handle: MemoryHandle, offset_bytes: int) -> None:
        # Call copy_host_to_device()
    
    async def copy_from_device(self, src_handle: MemoryHandle, offset_bytes: int, size_bytes: int) -> bytes:
        # Call copy_device_to_host()
    
    async def copy_device_to_device(self, src_handle: MemoryHandle, dst_handle: MemoryHandle, size_bytes: int) -> None:
        # Call copy_device_to_device()
```

### 1.7 Testing (2 hours)

Create unit tests in `tests/vulkan_validation.py`:

```python
class TestVulkanDeviceEnumeration:
    async def test_vulkan_initialization()
    async def test_device_properties()
    async def test_get_device_by_id()

class TestVulkanMemory:
    async def test_memory_allocation()
    async def test_memory_deallocation()
    async def test_memory_info()

class TestVulkanTransfer:
    async def test_copy_to_device()
    async def test_copy_from_device()
    async def test_copy_device_to_device()

class TestVulkanErrors:
    async def test_invalid_device()
    async def test_out_of_memory()
```

## Phase 2: Android Integration (8 hours)

### 2.1 JNI Bridge (4 hours)

**File**: `android/app/src/main/kotlin/io/exo/gpu/VulkanGPUManager.kt`

```kotlin
class VulkanGPUManager {
    companion object {
        init {
            System.loadLibrary("vulkan_bindings")
        }
    }
    
    external fun initializeVulkan(): Boolean
    external fun getDeviceCount(): Int
    external fun getDeviceName(index: Int): String
    external fun allocateMemory(deviceId: Int, sizeBytes: Long): Long
    external fun deallocateMemory(handle: Long): Boolean
    external fun copyToDevice(data: ByteArray, handle: Long): Boolean
    external fun copyFromDevice(handle: Long, sizeBytes: Int): ByteArray
}
```

### 2.2 Gradle Integration (3 hours)

Configure Android build system for Vulkan:

```gradle
android {
    compileSdk 33
    
    defaultConfig {
        minSdk 24
        
        externalNativeBuild {
            cmake {
                cppFlags += "-std=c++17"
                arguments += "-DCMAKE_BUILD_TYPE=Release"
                arguments += "-DVULKAN_SDK=/path/to/android-ndk/vulkan"
            }
        }
    }
    
    externalNativeBuild {
        cmake {
            path "CMakeLists.txt"
        }
    }
}

dependencies {
    // Android Vulkan SDK
    implementation "com.google.android.ndk.vulkan:vulkan-headers:1.3.250"
}
```

### 2.3 CMake Configuration (1 hour)

Create `android/app/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.10)
project(VulkanBindings)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Vulkan SDK
find_package(Vulkan REQUIRED)

# Rust library
add_library(vulkan_bindings SHARED IMPORTED)
set_target_properties(vulkan_bindings PROPERTIES
    IMPORTED_LOCATION ${CMAKE_CURRENT_SOURCE_DIR}/../../rust/exo_vulkan_bindings/target/release/libvulkan_bindings.so
)

# JNI bridge
add_library(vulkan_jni SHARED src/vulkan_jni.cpp)
target_link_libraries(vulkan_jni PRIVATE vulkan_bindings Vulkan::Vulkan)

# Platform-specific
if(ANDROID)
    target_link_libraries(vulkan_jni PRIVATE log)
endif()
```

## Phase 3: Optimization (2 hours)

### 3.1 Performance Tuning

- Memory pooling for frequent allocations
- Command buffer reuse
- Pipeline caching
- Transfer optimization

### 3.2 Error Recovery

- Graceful fallback to CPU
- Automatic device reset on error
- Memory leak prevention
- Validation layer support for debugging

## Dependencies

### Rust Crates

```toml
[dependencies]
ash = "0.37"  # Vulkan bindings
libc = "0.2"
thiserror = "1.0"

[dev-dependencies]
tokio = { version = "1.0", features = ["full"] }
```

### System Requirements

- Android NDK r26d or later
- Vulkan 1.0+ SDK
- Target API: Android 24+ (Vulkan support)
- Supported GPUs: Adreno (Qualcomm), Mali (ARM), PowerVR

## Testing Strategy

1. **Unit tests**: Device enumeration, memory ops
2. **Integration tests**: Full pipeline with real transfers
3. **Emulator tests**: Android emulator with Vulkan support
4. **Device tests**: Real Android phones with supported GPUs

## Known Limitations & Mitigations

| Limitation | Impact | Mitigation |
|:---|:---|:---|
| Vulkan not on all devices | 5-10% of Android devices | CPU fallback, graceful degradation |
| JNI overhead | 1-5% performance hit | Batch operations, reduce JNI calls |
| Memory fragmentation | Long-term stability | Memory pooling, periodic defrag |
| Validation overhead | Debug performance | Disable validation in release builds |

## References

- [Vulkan Tutorial](https://vulkan-tutorial.com/)
- [Ash Crate Docs](https://docs.rs/ash/latest/ash/)
- [Android Vulkan Support](https://developer.android.com/games/vulkan)
- [JNI Specification](https://docs.oracle.com/javase/21/docs/specs/jni/)

## Timeline

- **Week 1**: Rust FFI + Device enumeration
- **Week 2**: Memory management + Python wrapper
- **Week 3**: Android JNI bridge
- **Week 4**: Testing + optimization

**Total**: 16-24 hours of focused development
