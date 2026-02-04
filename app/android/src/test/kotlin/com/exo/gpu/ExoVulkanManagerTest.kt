package com.exo.gpu

import android.content.Context
import org.junit.Before
import org.junit.Test
import org.mockito.Mock
import org.mockito.MockitoAnnotations
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlin.test.assertFalse

class ExoVulkanManagerTest {
    @Mock
    private lateinit var context: Context

    private lateinit var manager: ExoVulkanManager

    @Before
    fun setUp() {
        MockitoAnnotations.openMocks(this)
        manager = ExoVulkanManager(context)
    }

    @Test
    fun testGetDevicesBeforeInitialize() {
        val result = manager.getDevices()
        assertTrue(result is GpuResult.Failure)
    }

    @Test
    fun testIsSupported() {
        val supported = manager.isSupported()
        // This will depend on actual hardware - just verify it returns a boolean
        assertNotNull(supported)
    }

    @Test
    fun testDeviceInfoCreation() {
        val device = DeviceInfo(
            deviceId = "gpu-0",
            name = "Test GPU",
            vendor = "NVIDIA",
            memoryBytes = 4L * 1024 * 1024 * 1024, // 4GB
            computeUnits = 128
        )
        
        assertEquals("gpu-0", device.deviceId)
        assertEquals("Test GPU", device.name)
        assertEquals("NVIDIA", device.vendor)
        assertEquals(4L * 1024 * 1024 * 1024, device.memoryBytes)
        assertEquals(128, device.computeUnits)
    }

    @Test
    fun testGpuResultSuccess() {
        val result: GpuResult<String> = GpuResult.Success("test data")
        assertTrue(result is GpuResult.Success)
        
        when (result) {
            is GpuResult.Success -> assertEquals("test data", result.data)
            is GpuResult.Failure -> throw AssertionError("Should be Success")
        }
    }

    @Test
    fun testGpuResultFailure() {
        val result: GpuResult<String> = GpuResult.Failure("test error")
        assertTrue(result is GpuResult.Failure)
        
        when (result) {
            is GpuResult.Success -> throw AssertionError("Should be Failure")
            is GpuResult.Failure -> assertEquals("test error", result.error)
        }
    }

    @Test
    fun testSingletonInstance() {
        val instance1 = ExoVulkanManager.getInstance(context)
        val instance2 = ExoVulkanManager.getInstance(context)
        
        // Both should be the same instance
        assertTrue(instance1 === instance2)
    }
}
