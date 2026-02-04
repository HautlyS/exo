//! Vulkan memory management subsystem
//!
//! Provides safe abstractions over Vulkan device memory allocation, mapping, and deallocation.
//! All unsafe operations are documented with SAFETY comments explaining invariants.

use ash::vk;
use thiserror::Error;

/// Memory-related errors
#[derive(Error, Debug)]
pub enum MemoryError {
    #[error("Memory allocation failed: {0}")]
    AllocationFailed(String),

    #[error("Memory not found: {0}")]
    NotFound(String),

    #[error("Memory mapping failed: {0}")]
    MapFailed(String),

    #[error("Invalid memory type: {0}")]
    InvalidMemoryType(String),

    #[error("Vulkan error: {0:?}")]
    VulkanError(vk::Result),
}

pub type MemoryResult<T> = Result<T, MemoryError>;

/// Information about a single memory allocation
#[derive(Clone, Debug)]
pub struct AllocationInfo {
    pub handle_id: String,
    pub size: u64,
    pub device_memory: vk::DeviceMemory,
    pub buffer: vk::Buffer,
    pub mapped_ptr: Option<*mut u8>,
}

/// Manages Vulkan device memory allocations
pub struct MemoryAllocator {
    device: ash::Device,
    physical_device_memory_properties: vk::PhysicalDeviceMemoryProperties,
    allocations: std::collections::HashMap<String, AllocationInfo>,
}

impl MemoryAllocator {
    /// Create a new memory allocator for a device
    ///
    /// # Arguments
    /// * `device` - Ash device handle (must be valid for lifetime of allocator)
    /// * `memory_properties` - Physical device memory properties (queried at creation)
    pub fn new(
        device: ash::Device,
        memory_properties: vk::PhysicalDeviceMemoryProperties,
    ) -> Self {
        Self {
            device,
            physical_device_memory_properties: memory_properties,
            allocations: std::collections::HashMap::new(),
        }
    }

    /// Allocate device memory with a backing buffer
    ///
    /// Creates a buffer and allocates device memory for it.
    ///
    /// # Safety Requirements
    /// - device handle must be valid and not destroyed during lifetime of returned allocation
    /// - size must be > 0 and <= device memory limits
    /// - memory_type_index must be valid for the device (see memory_properties)
    ///
    /// # Arguments
    /// * `size` - Number of bytes to allocate
    /// * `memory_type_index` - Memory type index (from device capabilities)
    /// * `handle_id` - Unique identifier for this allocation
    ///
    /// # Returns
    /// Handle ID for future reference to this allocation
    pub fn allocate(
        &mut self,
        size: u64,
        memory_type_index: u32,
        handle_id: String,
    ) -> MemoryResult<String> {
        // Validate inputs
        if size == 0 {
            return Err(MemoryError::AllocationFailed(
                "size must be > 0".to_string(),
            ));
        }

        if memory_type_index
            >= self.physical_device_memory_properties.memory_type_count
        {
            return Err(MemoryError::InvalidMemoryType(format!(
                "memory_type_index {} >= memory type count {}",
                memory_type_index,
                self.physical_device_memory_properties.memory_type_count
            )));
        }

        unsafe {
            // Create buffer object
            // SAFETY:
            //   - device is valid (guaranteed by contract)
            //   - vk::BufferCreateInfo::default() is a safe default
            //   - size is validated above
            let buffer_info = vk::BufferCreateInfo::default()
                .size(size)
                .usage(
                    vk::BufferUsageFlags::TRANSFER_DST
                        | vk::BufferUsageFlags::TRANSFER_SRC
                        | vk::BufferUsageFlags::STORAGE_BUFFER,
                )
                .sharing_mode(vk::SharingMode::EXCLUSIVE);

            let buffer = self
                .device
                .create_buffer(&buffer_info, None)
                .map_err(|e| {
                    MemoryError::VulkanError(e)
                })?;

            // Get memory requirements for buffer
            // SAFETY:
            //   - buffer is valid (just created)
            //   - device is valid
            let mem_requirements = self.device.get_buffer_memory_requirements(buffer);

            // Validate memory type is compatible
            let memory_type = &self.physical_device_memory_properties
                .memory_types[memory_type_index as usize];

            if !matches_memory_requirements(
                mem_requirements,
                memory_type.property_flags,
                memory_type_index,
            ) {
                // Memory type doesn't match requirements, find compatible type
                let compatible_index = self
                    .find_compatible_memory_type(mem_requirements.memory_type_bits)?;
                return self.allocate(size, compatible_index, handle_id);
            }

            // Allocate device memory
            // SAFETY:
            //   - device is valid
            //   - memory_type_index is validated
            //   - size is validated
            let alloc_info = vk::MemoryAllocateInfo::default()
                .allocation_size(mem_requirements.size)
                .memory_type_index(memory_type_index);

            let device_memory = self
                .device
                .allocate_memory(&alloc_info, None)
                .map_err(|e| {
                    // Clean up buffer on allocation failure
                    unsafe {
                        self.device.destroy_buffer(buffer, None);
                    }
                    MemoryError::VulkanError(e)
                })?;

            // Bind buffer to memory
            // SAFETY:
            //   - device is valid
            //   - buffer is valid
            //   - device_memory is valid and allocated
            //   - offset 0 is valid for any allocation
            self.device
                .bind_buffer_memory(buffer, device_memory, 0)
                .map_err(|e| {
                    // Clean up on bind failure
                    unsafe {
                        self.device.free_memory(device_memory, None);
                        self.device.destroy_buffer(buffer, None);
                    }
                    MemoryError::VulkanError(e)
                })?;

            let allocation = AllocationInfo {
                handle_id: handle_id.clone(),
                size,
                device_memory,
                buffer,
                mapped_ptr: None,
            };

            self.allocations.insert(handle_id.clone(), allocation);

            Ok(handle_id)
        }
    }

