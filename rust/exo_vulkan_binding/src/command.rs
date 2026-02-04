//! Vulkan command buffer and queue management
//!
//! Provides abstractions for recording and submitting Vulkan commands,
//! including synchronization primitives.

use ash::vk;
use thiserror::Error;

/// Command buffer related errors
#[derive(Error, Debug)]
pub enum CommandError {
    #[error("Command pool creation failed: {0}")]
    PoolCreationFailed(String),

    #[error("Command buffer allocation failed: {0}")]
    AllocationFailed(String),

    #[error("Command recording failed: {0}")]
    RecordingFailed(String),

    #[error("Queue submission failed: {0}")]
    SubmissionFailed(String),

    #[error("Synchronization failed: {0}")]
    SynchronizationFailed(String),

    #[error("Vulkan error: {0:?}")]
    VulkanError(vk::Result),
}

pub type CommandResult<T> = Result<T, CommandError>;

/// Represents a Vulkan command pool for allocating command buffers
pub struct CommandPool {
    device: ash::Device,
    pool: vk::CommandPool,
    queue_family_index: u32,
}

impl CommandPool {
    /// Create a new command pool
    ///
    /// # Safety Requirements
    /// - device must be valid and not destroyed during lifetime
    /// - queue_family_index must be valid for device
    ///
    /// # Arguments
    /// * `device` - Ash device
    /// * `queue_family_index` - Queue family to use
    pub fn new(device: ash::Device, queue_family_index: u32) -> CommandResult<Self> {
        unsafe {
            // Create command pool
            // SAFETY:
            //   - device is valid (caller's responsibility)
            //   - queue_family_index is validated by caller
            let pool_info = vk::CommandPoolCreateInfo::default()
                .queue_family_index(queue_family_index)
                .flags(vk::CommandPoolCreateFlags::RESET_COMMAND_BUFFER);

            let pool = device
                .create_command_pool(&pool_info, None)
                .map_err(|e| CommandError::VulkanError(e))?;

            Ok(CommandPool {
                device,
                pool,
                queue_family_index,
            })
        }
    }

    /// Allocate command buffers from this pool
    ///
    /// # Arguments
    /// * `count` - Number of buffers to allocate
    ///
    /// # Returns
    /// Vector of allocated command buffers
    pub fn allocate_buffers(&self, count: u32) -> CommandResult<Vec<vk::CommandBuffer>> {
        unsafe {
            // Allocate command buffers
            // SAFETY:
            //   - pool is valid (created in new())
            //   - device is valid
            //   - count > 0 is caller's responsibility
            let alloc_info = vk::CommandBufferAllocateInfo::default()
                .command_pool(self.pool)
                .level(vk::CommandBufferLevel::PRIMARY)
                .command_buffer_count(count);

            self.device
                .allocate_command_buffers(&alloc_info)
                .map_err(|e| CommandError::AllocationFailed(e.to_string()))
        }
    }

    /// Begin recording a command buffer
    ///
    /// # Arguments
    /// * `buffer` - Command buffer to begin recording
    /// * `flags` - Command buffer usage flags
    pub fn begin_recording(
        &self,
        buffer: vk::CommandBuffer,
        flags: vk::CommandBufferUsageFlags,
    ) -> CommandResult<()> {
        unsafe {
            // Begin command buffer recording
            // SAFETY:
            //   - buffer is valid (allocated from this pool)
            //   - device is valid
            let begin_info = vk::CommandBufferBeginInfo::default().flags(flags);

            self.device
                .begin_command_buffer(buffer, &begin_info)
                .map_err(|e| CommandError::RecordingFailed(e.to_string()))
        }
    }

    /// End recording a command buffer
    ///
    /// # Arguments
    /// * `buffer` - Command buffer to end
    pub fn end_recording(&self, buffer: vk::CommandBuffer) -> CommandResult<()> {
        unsafe {
            // End command buffer recording
            // SAFETY:
            //   - buffer is valid and in recording state
            //   - device is valid
            self.device
                .end_command_buffer(buffer)
                .map_err(|e| CommandError::RecordingFailed(e.to_string()))
        }
    }

    /// Reset command buffer for reuse
    ///
    /// # Arguments
    /// * `buffer` - Command buffer to reset
    pub fn reset_buffer(&self, buffer: vk::CommandBuffer) -> CommandResult<()> {
        unsafe {
            // Reset command buffer
            // SAFETY:
            //   - buffer is valid
            //   - device is valid
            self.device
                .reset_command_buffer(buffer, vk::CommandBufferResetFlags::empty())
                .map_err(|e| CommandError::VulkanError(e))
        }
    }

    /// Record pipeline barrier command
    ///
    /// Used for memory synchronization between operations
    pub fn record_barrier(
        &self,
        buffer: vk::CommandBuffer,
        src_stage: vk::PipelineStageFlags,
        dst_stage: vk::PipelineStageFlags,
        memory_barriers: &[vk::MemoryBarrier],
    ) -> CommandResult<()> {
        unsafe {
            // Record memory barrier
            // SAFETY:
            //   - buffer is valid and in recording state
            //   - device is valid
            //   - memory_barriers are valid for this scope
            self.device.cmd_pipeline_barrier(
                buffer,
                src_stage,
                dst_stage,
                vk::DependencyFlags::empty(),
                memory_barriers,
                &[],
                &[],
            );
            Ok(())
        }
    }

