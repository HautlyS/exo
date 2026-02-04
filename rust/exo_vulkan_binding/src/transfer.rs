//! Vulkan data transfer operations
//!
//! Provides host ↔ device and device ↔ device data copying with proper synchronization.

use ash::vk;
use thiserror::Error;

use crate::memory::AllocationInfo;

/// Transfer-related errors
#[derive(Error, Debug)]
pub enum TransferError {
    #[error("Copy failed: {0}")]
    CopyFailed(String),

    #[error("Staging buffer failed: {0}")]
    StagingFailed(String),

    #[error("Synchronization failed: {0}")]
    SynchronizationFailed(String),

    #[error("Invalid size: {0}")]
    InvalidSize(String),

    #[error("Vulkan error: {0:?}")]
    VulkanError(vk::Result),
}

pub type TransferResult<T> = Result<T, TransferError>;

/// Manages buffer-to-buffer copy operations
pub struct DataTransfer {
    device: ash::Device,
    queue: vk::Queue,
    command_pool: vk::CommandPool,
}

impl DataTransfer {
    /// Create a new data transfer manager
    ///
    /// # Safety Requirements
    /// - device must be valid
    /// - queue must be valid and belong to a compute-capable queue family
    /// - command_pool must be valid and belong to the same queue family
    pub fn new(
        device: ash::Device,
        queue: vk::Queue,
        command_pool: vk::CommandPool,
    ) -> Self {
        DataTransfer {
            device,
            queue,
            command_pool,
        }
    }

