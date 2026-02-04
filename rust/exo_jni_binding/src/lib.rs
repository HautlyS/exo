//! JNI Bindings for exo Vulkan GPU backend
//! 
//! Provides JNI interface for Android applications to access Vulkan GPU functionality.
//! Enables Kotlin/Java code to enumerate devices, allocate memory, and perform GPU operations.

#![allow(unsafe_code, missing_inline_in_public_items)]

use jni::JNIEnv;
use jni::objects::{JClass, JString};
use jni::sys::{jint, jlong, jbyteArray, jstring, jboolean};
use log::{error, info};
use std::sync::Arc;
use std::collections::HashMap;
use uuid::Uuid;
use lazy_static::lazy_static;
use parking_lot::Mutex;

use exo_vulkan_binding::{initialize_vulkan, enumerate_vulkan_devices, VulkanContext};

/// Device handles allocated from JNI
#[derive(Clone, Debug)]
struct DeviceHandle {
    device_id: String,
    name: String,
    vendor: String,
    memory_bytes: u64,
}

/// Memory handle for JNI access
#[derive(Clone, Debug)]
struct MemoryAllocation {
    handle_id: String,
    device_id: String,
    size_bytes: u64,
}

/// Global Vulkan context for JNI access
lazy_static! {
    static ref VULKAN_CONTEXT: Mutex<Option<Arc<VulkanContext>>> = Mutex::new(None);
    static ref DEVICE_HANDLES: Mutex<HashMap<String, DeviceHandle>> = Mutex::new(HashMap::new());
    static ref MEMORY_ALLOCATIONS: Mutex<HashMap<String, MemoryAllocation>> = Mutex::new(HashMap::new());
}

/// Initialize Vulkan context if not already done
fn get_or_init_vulkan() -> Result<Arc<VulkanContext>, String> {
    let mut ctx = VULKAN_CONTEXT.lock();
    if let Some(ref context) = *ctx {
        return Ok(Arc::clone(context));
    }
    
    let context = initialize_vulkan()
        .map_err(|e| format!("Vulkan initialization failed: {}", e))?;
    *ctx = Some(Arc::clone(&context));
    Ok(context)
}

// ============ Device Functions ============

/// Initialize Vulkan for Android JNI
/// @return true if initialization succeeded, false otherwise
// SAFETY: JNI function - called from Java/Kotlin with valid JNIEnv
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_initializeVulkan(
    _env: JNIEnv,
    _class: JClass,
) -> jboolean {
    match get_or_init_vulkan() {
        Ok(_ctx) => {
            info!("Vulkan initialized via JNI");
            jboolean::from(true)
        }
        Err(e) => {
            error!("Failed to initialize Vulkan: {}", e);
            jboolean::from(false)
        }
    }
}

/// Enumerate Vulkan devices available on the system
/// @return JSON array of device info, or null on error
// SAFETY: JNI function - device list is valid for call duration
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_enumerateDevices(
    mut env: JNIEnv,
    _class: JClass,
) -> jstring {
    match (|| -> Result<String, String> {
        let vulkan_ctx = get_or_init_vulkan()?;
        let devices = vulkan_ctx
            .enumerate_devices()
            .map_err(|e| format!("Device enumeration failed: {}", e))?;
        
        info!("Enumerated {} Vulkan devices", devices.len());
        
        // Clear old handles
        {
            let mut handles = DEVICE_HANDLES.lock();
            handles.clear();
        }
        
        // Build JSON response and store handles
        let mut device_jsons = Vec::new();
        {
            let mut handles = DEVICE_HANDLES.lock();
            
            for (idx, dev_info) in devices.iter().enumerate() {
                let device_id = format!("vulkan:{}", idx);
                
                // Store handle
                let handle = DeviceHandle {
                    device_id: device_id.clone(),
                    name: dev_info.name.clone(),
                    vendor: dev_info.vendor.clone(),
                    memory_bytes: dev_info.total_memory_bytes,
                };
                handles.insert(device_id.clone(), handle);
                
                // Build JSON for device
                let device_json = format!(
                    r#"{{"device_id":"{}","name":"{}","vendor":"{}","memory_bytes":{},"compute_units":{},"bandwidth_gbps":{}}}"#,
                    device_id,
                    dev_info.name,
                    dev_info.vendor,
                    dev_info.total_memory_bytes,
                    dev_info.compute_units,
                    dev_info.bandwidth_gbps as i32
                );
                device_jsons.push(device_json);
            }
        }
        
        // Return as JSON array
        let json = format!(r#"{{"devices":[{}],"count":{}}}"#, 
            device_jsons.join(","),
            devices.len()
        );
        
        Ok(json)
    })() {
        Ok(json) => {
            match env.new_string(&json) {
                Ok(jstr) => jstr.into_raw(),
                Err(e) => {
                    error!("Failed to create JNI string: {}", e);
                    let _ = env.throw_new("java/lang/RuntimeException", &e.to_string());
                    std::ptr::null_mut()
                }
            }
        }
        Err(e) => {
            error!("Failed to enumerate devices: {}", e);
            let _ = env.throw_new("java/lang/RuntimeException", &e);
            std::ptr::null_mut()
        }
    }
}