    /// Map device memory to host address space
    ///
    /// # Safety Requirements
    /// - handle_id must refer to valid, previously allocated memory
    /// - returned pointer is valid only until unmapped
    /// - memory must be HOST_VISIBLE
    ///
    /// # Arguments
    /// * `handle_id` - Allocation handle
    ///
    /// # Returns
    /// Mapped pointer to device memory in host space
    pub fn map(&mut self, handle_id: &str) -> MemoryResult<*mut u8> {
        let allocation = self
            .allocations
            .get_mut(handle_id)
            .ok_or_else(|| MemoryError::NotFound(handle_id.to_string()))?;

        if let Some(ptr) = allocation.mapped_ptr {
            // Already mapped
            return Ok(ptr);
        }

        unsafe {
            // Map memory to host address space
            // SAFETY:
            //   - device_memory is valid (from allocation)
            //   - offset 0 and size are valid for this allocation
            //   - device is valid
            let ptr = self
                .device
                .map_memory(
                    allocation.device_memory,
                    0,
                    vk::WHOLE_SIZE,
                    vk::MemoryMapFlags::empty(),
                )
                .map_err(MemoryError::VulkanError)? as *mut u8;

            allocation.mapped_ptr = Some(ptr);
            Ok(ptr)
        }
    }

    /// Unmap device memory from host address space
    ///
    /// # Arguments
    /// * `handle_id` - Allocation handle
    pub fn unmap(&mut self, handle_id: &str) -> MemoryResult<()> {
        let allocation = self
            .allocations
            .get_mut(handle_id)
            .ok_or_else(|| MemoryError::NotFound(handle_id.to_string()))?;

        if allocation.mapped_ptr.is_some() {
            unsafe {
                // Unmap memory
                // SAFETY:
                //   - device_memory is valid
                //   - device is valid
                //   - we previously successfully mapped this memory
                self.device.unmap_memory(allocation.device_memory);
            }
            allocation.mapped_ptr = None;
        }

        Ok(())
    }

    /// Deallocate device memory
    ///
    /// # Arguments
    /// * `handle_id` - Allocation handle
    pub fn deallocate(&mut self, handle_id: &str) -> MemoryResult<()> {
        let allocation = self
            .allocations
            .remove(handle_id)
            .ok_or_else(|| MemoryError::NotFound(handle_id.to_string()))?;

        // Unmap if still mapped
        if allocation.mapped_ptr.is_some() {
            unsafe {
                self.device.unmap_memory(allocation.device_memory);
            }
        }

        unsafe {
            // Clean up buffer and memory
            // SAFETY:
            //   - Both resources are valid (from allocation)
            //   - device is valid
            //   - they haven't been destroyed yet
            self.device.destroy_buffer(allocation.buffer, None);
            self.device.free_memory(allocation.device_memory, None);
        }

        Ok(())
    }

    /// Get allocation info
    pub fn get_allocation(&self, handle_id: &str) -> MemoryResult<&AllocationInfo> {
        self.allocations
            .get(handle_id)
            .ok_or_else(|| MemoryError::NotFound(handle_id.to_string()))
    }

    /// Get mutable allocation info
    pub fn get_allocation_mut(
        &mut self,
        handle_id: &str,
    ) -> MemoryResult<&mut AllocationInfo> {
        self.allocations
            .get_mut(handle_id)
            .ok_or_else(|| MemoryError::NotFound(handle_id.to_string()))
    }

    /// Find a compatible memory type for given requirements
    fn find_compatible_memory_type(&self, type_bits: u32) -> MemoryResult<u32> {
        for (i, memory_type) in self.physical_device_memory_properties.memory_types
            [..self.physical_device_memory_properties.memory_type_count as usize]
            .iter()
            .enumerate()
        {
            if (type_bits & (1 << i)) != 0 {
                return Ok(i as u32);
            }
        }
        Err(MemoryError::InvalidMemoryType(
            "No compatible memory type found".to_string(),
        ))
    }
}

/// Check if memory type matches buffer requirements
fn matches_memory_requirements(
    requirements: vk::MemoryRequirements,
    property_flags: vk::MemoryPropertyFlags,
    type_index: u32,
) -> bool {
    // Check if this memory type is in the compatible types for the buffer
    (requirements.memory_type_bits & (1 << type_index)) != 0
        && property_flags.contains(vk::MemoryPropertyFlags::HOST_VISIBLE)
}

impl Drop for MemoryAllocator {
    fn drop(&mut self) {
        // Clean up all remaining allocations
        let handles: Vec<_> = self.allocations.keys().cloned().collect();
        for handle in handles {
            let _ = self.deallocate(&handle);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_error_display() {
        let err = MemoryError::AllocationFailed("test".to_string());
        assert!(err.to_string().contains("test"));
    }
}
