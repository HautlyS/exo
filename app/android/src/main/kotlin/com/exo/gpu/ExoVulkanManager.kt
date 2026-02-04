package com.exo.gpu

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.util.concurrent.locks.ReentrantReadWriteLock
import kotlin.concurrent.read
import kotlin.concurrent.write

/**
 * Device information structure.
 */
@Serializable
data class DeviceInfo(
    val deviceId: String,
    val name: String,
    val vendor: String,
    val memoryBytes: Long,
    val computeUnits: Int = 0
)

/**
 * GPU operation result with error information.
 */
sealed class GpuResult<T> {
    data class Success<T>(val data: T) : GpuResult<T>()
    data class Failure<T>(val error: String, val exception: Throwable? = null) : GpuResult<T>()
}

/**
 * High-level GPU manager for Vulkan operations.
 * Thread-safe wrapper around VulkanGpu JNI interface.
 */
class ExoVulkanManager(private val context: Context) {
    private val lock = ReentrantReadWriteLock()
    private var isInitialized = false
    private var devices: List<DeviceInfo> = emptyList()

    companion object {
        private const val TAG = "ExoVulkanManager"
        private val json = Json { ignoreUnknownKeys = true }

        @Volatile
        private var instance: ExoVulkanManager? = null

        /**
         * Get singleton instance.
         */
        fun getInstance(context: Context): ExoVulkanManager {
            return instance ?: synchronized(this) {
                instance ?: ExoVulkanManager(context).also { instance = it }
            }
        }
    }

    /**
     * Initialize Vulkan and enumerate devices.
     * Must be called before other operations.
     */
    suspend fun initialize(): GpuResult<List<DeviceInfo>> = withContext(Dispatchers.Default) {
        lock.write {
            try {
                if (isInitialized) {
                    Log.d(TAG, "Already initialized, returning cached devices")
                    return@withContext GpuResult.Success(devices)
                }

                // Initialize Vulkan
                val initSuccess = VulkanGpu.initializeVulkan()
                if (!initSuccess) {
                    val error = "Vulkan initialization failed"
                    Log.e(TAG, error)
                    return@withContext GpuResult.Failure(error)
                }

                // Enumerate devices
                val devicesJson = VulkanGpu.enumerateDevices()
                devices = parseDevices(devicesJson)

                isInitialized = true
                Log.i(TAG, "Initialized with ${devices.size} device(s)")

                GpuResult.Success(devices)
            } catch (e: Exception) {
                val error = "Initialization failed: ${e.message}"
                Log.e(TAG, error, e)
                GpuResult.Failure(error, e)
            }
        }
    }

    /**
     * Get list of available devices.
     */
    fun getDevices(): GpuResult<List<DeviceInfo>> = lock.read {
        return if (isInitialized) {
            GpuResult.Success(devices.toList())
        } else {
            GpuResult.Failure("Not initialized - call initialize() first")
        }
    }

    /**
     * Allocate memory on specific device.
     */
    suspend fun allocateMemory(
        deviceIndex: Int,
        sizeBytes: Long
    ): GpuResult<String> = withContext(Dispatchers.Default) {
        lock.read {
            try {
                if (!isInitialized) {
                    return@withContext GpuResult.Failure("Not initialized")
                }
                if (deviceIndex !in devices.indices) {
                    return@withContext GpuResult.Failure("Invalid device index: $deviceIndex")
                }
                if (sizeBytes <= 0) {
                    return@withContext GpuResult.Failure("Invalid size: $sizeBytes")
                }

                val handleId = VulkanGpu.allocateMemory(deviceIndex, sizeBytes)
                Log.d(TAG, "Allocated $sizeBytes bytes on device $deviceIndex: $handleId")

                GpuResult.Success(handleId)
            } catch (e: Exception) {
                Log.e(TAG, "Allocation failed", e)
                GpuResult.Failure("Allocation failed: ${e.message}", e)
            }
        }
    }

    /**
     * Free allocated memory.
     */
    suspend fun freeMemory(handleId: String): GpuResult<Boolean> = withContext(Dispatchers.Default) {
        lock.read {
            try {
                val success = VulkanGpu.freeMemory(handleId)
                if (success) {
                    Log.d(TAG, "Freed memory: $handleId")
                }
                GpuResult.Success(success)
            } catch (e: Exception) {
                Log.e(TAG, "Free failed", e)
                GpuResult.Failure("Free failed: ${e.message}", e)
            }
        }
    }

    /**
     * Copy data to device.
     */
    suspend fun copyToDevice(
        handleId: String,
        data: ByteArray
    ): GpuResult<Boolean> = withContext(Dispatchers.Default) {
        lock.read {
            try {
                val success = VulkanGpu.copyToDevice(handleId, data)
                if (success) {
                    Log.d(TAG, "Copied ${data.size} bytes to device: $handleId")
                }
                GpuResult.Success(success)
            } catch (e: Exception) {
                Log.e(TAG, "Copy to device failed", e)
                GpuResult.Failure("Copy failed: ${e.message}", e)
            }
        }
    }

    /**
     * Copy data from device.
     */
    suspend fun copyFromDevice(
        handleId: String,
        sizeBytes: Long
    ): GpuResult<ByteArray> = withContext(Dispatchers.Default) {
        lock.read {
            try {
                val data = VulkanGpu.copyFromDevice(handleId, sizeBytes)
                    ?: return@withContext GpuResult.Failure("Copy returned null")

                Log.d(TAG, "Copied ${data.size} bytes from device: $handleId")
                GpuResult.Success(data)
            } catch (e: Exception) {
                Log.e(TAG, "Copy from device failed", e)
                GpuResult.Failure("Copy failed: ${e.message}", e)
            }
        }
    }

    /**
     * Check if Vulkan is supported on this device.
     */
    fun isSupported(): Boolean {
        return VulkanGpu.isVulkanSupported()
    }

    private fun parseDevices(json: String): List<DeviceInfo> {
        return try {
            if (json.isEmpty() || json == "[]") {
                return emptyList()
            }
            // TODO: Parse JSON array into DeviceInfo list
            // For now, return empty to avoid crashes
            emptyList()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse devices JSON: ${e.message}", e)
            emptyList()
        }
    }
}
