//! Vulkan GPU backend for Android and cross-platform GPU compute
//! 
//! This module provides raw Vulkan FFI bindings for device detection and compute operations.
//! It handles device enumeration, memory management, and command buffer submission.

pub mod command;
pub mod memory;
pub mod transfer;

use ash::vk;
use parking_lot::Mutex;
use std::sync::Arc;
use thiserror::Error;
use uuid::Uuid;

/// Vulkan backend errors
#[derive(Error, Debug)]
pub enum VulkanError {
    #[error("Vulkan initialization failed: {0}")]
    InitializationFailed(String),
    
    #[error("Device not found: {0}")]
    DeviceNotFound(String),
    
    #[error("Memory allocation failed: {0}")]
    AllocationFailed(String),
    
    #[error("Memory copy failed: {0}")]
    CopyFailed(String),
    
    #[error("Vulkan API error: {0:?}")]
    VulkanError(vk::Result),
    
    #[error("Invalid operation: {0}")]
    InvalidOperation(String),
}

/// Result type for Vulkan operations
pub type VulkanResult<T> = Result<T, VulkanError>;

/// Device information returned by Vulkan enumeration
#[derive(Clone, Debug)]
pub struct DeviceInfo {
    pub device_id: String,
    pub name: String,
    pub vendor: String,
    pub driver_version: String,
    pub compute_units: u32,
    pub total_memory_bytes: u64,
    pub bandwidth_gbps: f32,
}

/// Global Vulkan context - initialized once per process
pub struct VulkanContext {
    #[allow(dead_code)]
    entry: Arc<ash::Entry>,
    instance: Arc<ash::Instance>,
    physical_devices: Vec<vk::PhysicalDevice>,
    device_properties: Vec<vk::PhysicalDeviceProperties>,
    device_memory_properties: Vec<vk::PhysicalDeviceMemoryProperties>,
}

impl VulkanContext {
    /// Initialize Vulkan and enumerate devices
    pub fn new() -> VulkanResult<Self> {
        unsafe {
            let entry = ash::Entry::load()
                .map_err(|e| VulkanError::InitializationFailed(e.to_string()))?;

            let app_info = vk::ApplicationInfo::default()
                .application_name(c"exo")
                .engine_name(c"exo")
                .api_version(vk::make_api_version(0, 1, 1, 0));

            let create_info = vk::InstanceCreateInfo::default()
                .application_info(&app_info);

            let instance = entry
                .create_instance(&create_info, None)
                .map_err(|e| VulkanError::VulkanError(e))?;

            let physical_devices = instance
                .enumerate_physical_devices()
                .map_err(|e| VulkanError::VulkanError(e))?;

            let device_properties: Vec<_> = physical_devices
                .iter()
                .map(|&pd| instance.get_physical_device_properties(pd))
                .collect();

            let device_memory_properties: Vec<_> = physical_devices
                .iter()
                .map(|&pd| instance.get_physical_device_memory_properties(pd))
                .collect();

            Ok(VulkanContext {
                entry: Arc::new(entry),
                instance: Arc::new(instance),
                physical_devices,
                device_properties,
                device_memory_properties,
            })
        }
    }

    /// Get list of all available GPU devices
    pub fn enumerate_devices(&self) -> VulkanResult<Vec<DeviceInfo>> {
        let mut devices = Vec::new();

        for (idx, &_physical_device) in self.physical_devices.iter().enumerate() {
            let props = &self.device_properties[idx];

            // SAFETY: device_properties is managed and valid
            let device_name = unsafe {
                std::ffi::CStr::from_ptr(props.device_name.as_ptr() as *const std::ffi::c_char)
                    .to_string_lossy()
                    .into_owned()
            };

            let vendor_name = match props.vendor_id {
                0x10DE => "NVIDIA",
                0x1002 => "AMD",
                0x106B => "Apple",
                0x8086 => "Intel",
                0x13B5 => "ARM",
                _ => "Unknown",
            };

            // TODO: Get actual compute units from device properties
            let compute_units = 16; // Default estimate

            // Get total memory
            let mem_props = &self.device_memory_properties[idx];
            let total_memory_bytes = mem_props.memory_heaps[0].size;

            let device_id = Uuid::new_v4().to_string();

            devices.push(DeviceInfo {
                device_id,
                name: device_name,
                vendor: vendor_name.to_string(),
                driver_version: format!("{}", props.driver_version),
                compute_units,
                total_memory_bytes,
                bandwidth_gbps: 32.0, // TODO: Query actual bandwidth
            });
        }

        Ok(devices)
    }

    /// Get a specific device by index
    pub fn get_physical_device(&self, index: usize) -> VulkanResult<vk::PhysicalDevice> {
        self.physical_devices
            .get(index)
            .copied()
            .ok_or_else(|| VulkanError::DeviceNotFound(format!("Device {} not found", index)))
    }

    /// Get device properties
    pub fn get_device_properties(&self, index: usize) -> VulkanResult<&vk::PhysicalDeviceProperties> {
        self.device_properties
            .get(index)
            .ok_or_else(|| VulkanError::DeviceNotFound(format!("Device {} not found", index)))
    }

    /// Get memory properties for a device
    pub fn get_memory_properties(&self, index: usize) -> VulkanResult<&vk::PhysicalDeviceMemoryProperties> {
        self.device_memory_properties
            .get(index)
            .ok_or_else(|| VulkanError::DeviceNotFound(format!("Device {} not found", index)))
    }

    /// Get the instance handle (for advanced operations)
    pub fn instance(&self) -> Arc<ash::Instance> {
        Arc::clone(&self.instance)
    }
}

impl Drop for VulkanContext {
    fn drop(&mut self) {
        unsafe {
            self.instance.destroy_instance(None);
        }
    }
}

lazy_static::lazy_static! {
    /// Global Vulkan context singleton
    static ref VULKAN_CONTEXT: Mutex<Option<Arc<VulkanContext>>> = Mutex::new(None);
}

/// Initialize Vulkan globally (call once)
pub fn initialize_vulkan() -> VulkanResult<Arc<VulkanContext>> {
    let mut ctx = VULKAN_CONTEXT.lock();
    
    if let Some(ref context) = *ctx {
        return Ok(Arc::clone(context));
    }

    let context = Arc::new(VulkanContext::new()?);
    *ctx = Some(Arc::clone(&context));
    Ok(context)
}

/// Get the global Vulkan context if initialized
pub fn get_vulkan_context() -> VulkanResult<Arc<VulkanContext>> {
    let ctx = VULKAN_CONTEXT.lock();
    ctx.as_ref()
        .cloned()
        .ok_or_else(|| VulkanError::InitializationFailed("Vulkan not initialized".to_string()))
}

/// Enumerate Vulkan devices as JSON-serializable info
pub fn enumerate_vulkan_devices() -> VulkanResult<Vec<DeviceInfo>> {
    let context = initialize_vulkan()?;
    context.enumerate_devices()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_initialize_vulkan() {
        // This may fail if Vulkan is not available
        let result = initialize_vulkan();
        // Don't assert success, as Vulkan may not be available in test env
        let _ = result;
    }

    #[test]
    fn test_get_context_before_init() {
        // Context should fail if not initialized
        // Note: This test depends on test execution order
        let _ = VULKAN_CONTEXT.lock().take(); // Reset for testing
        let result = get_vulkan_context();
        assert!(result.is_err());
    }
}