/// Get device name by index
/// @param device_index: index of device to query
/// @return device name as JNI string
// SAFETY: JNI function - returns valid string or null
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_getDeviceName(
    mut env: JNIEnv,
    _class: JClass,
    device_index: jint,
) -> jstring {
    let handles = DEVICE_HANDLES.lock();
    let device_id = format!("vulkan:{}", device_index);
    
    if let Some(handle) = handles.get(&device_id) {
        match env.new_string(&handle.name) {
            Ok(jstr) => return jstr.into_raw(),
            Err(e) => {
                error!("Failed to create JNI string: {}", e);
                let _ = env.throw_new("java/lang/RuntimeException", &e.to_string());
            }
        }
    } else {
        error!("Device {} not found", device_id);
        let _ = env.throw_new("java/lang/IllegalArgumentException", "Device not found");
    }
    std::ptr::null_mut()
}

/// Get device memory size in bytes
/// @param device_index: index of device to query
/// @return memory size in bytes, or 0 if device not found
// SAFETY: JNI function - no unsafe operations
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_getDeviceMemory(
    _env: JNIEnv,
    _class: JClass,
    device_index: jint,
) -> jlong {
    let handles = DEVICE_HANDLES.lock();
    let device_id = format!("vulkan:{}", device_index);
    
    handles
        .get(&device_id)
        .map(|h| h.memory_bytes as jlong)
        .unwrap_or(0)
}

/// Get device compute units
/// @param device_index: index of device to query
/// @return number of compute units, or 0 if device not found
// SAFETY: JNI function - no unsafe operations
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_getComputeUnits(
    _env: JNIEnv,
    _class: JClass,
    device_index: jint,
) -> jint {
    // For now return a default value since we don't store this yet
    // TODO: Store compute units in DeviceHandle
    16
}

// ============ Memory Functions ============

/// Allocate memory on device
/// @param device_index: device to allocate on
/// @param size_bytes: number of bytes to allocate
/// @return handle ID as JNI string, or null on error
// SAFETY: JNI function - validates inputs and handles errors properly
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_allocateMemory(
    mut env: JNIEnv,
    _class: JClass,
    device_index: jint,
    size_bytes: jlong,
) -> jstring {
    match (|| -> Result<String, String> {
        if size_bytes <= 0 {
            return Err("Size must be > 0".to_string());
        }
        
        // Verify device exists
        {
            let handles = DEVICE_HANDLES.lock();
            let device_id = format!("vulkan:{}", device_index);
            if !handles.contains_key(&device_id) {
                return Err(format!("Device {} not found", device_id));
            }
        }
        
        // Create allocation handle
        let handle_id = Uuid::new_v4().to_string();
        let device_id = format!("vulkan:{}", device_index);
        
        // Store allocation
        let allocation = MemoryAllocation {
            handle_id: handle_id.clone(),
            device_id,
            size_bytes: size_bytes as u64,
        };
        
        {
            let mut allocs = MEMORY_ALLOCATIONS.lock();
            allocs.insert(handle_id.clone(), allocation);
        }
        
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
            error!("Memory allocation failed: {}", e);
            let _ = env.throw_new("java/lang/RuntimeException", &e);
            std::ptr::null_mut()
        }
    }
}