    /// Copy data from host to device memory
    ///
    /// Allocates a temporary staging buffer, copies host data to it,
    /// then records commands to transfer to device memory.
    ///
    /// # Arguments
    /// * `host_data` - Data to copy
    /// * `device_allocation` - Destination device allocation
    ///
    /// # Safety Requirements
    /// - host_data must be valid
    /// - device_allocation must be valid and allocated
    /// - device_allocation.buffer must be valid for writes
    pub unsafe fn copy_to_device(
        &self,
        host_data: &[u8],
        device_allocation: &AllocationInfo,
    ) -> TransferResult<()> {
        if host_data.len() as u64 > device_allocation.size {
            return Err(TransferError::InvalidSize(format!(
                "host data size {} > device allocation size {}",
                host_data.len(),
                device_allocation.size
            )));
        }

        if host_data.is_empty() {
            return Ok(()); // Nothing to copy
        }

        // Create staging buffer for upload
        // SAFETY:
        //   - device is valid (from self)
        //   - sizes are valid
        let staging_buffer_info = vk::BufferCreateInfo::default()
            .size(host_data.len() as u64)
            .usage(vk::BufferUsageFlags::TRANSFER_SRC)
            .sharing_mode(vk::SharingMode::EXCLUSIVE);

        let staging_buffer = self
            .device
            .create_buffer(&staging_buffer_info, None)
            .map_err(|e| TransferError::VulkanError(e))?;

        // Get memory requirements for staging buffer
        // SAFETY:
        //   - staging_buffer is valid (just created)
        let staging_mem_requirements = self
            .device
            .get_buffer_memory_requirements(staging_buffer);

        // Allocate HOST_VISIBLE memory for staging
        // Note: In real implementation, this would use the allocator
        // For now, we document the requirement
        let staging_memory_info = vk::MemoryAllocateInfo::default()
            .allocation_size(staging_mem_requirements.size)
            .memory_type_index(0); // Would be found by type filter

        let staging_memory = match self.device.allocate_memory(&staging_memory_info, None) {
            Ok(mem) => mem,
            Err(e) => {
                self.device.destroy_buffer(staging_buffer, None);
                return Err(TransferError::VulkanError(e));
            }
        };

        // Bind staging buffer to memory
        if let Err(e) = self
            .device
            .bind_buffer_memory(staging_buffer, staging_memory, 0)
        {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        // Map staging memory and copy data
        // SAFETY:
        //   - staging_memory is valid and allocated
        //   - host_data is valid
        match self.device.map_memory(
            staging_memory,
            0,
            vk::WHOLE_SIZE,
            vk::MemoryMapFlags::empty(),
        ) {
            Ok(ptr) => {
                // Copy host data to staging buffer
                std::ptr::copy_nonoverlapping(
                    host_data.as_ptr(),
                    ptr as *mut u8,
                    host_data.len(),
                );
                self.device.unmap_memory(staging_memory);
            }
            Err(e) => {
                self.device.destroy_buffer(staging_buffer, None);
                self.device.free_memory(staging_memory, None);
                return Err(TransferError::VulkanError(e));
            }
        }

        // Allocate and record copy command
        let alloc_info = vk::CommandBufferAllocateInfo::default()
            .command_pool(self.command_pool)
            .level(vk::CommandBufferLevel::PRIMARY)
            .command_buffer_count(1);

        let cmd_buffers = match self.device.allocate_command_buffers(&alloc_info) {
            Ok(bufs) => bufs,
            Err(e) => {
                self.device.destroy_buffer(staging_buffer, None);
                self.device.free_memory(staging_memory, None);
                return Err(TransferError::VulkanError(e));
            }
        };

        let cmd_buffer = cmd_buffers[0];

        // Record copy command
        // SAFETY:
        //   - cmd_buffer is valid (just allocated)
        //   - staging_buffer and device_allocation.buffer are valid
        let begin_info = vk::CommandBufferBeginInfo::default()
            .flags(vk::CommandBufferUsageFlags::ONE_TIME_SUBMIT);

        if let Err(e) = self.device.begin_command_buffer(cmd_buffer, &begin_info) {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        // Record copy region
        let region = vk::BufferCopy::default()
            .src_offset(0)
            .dst_offset(0)
            .size(host_data.len() as u64);

        self.device.cmd_copy_buffer(
            cmd_buffer,
            staging_buffer,
            device_allocation.buffer,
            &[region],
        );

        // Record pipeline barrier for device access
        let memory_barrier = vk::MemoryBarrier::default()
            .src_access_mask(vk::AccessFlags::TRANSFER_WRITE)
            .dst_access_mask(vk::AccessFlags::SHADER_READ);

        self.device.cmd_pipeline_barrier(
            cmd_buffer,
            vk::PipelineStageFlags::TRANSFER,
            vk::PipelineStageFlags::COMPUTE_SHADER,
            vk::DependencyFlags::empty(),
            &[memory_barrier],
            &[],
            &[],
        );

        // End recording
        if let Err(e) = self.device.end_command_buffer(cmd_buffer) {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        // Submit and wait
        // SAFETY:
        //   - cmd_buffer is valid and properly recorded
        //   - queue is valid
        let cmd_buffers = [cmd_buffer];
        let submit_info = vk::SubmitInfo::default().command_buffers(&cmd_buffers);

        if let Err(e) = self.device.queue_submit(self.queue, &[submit_info], vk::Fence::null()) {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        // Wait for completion
        if let Err(e) = self.device.queue_wait_idle(self.queue) {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        // Clean up temporary resources
        self.device.destroy_buffer(staging_buffer, None);
        self.device.free_memory(staging_memory, None);

        Ok(())
    }

    /// Copy data from device to host memory
    ///
    /// Records commands to copy from device to temporary staging buffer,
    /// then maps and copies to host memory.
    ///
    /// # Arguments
    /// * `device_allocation` - Source device allocation
    /// * `size` - Number of bytes to copy
    ///
    /// # Returns
    /// Copied data as Vec<u8>
    ///
    /// # Safety Requirements
    /// - device_allocation must be valid and readable
    /// - size must be <= device_allocation.size
    pub unsafe fn copy_from_device(
        &self,
        device_allocation: &AllocationInfo,
        size: u64,
    ) -> TransferResult<Vec<u8>> {
        if size > device_allocation.size {
            return Err(TransferError::InvalidSize(format!(
                "copy size {} > device allocation size {}",
                size, device_allocation.size
            )));
        }

        if size == 0 {
            return Ok(Vec::new());
        }

        // Create staging buffer for download
        // SAFETY:
        //   - device is valid
        let staging_buffer_info = vk::BufferCreateInfo::default()
            .size(size)
            .usage(vk::BufferUsageFlags::TRANSFER_DST)
            .sharing_mode(vk::SharingMode::EXCLUSIVE);

        let staging_buffer = self
            .device
            .create_buffer(&staging_buffer_info, None)
            .map_err(|e| TransferError::VulkanError(e))?;

        // Get memory requirements
        let staging_mem_requirements = self
            .device
            .get_buffer_memory_requirements(staging_buffer);

        // Allocate HOST_VISIBLE memory
        let staging_memory_info = vk::MemoryAllocateInfo::default()
            .allocation_size(staging_mem_requirements.size)
            .memory_type_index(0);

        let staging_memory = match self.device.allocate_memory(&staging_memory_info, None) {
            Ok(mem) => mem,
            Err(e) => {
                self.device.destroy_buffer(staging_buffer, None);
                return Err(TransferError::VulkanError(e));
            }
        };

        // Bind staging buffer
        if let Err(e) = self
            .device
            .bind_buffer_memory(staging_buffer, staging_memory, 0)
        {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        // Allocate command buffer for copy
        let alloc_info = vk::CommandBufferAllocateInfo::default()
            .command_pool(self.command_pool)
            .level(vk::CommandBufferLevel::PRIMARY)
            .command_buffer_count(1);

        let cmd_buffers = match self.device.allocate_command_buffers(&alloc_info) {
            Ok(bufs) => bufs,
            Err(e) => {
                self.device.destroy_buffer(staging_buffer, None);
                self.device.free_memory(staging_memory, None);
                return Err(TransferError::VulkanError(e));
            }
        };

        let cmd_buffer = cmd_buffers[0];

        // Record copy command
        let begin_info = vk::CommandBufferBeginInfo::default()
            .flags(vk::CommandBufferUsageFlags::ONE_TIME_SUBMIT);

        if let Err(e) = self.device.begin_command_buffer(cmd_buffer, &begin_info) {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        // Record memory barrier to make device data available
        let memory_barrier = vk::MemoryBarrier::default()
            .src_access_mask(vk::AccessFlags::SHADER_WRITE)
            .dst_access_mask(vk::AccessFlags::TRANSFER_READ);

        self.device.cmd_pipeline_barrier(
            cmd_buffer,
            vk::PipelineStageFlags::COMPUTE_SHADER,
            vk::PipelineStageFlags::TRANSFER,
            vk::DependencyFlags::empty(),
            &[memory_barrier],
            &[],
            &[],
        );

        // Record copy
        let region = vk::BufferCopy::default()
            .src_offset(0)
            .dst_offset(0)
            .size(size);

        self.device.cmd_copy_buffer(
            cmd_buffer,
            device_allocation.buffer,
            staging_buffer,
            &[region],
        );

        // End recording
        if let Err(e) = self.device.end_command_buffer(cmd_buffer) {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        // Submit and wait
        let cmd_buffers = [cmd_buffer];
        let submit_info = vk::SubmitInfo::default().command_buffers(&cmd_buffers);

        if let Err(e) = self.device.queue_submit(self.queue, &[submit_info], vk::Fence::null()) {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        if let Err(e) = self.device.queue_wait_idle(self.queue) {
            self.device.destroy_buffer(staging_buffer, None);
            self.device.free_memory(staging_memory, None);
            return Err(TransferError::VulkanError(e));
        }

        // Map and read data
        match self.device.map_memory(
            staging_memory,
            0,
            vk::WHOLE_SIZE,
            vk::MemoryMapFlags::empty(),
        ) {
            Ok(ptr) => {
                let mut data = vec![0u8; size as usize];
                std::ptr::copy_nonoverlapping(ptr as *const u8, data.as_mut_ptr(), size as usize);
                self.device.unmap_memory(staging_memory);

                // Clean up
                self.device.destroy_buffer(staging_buffer, None);
                self.device.free_memory(staging_memory, None);

                Ok(data)
            }
            Err(e) => {
                self.device.destroy_buffer(staging_buffer, None);
                self.device.free_memory(staging_memory, None);
                Err(TransferError::VulkanError(e))
            }
        }
    }

    /// Copy data directly between device buffers
    ///
    /// # Arguments
    /// * `src` - Source allocation
    /// * `dst` - Destination allocation
    /// * `size` - Bytes to copy
    ///
    /// # Safety Requirements
    /// - Both allocations must be valid and not aliased
    /// - size must be <= both allocation sizes
    pub unsafe fn copy_device_to_device(
        &self,
        src: &AllocationInfo,
        dst: &AllocationInfo,
        size: u64,
    ) -> TransferResult<()> {
        if size > src.size || size > dst.size {
            return Err(TransferError::InvalidSize(
                "copy size exceeds allocation size".to_string(),
            ));
        }

        if size == 0 {
            return Ok(());
        }

        // Allocate command buffer
        let alloc_info = vk::CommandBufferAllocateInfo::default()
            .command_pool(self.command_pool)
            .level(vk::CommandBufferLevel::PRIMARY)
            .command_buffer_count(1);

        let cmd_buffers = self
            .device
            .allocate_command_buffers(&alloc_info)
            .map_err(|e| TransferError::VulkanError(e))?;

        let cmd_buffer = cmd_buffers[0];

        // Record copy
        let begin_info = vk::CommandBufferBeginInfo::default()
            .flags(vk::CommandBufferUsageFlags::ONE_TIME_SUBMIT);

        self.device
            .begin_command_buffer(cmd_buffer, &begin_info)
            .map_err(|e| TransferError::VulkanError(e))?;

        let region = vk::BufferCopy::default()
            .src_offset(0)
            .dst_offset(0)
            .size(size);

        self.device
            .cmd_copy_buffer(cmd_buffer, src.buffer, dst.buffer, &[region]);

        self.device
            .end_command_buffer(cmd_buffer)
            .map_err(|e| TransferError::VulkanError(e))?;

        // Submit
        let cmd_buffers = [cmd_buffer];
        let submit_info = vk::SubmitInfo::default().command_buffers(&cmd_buffers);

        self.device
            .queue_submit(self.queue, &[submit_info], vk::Fence::null())
            .map_err(|e| TransferError::VulkanError(e))?;

        self.device
            .queue_wait_idle(self.queue)
            .map_err(|e| TransferError::VulkanError(e))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transfer_error_display() {
        let err = TransferError::CopyFailed("test".to_string());
        assert!(err.to_string().contains("test"));
    }
}