    /// Get the queue family index for this pool
    pub fn queue_family_index(&self) -> u32 {
        self.queue_family_index
    }
}

impl Drop for CommandPool {
    fn drop(&mut self) {
        unsafe {
            // Destroy command pool
            // SAFETY:
            //   - pool is valid
            //   - device is valid
            //   - no command buffers from this pool are in use
            self.device.destroy_command_pool(self.pool, None);
        }
    }
}

/// Wrapper for queue operations
pub struct Queue {
    device: ash::Device,
    queue: vk::Queue,
    queue_family_index: u32,
}

impl Queue {
    /// Create a queue reference
    ///
    /// # Safety Requirements
    /// - device must be valid
    /// - queue must be valid for the device
    /// - queue_family_index must be valid
    pub fn new(
        device: ash::Device,
        queue: vk::Queue,
        queue_family_index: u32,
    ) -> Self {
        Queue {
            device,
            queue,
            queue_family_index,
        }
    }

    /// Submit command buffers to queue
    ///
    /// # Arguments
    /// * `buffers` - Command buffers to submit
    /// * `wait_semaphore` - Optional semaphore to wait on
    /// * `signal_semaphore` - Optional semaphore to signal
    /// * `fence` - Optional fence to signal on completion
    pub fn submit(
        &self,
        buffers: &[vk::CommandBuffer],
        wait_semaphore: Option<vk::Semaphore>,
        signal_semaphore: Option<vk::Semaphore>,
        fence: Option<vk::Fence>,
    ) -> CommandResult<()> {
        unsafe {
            // Build submit info
            // SAFETY:
            //   - device is valid
            //   - queue is valid
            //   - buffers, semaphores, fence are all valid
            let wait_stages = [vk::PipelineStageFlags::ALL_COMMANDS];
            let (wait_semaphores, wait_stages_ref) = if let Some(sem) = wait_semaphore {
                (vec![sem], &wait_stages[..])
            } else {
                (vec![], &[][..])
            };

            let signal_semaphores = if let Some(sem) = signal_semaphore {
                vec![sem]
            } else {
                vec![]
            };

            let submit_info = vk::SubmitInfo::default()
                .wait_semaphores(&wait_semaphores)
                .wait_dst_stage_mask(wait_stages_ref)
                .command_buffers(buffers)
                .signal_semaphores(&signal_semaphores);

            self.device
                .queue_submit(self.queue, &[submit_info], fence.unwrap_or(vk::Fence::null()))
                .map_err(|e| CommandError::SubmissionFailed(e.to_string()))
        }
    }

    /// Wait for queue to be idle
    pub fn wait_idle(&self) -> CommandResult<()> {
        unsafe {
            // Wait for queue
            // SAFETY:
            //   - queue is valid
            //   - device is valid
            self.device
                .queue_wait_idle(self.queue)
                .map_err(|e| CommandError::SynchronizationFailed(e.to_string()))
        }
    }

    /// Get the queue family index
    pub fn queue_family_index(&self) -> u32 {
        self.queue_family_index
    }
}

/// Synchronization primitive: Fence
pub struct Fence {
    device: ash::Device,
    fence: vk::Fence,
}

impl Fence {
    /// Create a new fence
    ///
    /// # Arguments
    /// * `device` - Ash device
    /// * `signaled` - If true, fence starts in signaled state
    pub fn new(device: ash::Device, signaled: bool) -> CommandResult<Self> {
        unsafe {
            // Create fence
            // SAFETY:
            //   - device is valid
            let fence_info = vk::FenceCreateInfo::default().flags(
                if signaled {
                    vk::FenceCreateFlags::SIGNALED
                } else {
                    vk::FenceCreateFlags::empty()
                },
            );

            let fence = device
                .create_fence(&fence_info, None)
                .map_err(|e| CommandError::VulkanError(e))?;

            Ok(Fence { device, fence })
        }
    }

    /// Wait for fence to be signaled
    ///
    /// # Arguments
    /// * `timeout_ns` - Timeout in nanoseconds
    pub fn wait(&self, timeout_ns: u64) -> CommandResult<bool> {
        unsafe {
            // Wait for fence
            // SAFETY:
            //   - fence is valid
            //   - device is valid
            match self
                .device
                .wait_for_fences(&[self.fence], true, timeout_ns)
            {
                Ok(()) => Ok(true),
                Err(vk::Result::TIMEOUT) => Ok(false),
                Err(e) => Err(CommandError::SynchronizationFailed(e.to_string())),
            }
        }
    }

    /// Reset fence to unsignaled state
    pub fn reset(&self) -> CommandResult<()> {
        unsafe {
            // Reset fence
            // SAFETY:
            //   - fence is valid
            //   - device is valid
            self.device
                .reset_fences(&[self.fence])
                .map_err(|e| CommandError::VulkanError(e))
        }
    }

    /// Get the raw fence handle
    pub fn raw(&self) -> vk::Fence {
        self.fence
    }
}

impl Drop for Fence {
    fn drop(&mut self) {
        unsafe {
            // Destroy fence
            // SAFETY:
            //   - fence is valid
            //   - device is valid
            self.device.destroy_fence(self.fence, None);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_command_error_display() {
        let err = CommandError::PoolCreationFailed("test".to_string());
        assert!(err.to_string().contains("test"));
    }
}