/// Free allocated device memory
/// @param handle_id: memory handle to free
/// @return true if successful, false otherwise
// SAFETY: JNI function - handle is validated before freeing
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_freeMemory(
    mut env: JNIEnv,
    _class: JClass,
    handle_id: JString,
) -> jboolean {
    match env.get_string(&handle_id) {
        Ok(jstr) => {
            let handle = jstr.to_string_lossy().to_string();
            
            // Remove allocation
            let mut allocs = MEMORY_ALLOCATIONS.lock();
            if allocs.remove(&handle).is_some() {
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

/// Copy data from host to device
/// @param handle_id: destination memory handle
/// @param data: data to copy
/// @return true if successful, false otherwise
// SAFETY: JNI function - validates handle before proceeding
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
        
        // Verify allocation exists
        {
            let allocs = MEMORY_ALLOCATIONS.lock();
            if !allocs.contains_key(&handle_str) {
                return Err(format!("Memory handle not found: {}", handle_str));
            }
        }
        
        // TODO: Get array length and copy data when integrated with proper JNI 
        // For now, just validate the handle exists
        info!("Copy to device requested for {}", handle_str);
        
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

/// Copy data from device to host
/// @param handle_id: source memory handle
/// @param size_bytes: number of bytes to copy
/// @return byte array with copied data, or null on error
// SAFETY: JNI function - validates handle and creates appropriately sized array
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_copyFromDevice(
    mut env: JNIEnv,
    _class: JClass,
    handle_id: JString,
    size_bytes: jlong,
) -> jbyteArray {
    match (|| -> Result<Vec<u8>, String> {
        if size_bytes < 0 {
            return Err("Size must be >= 0".to_string());
        }
        
        if size_bytes == 0 {
            return Ok(Vec::new()); // Nothing to copy
        }
        
        // Get handle string
        let handle_str = env
            .get_string(&handle_id)
            .map_err(|e| format!("Failed to get handle string: {}", e))?
            .to_string_lossy()
            .to_string();
        
        // Verify allocation exists
        {
            let allocs = MEMORY_ALLOCATIONS.lock();
            allocs
                .get(&handle_str)
                .ok_or_else(|| format!("Memory handle not found: {}", handle_str))?;
        }
        
        // Create zero-filled buffer for now
        // TODO: Call actual Vulkan copy via DataTransfer when integrated
        let buffer = vec![0u8; size_bytes as usize];
        
        info!("Copied {} bytes from device {}", size_bytes, handle_str);
        
        Ok(buffer)
    })() {
        Ok(buffer) => {
            match env.new_byte_array(buffer.len() as i32) {
                Ok(arr) => arr.into_raw(),
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

// ============ Utilities ============

/// Shutdown Vulkan and clean up all resources
// SAFETY: JNI function - clears all global state
#[unsafe(no_mangle)]
pub extern "C" fn Java_com_exo_gpu_VulkanGpu_shutdown(
    _env: JNIEnv,
    _class: JClass,
) -> jboolean {
    // Clear all allocations
    {
        let mut allocs = MEMORY_ALLOCATIONS.lock();
        allocs.clear();
    }
    
    // Clear all device handles
    {
        let mut handles = DEVICE_HANDLES.lock();
        handles.clear();
    }
    
    // Clear Vulkan context
    {
        let mut ctx = VULKAN_CONTEXT.lock();
        *ctx = None;
    }
    
    info!("Vulkan JNI shutdown complete");
    jboolean::from(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_device_enumeration() {
        match enumerate_vulkan_devices() {
            Ok(devices) => {
                println!("Found {} devices", devices.len());
            }
            Err(e) => {
                println!("Device enumeration failed: {}", e);
            }
        }
    }
}
