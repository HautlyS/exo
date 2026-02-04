package com.exo.gpu

import android.util.Log
import java.nio.ByteBuffer

/**
 * JNI interface to Vulkan GPU operations.
 * Direct bindings to exo_jni_binding native library.
 */
object VulkanGpu {
    private const val TAG = "VulkanGpu"

    init {
        try {
            System.loadLibrary("exo_jni_binding")
            Log.i(TAG, "Successfully loaded exo_jni_binding library")
        } catch (e: UnsatisfiedLinkError) {
            Log.e(TAG, "Failed to load exo_jni_binding: ${e.message}")
            throw RuntimeException("Could not load native Vulkan library", e)
        }
    }

    // ============ Device Management ============

    /**
     * Initialize Vulkan context.
     * @return true if initialization succeeded
     */
    external fun initializeVulkan(): Boolean

    /**
     * Get list of available Vulkan devices in JSON format.
     * JSON structure: [{"device_id": "...", "name": "...", "vendor": "...", "memory_bytes": 12345}]
     * @return JSON string of devices, or null on error
     * @throws RuntimeException if JNI call fails
     */
    @Throws(RuntimeException::class)
    external fun enumerateDevices(): String

    /**
     * Get device name by index.
     * @param deviceIndex 0-based device index
     * @return Device name string
     * @throws RuntimeException if device not found
     */
    @Throws(RuntimeException::class)
    external fun getDeviceName(deviceIndex: Int): String

    /**
     * Get device memory capacity in bytes.
     * @param deviceIndex 0-based device index
     * @return Memory size in bytes
     * @throws RuntimeException if device not found
     */
    @Throws(RuntimeException::class)
    external fun getDeviceMemory(deviceIndex: Int): Long

    /**
     * Get device compute units (SM/EU count).
     * @param deviceIndex 0-based device index
     * @return Number of compute units
     * @throws RuntimeException if device not found
     */
    @Throws(RuntimeException::class)
    external fun getComputeUnits(deviceIndex: Int): Int

    // ============ Memory Management ============

    /**
     * Allocate memory on device.
     * @param deviceIndex 0-based device index
     * @param sizeBytes Number of bytes to allocate
     * @return Handle ID string for this allocation
     * @throws RuntimeException on allocation failure
     * @throws IllegalArgumentException if size invalid
     */
    @Throws(RuntimeException::class, IllegalArgumentException::class)
    external fun allocateMemory(deviceIndex: Int, sizeBytes: Long): String

    /**
     * Free previously allocated memory.
     * @param handleId Handle returned from allocateMemory()
     * @return true if freed successfully, false if handle not found
     * @throws RuntimeException on deallocation failure
     */
    @Throws(RuntimeException::class)
    external fun freeMemory(handleId: String): Boolean

    // ============ Data Transfer ============

    /**
     * Copy data from host to device.
     * @param handleId Handle from allocateMemory()
     * @param data Byte array to copy
     * @return true if copy succeeded
     * @throws RuntimeException on transfer failure
     * @throws IllegalArgumentException if handle invalid
     */
    @Throws(RuntimeException::class, IllegalArgumentException::class)
    external fun copyToDevice(handleId: String, data: ByteArray): Boolean

    /**
     * Copy data from device to host.
     * @param handleId Handle from allocateMemory()
     * @param sizeBytes Number of bytes to copy
     * @return ByteArray with copied data, or null on error
     * @throws RuntimeException on transfer failure
     * @throws IllegalArgumentException if handle invalid
     */
    @Throws(RuntimeException::class, IllegalArgumentException::class)
    external fun copyFromDevice(handleId: String, sizeBytes: Long): ByteArray?

    // ============ Utility Methods ============

    /**
     * Verify that required Vulkan capabilities are available.
     * @return true if system supports Vulkan operations
     */
    fun isVulkanSupported(): Boolean {
        return try {
            initializeVulkan()
        } catch (e: Exception) {
            Log.w(TAG, "Vulkan not supported: ${e.message}")
            false
        }
    }
}
