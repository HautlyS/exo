# Phase 3: Android Kotlin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to implement this plan task-by-task with testing.

**Goal:** Create production-ready Android Kotlin integration layer for Vulkan GPU operations with complete JNI bridge, device discovery, and memory management.

**Architecture:** 
- Kotlin wrapper classes for JNI functions (ExoVulkanManager, VulkanGpu)
- Device discovery system using NSD (Network Service Discovery)
- AndroidManifest configuration with required permissions
- CMake/Gradle build integration linking Rust JNI bindings
- Proper error handling and logging throughout

**Tech Stack:** 
- Kotlin 2.0+, Android API 24+
- JNI for Rust interop
- Gradle 8.0+ with NDK integration
- CMake 3.22.1+

---

## Task 1: Create Directory Structure & Gradle Configuration

**Files:**
- Create: `app/android/build.gradle.kts`
- Create: `app/android/CMakeLists.txt`
- Create: `app/android/src/main/AndroidManifest.xml`
- Create: `app/android/src/main/kotlin/com/exo/gpu/ExoVulkanManager.kt`
- Create: `app/android/src/main/kotlin/com/exo/gpu/VulkanGpu.kt`
- Create: `app/android/src/main/kotlin/com/exo/gpu/DeviceDiscovery.kt`
- Create: `tests/android/ExoVulkanManagerTest.kt`

**Step 1: Create top-level build.gradle.kts**

```gradle
plugins {
    id("com.android.application") version "8.1.0"
    kotlin("android") version "2.0.0"
    kotlin("plugin.serialization") version "2.0.0"
}

android {
    namespace = "com.exo.gpu"
    compileSdk = 35
    ndkVersion = "26.0.10469015"

    defaultConfig {
        applicationId = "com.exo.gpu"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        externalNativeBuild {
            cmake {
                cppFlags = "-std=c++17"
                arguments += "-DCMAKE_BUILD_TYPE=Release"
                arguments += "-DCARGO_PROFILE=release"
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isMinifyEnabled = false
        }
    }

    externalNativeBuild {
        cmake {
            path = file("CMakeLists.txt")
            version = "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // Android
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.0")

    // Kotlin
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.0")

    // Networking
    implementation("androidx.nsd:nsd:1.0.0-alpha01")

    // Testing
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.mockito.kotlin:mockito-kotlin:5.1.0")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
}
```

**Step 2: Verify Gradle configuration**

Run: `gradle --version`
Expected: Gradle version 8.0 or higher

- [ ] Gradle configuration created
- [ ] No syntax errors in build.gradle.kts

---

## Task 2: Create CMakeLists.txt for Native Build

**Files:**
- Create: `app/android/CMakeLists.txt`

**Step 1: Write CMakeLists configuration**

```cmake
cmake_minimum_required(VERSION 3.22.1)
project(exo_gpu_android C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Platform detection
if(CMAKE_SYSTEM_NAME STREQUAL "Android")
    set(ANDROID_PLATFORM TRUE)
endif()

# Paths to Rust built libraries
set(RUST_TARGET "aarch64-linux-android")
set(RUST_BUILD_DIR "${CMAKE_SOURCE_DIR}/../../../target/${RUST_TARGET}/release")

# Find Rust static libraries
find_library(
    LIBEXO_JNI_BINDING
    NAMES exo_jni_binding
    PATHS ${RUST_BUILD_DIR}
    NO_DEFAULT_PATH
    NO_CMAKE_FIND_ROOT_PATH
)

if(NOT LIBEXO_JNI_BINDING)
    message(FATAL_ERROR "Could not find libexo_jni_binding.a in ${RUST_BUILD_DIR}")
endif()

message(STATUS "Found exo_jni_binding: ${LIBEXO_JNI_BINDING}")

# Find Vulkan
find_package(Vulkan REQUIRED)

# Create JNI bridge library
add_library(exo_jni_bridge SHARED
    src/native/jni_bridge.c
)

target_include_directories(exo_jni_bridge PRIVATE
    ${JAVA_INCLUDE_PATH}
    ${JAVA_INCLUDE_PATH2}
    ${VULKAN_INCLUDE_DIR}
    ../../../rust/exo_vulkan_binding/src
    ../../../rust/exo_jni_binding/src
)

target_link_libraries(exo_jni_bridge
    ${LIBEXO_JNI_BINDING}
    ${VULKAN_LIBRARIES}
    -ldl
    -llog
)

# Optimization flags
target_compile_options(exo_jni_bridge PRIVATE
    -ffunction-sections
    -fdata-sections
    -fPIC
)

# Link-time optimization for release builds
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    target_compile_options(exo_jni_bridge PRIVATE -flto)
    target_link_options(exo_jni_bridge PRIVATE -flto -Wl,--gc-sections)
endif()

# Install
install(
    TARGETS exo_jni_bridge
    LIBRARY DESTINATION lib
)
```

**Step 2: Verify CMake syntax**

Run: `cmake --version && cd app/android && cmake -P CMakeLists.txt`
Expected: No errors, CMake version 3.22+

- [ ] CMakeLists.txt created
- [ ] No CMake syntax errors

---

## Task 3: Create AndroidManifest.xml

**Files:**
- Create: `app/android/src/main/AndroidManifest.xml`

**Step 1: Write AndroidManifest with Vulkan requirements**

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.exo.gpu">

    <!-- Network permissions for device discovery -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.CHANGE_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />

    <!-- GPU-related permissions -->
    <uses-permission android:name="android.permission.GET_TASKS" />

    <!-- Hardware requirements -->
    <uses-feature
        android:name="android.hardware.vulkan.level"
        android:required="true" />
    <uses-feature
        android:name="android.hardware.vulkan.version"
        android:required="false" />

    <application
        android:allowBackup="false"
        android:debuggable="false"
        android:label="@string/app_name"
        android:theme="@style/Theme.AppCompat">

        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <service
            android:name=".services.DeviceDiscoveryService"
            android:exported="false" />

    </application>

</manifest>
```

**Step 2: Verify XML syntax**

Run: `xmllint --noout app/android/src/main/AndroidManifest.xml`
Expected: No XML errors

- [ ] AndroidManifest.xml created
- [ ] All required permissions declared
- [ ] Vulkan feature requirements specified

---

## Task 4: Create VulkanGpu JNI Wrapper Class

**Files:**
- Create: `app/android/src/main/kotlin/com/exo/gpu/VulkanGpu.kt`

**Step 1: Write VulkanGpu class with JNI declarations**

```kotlin
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

    /**
     * Convert JNI exception to Kotlin exception.
     * @param exception JNI exception
     * @return Kotlin RuntimeException
     */
    private fun jniExceptionToKotlin(exception: Throwable): RuntimeException {
        return when (exception) {
            is IllegalArgumentException -> exception as? RuntimeException ?: RuntimeException(exception)
            is RuntimeException -> exception
            else -> RuntimeException("JNI operation failed: ${exception.message}", exception)
        }
    }
}
```

**Step 2: Verify Kotlin syntax**

Run: `kotlinc -version && cd app/android && kotlinc -cp . src/main/kotlin/com/exo/gpu/VulkanGpu.kt 2>&1 | head -20`
Expected: No syntax errors

- [ ] VulkanGpu.kt created
- [ ] All JNI methods declared with external keyword
- [ ] Documentation comments complete
- [ ] Exception handling documented

---

## Task 5: Create ExoVulkanManager Wrapper

**Files:**
- Create: `app/android/src/main/kotlin/com/exo/gpu/ExoVulkanManager.kt`

**Step 1: Write ExoVulkanManager high-level API**

```kotlin
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
            val jsonArray = Json.parseToJsonElement(json)
            // Handle array or object response
            emptyList() // TODO: Parse JSON array into DeviceInfo list
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse devices JSON", e)
            emptyList()
        }
    }
}
```

**Step 2: Verify Kotlin and design**

Run: `kotlinc -version`
Expected: Kotlin compiler available

- [ ] ExoVulkanManager.kt created
- [ ] Thread-safe with ReentrantReadWriteLock
- [ ] All methods return GpuResult<T>
- [ ] Proper error handling and logging
- [ ] Suspend functions for async operations

---

## Task 6: Create Device Discovery Service

**Files:**
- Create: `app/android/src/main/kotlin/com/exo/gpu/DeviceDiscovery.kt`
- Create: `app/android/src/main/kotlin/com/exo/gpu/services/DeviceDiscoveryService.kt`

**Step 1: Write DeviceDiscovery data classes and interface**

```kotlin
package com.exo.gpu

import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.content.Context
import android.util.Log
import kotlinx.serialization.Serializable
import java.net.InetAddress

/**
 * Discovered GPU device information.
 */
@Serializable
data class DiscoveredDevice(
    val hostName: String,
    val serviceName: String,
    val address: String,
    val port: Int,
    val gpuInfo: GpuDeviceInfo
)

/**
 * GPU capabilities and properties.
 */
@Serializable
data class GpuDeviceInfo(
    val name: String,
    val vendor: String,
    val maxMemory: Long,
    val computeUnits: Int,
    val vulkanVersion: String = "1.0"
)

/**
 * Network Service Discovery helper for finding GPU devices.
 */
class DeviceDiscovery(
    private val context: Context,
    private val serviceType: String = "_exo-gpu._tcp"
) {
    private val nsdManager = context.getSystemService(Context.NSD_SERVICE) as NsdManager?
    private val discoveredDevices = mutableListOf<DiscoveredDevice>()

    companion object {
        private const val TAG = "DeviceDiscovery"
    }

    /**
     * Start discovering GPU devices on network.
     */
    fun startDiscovery(
        onDeviceFound: (DiscoveredDevice) -> Unit,
        onDiscoveryError: (String) -> Unit
    ) {
        if (nsdManager == null) {
            onDiscoveryError("NSD not available on this device")
            return
        }

        val discoveryListener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {
                Log.d(TAG, "Discovery started for $serviceType")
            }

            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                Log.d(TAG, "Service found: ${serviceInfo.serviceName}")
                // Resolve service to get address/port
                nsdManager.resolveService(
                    serviceInfo,
                    object : NsdManager.ResolveListener {
                        override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                            Log.e(TAG, "Failed to resolve service: $errorCode")
                        }

                        override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                            val device = DiscoveredDevice(
                                hostName = serviceInfo.host?.hostName ?: "unknown",
                                serviceName = serviceInfo.serviceName,
                                address = serviceInfo.host?.hostAddress ?: "unknown",
                                port = serviceInfo.port,
                                gpuInfo = GpuDeviceInfo(
                                    name = serviceInfo.attributes["gpu_name"]?.let {
                                        String(it)
                                    } ?: "Unknown",
                                    vendor = serviceInfo.attributes["gpu_vendor"]?.let {
                                        String(it)
                                    } ?: "Unknown",
                                    maxMemory = serviceInfo.attributes["max_memory"]?.let {
                                        String(it).toLongOrNull() ?: 0L
                                    } ?: 0L,
                                    computeUnits = serviceInfo.attributes["compute_units"]?.let {
                                        String(it).toIntOrNull() ?: 0
                                    } ?: 0
                                )
                            )
                            discoveredDevices.add(device)
                            onDeviceFound(device)
                        }
                    }
                )
            }

            override fun onServiceLost(serviceInfo: NsdServiceInfo) {
                Log.d(TAG, "Service lost: ${serviceInfo.serviceName}")
                discoveredDevices.removeAll { it.serviceName == serviceInfo.serviceName }
            }

            override fun onDiscoveryStopped(serviceType: String) {
                Log.d(TAG, "Discovery stopped for $serviceType")
            }

            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.e(TAG, "Failed to start discovery: $errorCode")
                onDiscoveryError("Discovery failed with error code: $errorCode")
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.e(TAG, "Failed to stop discovery: $errorCode")
            }
        }

        nsdManager.discoverServices(
            serviceType,
            NsdManager.PROTOCOL_DNS_SD,
            discoveryListener
        )
    }

    /**
     * Stop discovering devices.
     */
    fun stopDiscovery() {
        // Implementation depends on keeping reference to NsdManager listener
        Log.d(TAG, "Stopping discovery")
    }

    /**
     * Get all discovered devices.
     */
    fun getDiscoveredDevices(): List<DiscoveredDevice> {
        return discoveredDevices.toList()
    }
}
```

**Step 2: Write DeviceDiscoveryService**

```kotlin
package com.exo.gpu.services

import android.app.Service
import android.content.Intent
import android.os.Binder
import android.os.IBinder
import android.util.Log
import com.exo.gpu.DeviceDiscovery
import com.exo.gpu.DiscoveredDevice

/**
 * Background service for continuous device discovery.
 */
class DeviceDiscoveryService : Service() {
    private val binder = LocalBinder()
    private var discovery: DeviceDiscovery? = null

    companion object {
        private const val TAG = "DeviceDiscoveryService"
    }

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Service created")
        discovery = DeviceDiscovery(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "Service started")
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? {
        return binder
    }

    override fun onDestroy() {
        super.onDestroy()
        discovery?.stopDiscovery()
        Log.d(TAG, "Service destroyed")
    }

    inner class LocalBinder : Binder() {
        fun getService(): DeviceDiscoveryService = this@DeviceDiscoveryService
    }

    fun startDiscovering(
        onDeviceFound: (DiscoveredDevice) -> Unit,
        onError: (String) -> Unit
    ) {
        discovery?.startDiscovery(onDeviceFound, onError)
    }

    fun stopDiscovering() {
        discovery?.stopDiscovery()
    }

    fun getDiscoveredDevices(): List<DiscoveredDevice> {
        return discovery?.getDiscoveredDevices() ?: emptyList()
    }
}
```

**Step 3: Verify Kotlin syntax**

Run: `kotlinc -version`
Expected: Kotlin compiler available

- [ ] DeviceDiscovery.kt created
- [ ] DeviceDiscoveryService.kt created
- [ ] NSD integration complete
- [ ] All data classes serializable

---

## Task 7: Create Unit Tests

**Files:**
- Create: `tests/android/kotlin/com/exo/gpu/ExoVulkanManagerTest.kt`
- Create: `tests/android/kotlin/com/exo/gpu/VulkanGpuTest.kt`
- Create: `tests/android/kotlin/com/exo/gpu/DeviceDiscoveryTest.kt`

**Step 1: Write ExoVulkanManagerTest**

```kotlin
package com.exo.gpu

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlin.test.assertFalse

@RunWith(AndroidJUnit4::class)
class ExoVulkanManagerTest {
    private lateinit var context: Context
    private lateinit var manager: ExoVulkanManager

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
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
        // This will depend on actual hardware
        assertNotNull(supported)
    }

    @Test(expected = IllegalArgumentException::class)
    fun testAllocateMemoryWithInvalidSize() {
        // Should validate size before calling JNI
        val result = manager.allocateMemory(0, -1)
        assertTrue(result is GpuResult.Failure)
    }
}
```

**Step 2: Write VulkanGpuTest (native test)**

```kotlin
package com.exo.gpu

import org.junit.Before
import org.junit.Test
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class VulkanGpuTest {
    @Before
    fun setUp() {
        // Load library
    }

    @Test
    fun testInitializeVulkan() {
        try {
            val result = VulkanGpu.initializeVulkan()
            // Result depends on hardware
            assertNotNull(result)
        } catch (e: UnsatisfiedLinkError) {
            // Expected if running on non-Android
        }
    }

    @Test
    fun testEnumerateDevices() {
        try {
            VulkanGpu.initializeVulkan()
            val devicesJson = VulkanGpu.enumerateDevices()
            assertNotNull(devicesJson)
            assertTrue(devicesJson.startsWith("[") || devicesJson.isEmpty())
        } catch (e: Exception) {
            // Expected if Vulkan unavailable
        }
    }
}
```

**Step 3: Verify test structure**

Run: `find tests/android -name "*.kt" -type f | wc -l`
Expected: 3 test files created

- [ ] ExoVulkanManagerTest.kt created
- [ ] VulkanGpuTest.kt created
- [ ] DeviceDiscoveryTest.kt created
- [ ] Test classes properly annotated
- [ ] Test methods are isolated and independent

---

## Task 8: Create JNI Bridge Implementation

**Files:**
- Create: `app/android/src/native/jni_bridge.c`

**Step 1: Write C JNI bridge**

```c
#include <jni.h>
#include <android/log.h>
#include <stdio.h>

#define LOG_TAG "exo_jni_bridge"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

// Forward declarations from Rust library
extern jboolean Java_com_exo_gpu_VulkanGpu_initializeVulkan(
    JNIEnv *env, jclass clazz);

extern jstring Java_com_exo_gpu_VulkanGpu_enumerateDevices(
    JNIEnv *env, jclass clazz);

extern jstring Java_com_exo_gpu_VulkanGpu_allocateMemory(
    JNIEnv *env, jclass clazz, jint deviceIndex, jlong sizeBytes);

extern jboolean Java_com_exo_gpu_VulkanGpu_freeMemory(
    JNIEnv *env, jclass clazz, jstring handleId);

extern jboolean Java_com_exo_gpu_VulkanGpu_copyToDevice(
    JNIEnv *env, jclass clazz, jstring handleId, jbyteArray data);

extern jbyteArray Java_com_exo_gpu_VulkanGpu_copyFromDevice(
    JNIEnv *env, jclass clazz, jstring handleId, jlong sizeBytes);

// JNI_OnLoad - called when library is loaded
jint JNI_OnLoad(JavaVM *vm, void *reserved) {
    LOGI("JNI_OnLoad called");
    JNIEnv *env;
    if ((*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6) != JNI_OK) {
        LOGE("Failed to get JNI environment");
        return -1;
    }
    LOGI("JNI initialized successfully");
    return JNI_VERSION_1_6;
}

// JNI_OnUnload - called when library is unloaded
void JNI_OnUnload(JavaVM *vm, void *reserved) {
    LOGI("JNI_OnUnload called");
}
```

**Step 2: Verify C syntax**

Run: `clang -fsyntax-only -fPIC app/android/src/native/jni_bridge.c`
Expected: No syntax errors

- [ ] jni_bridge.c created
- [ ] All JNI function signatures correct
- [ ] Log macros properly defined
- [ ] JNI_OnLoad and JNI_OnUnload implemented

---

## Task 9: Compile and Test Android Native Build

**Files:**
- No new files

**Step 1: Build JNI binding for Android target**

Run: `cd /home/hautly/exo && cargo build --target aarch64-linux-android --release -p exo_jni_binding`
Expected: Successful build, no errors

- [ ] aarch64-linux-android target installed: `rustup target add aarch64-linux-android`
- [ ] Build succeeds with no errors
- [ ] libexo_jni_binding.a created at target/aarch64-linux-android/release/

**Step 2: Build Android app**

Run: `cd app/android && ./gradlew assembleRelease`
Expected: APK generated successfully

- [ ] Gradle build succeeds
- [ ] CMake correctly links Rust library
- [ ] exo_jni_binding symbols resolved
- [ ] APK generated

**Step 3: Run instrumented tests**

Run: `cd app/android && ./gradlew connectedAndroidTest`
Expected: Tests pass on device/emulator

- [ ] All unit tests pass
- [ ] No runtime errors in JNI
- [ ] Device enumeration works

---

## Task 10: Document and Create README

**Files:**
- Create: `app/android/README.md`
- Create: `app/android/DEVELOPMENT.md`

**Step 1: Write README**

```markdown
# Exo GPU - Android Vulkan Implementation

Production-ready Android Vulkan GPU integration for distributed AI inference.

## Features

- Native Vulkan GPU access on Android
- JNI bindings for Kotlin/Java
- Device discovery via NSD
- Memory management (allocation, deallocation)
- Host↔Device data transfer
- Thread-safe API with coroutines

## Requirements

- Android API 24+
- Vulkan 1.0+
- Android NDK 26.0+
- Gradle 8.0+
- Kotlin 2.0+

## Building

```bash
# Install Android targets
rustup target add aarch64-linux-android

# Build Rust library for Android
cargo build --target aarch64-linux-android --release -p exo_jni_binding

# Build Android app
cd app/android
./gradlew assembleRelease

# Run tests
./gradlew connectedAndroidTest
```

## Usage

```kotlin
val manager = ExoVulkanManager.getInstance(context)

// Initialize and enumerate devices
when (val result = manager.initialize()) {
    is GpuResult.Success -> {
        for (device in result.data) {
            Log.i("GPU", "Found: ${device.name} - ${device.memoryBytes} bytes")
        }
    }
    is GpuResult.Failure -> Log.e("GPU", result.error)
}

// Allocate memory
when (val result = manager.allocateMemory(0, 1024 * 1024)) {
    is GpuResult.Success -> {
        val handleId = result.data
        // Use handleId for transfers
    }
    is GpuResult.Failure -> Log.e("GPU", result.error)
}
```

## Architecture

- `VulkanGpu.kt` - Low-level JNI interface
- `ExoVulkanManager.kt` - High-level thread-safe API
- `DeviceDiscovery.kt` - Network device discovery
- `CMakeLists.txt` - Native build configuration
- `build.gradle.kts` - Gradle build configuration

## Testing

Run all tests:
```bash
./gradlew test connectedAndroidTest
```

## License

See repository LICENSE
```

**Step 2: Write DEVELOPMENT.md**

```markdown
# Android Development Guide

## Setup

1. Install Android SDK/NDK
2. Add to PATH: `export ANDROID_SDK_ROOT=$HOME/Android/Sdk`
3. Install Rust Android target: `rustup target add aarch64-linux-android`

## Development Workflow

1. Make changes to Kotlin code
2. Build JNI binding: `cargo build --target aarch64-linux-android --release`
3. Build app: `./gradlew assembleDebug`
4. Run tests: `./gradlew connectedAndroidTest`

## Debugging

- View logs: `adb logcat | grep -E "ExoVulkan|VulkanGpu|exo_jni"`
- Check library loading: `adb shell ldd /system/app/...`
- Debug native code: Use Android Studio with LLDB

## Common Issues

### Library not found
- Verify: `ls target/aarch64-linux-android/release/libexo_jni_binding.a`
- Check CMakeLists.txt paths match your build

### Device enumeration returns empty
- Ensure Vulkan drivers installed
- Check: `adb shell vulkaninfo`

### JNI exceptions
- Check logcat for full error message
- Verify method signatures match Rust side
```

**Step 3: Verify documentation**

Run: `wc -l app/android/README.md app/android/DEVELOPMENT.md`
Expected: Both files created with substantial content

- [ ] README.md created with usage examples
- [ ] DEVELOPMENT.md created with setup instructions
- [ ] Code examples are correct and tested
- [ ] All sections documented

---

## Verification Checklist

After all tasks complete:

```bash
# 1. Verify directory structure
find app/android -type f -name "*.kt" -o -name "*.xml" -o -name "*.gradle" \
  | wc -l
# Expected: 8+ files

# 2. Verify Kotlin syntax
cd app/android
kotlinc -version

# 3. Verify CMake syntax
cmake -P CMakeLists.txt
# Expected: No errors

# 4. Build Rust library for Android
cd /home/hautly/exo
cargo build --target aarch64-linux-android --release -p exo_jni_binding
# Expected: Completes successfully

# 5. Verify all files exist
ls -la app/android/src/main/kotlin/com/exo/gpu/*.kt
ls -la app/android/src/main/AndroidManifest.xml
ls -la app/android/CMakeLists.txt
ls -la app/android/build.gradle.kts
# Expected: All files present

# 6. Count lines of code
find app/android/src/main/kotlin -name "*.kt" -exec wc -l {} + | tail -1
# Expected: 500+ lines of Kotlin code
```

---

## Success Criteria

✅ Phase 3 is complete when:

1. **All 5 Kotlin files exist and compile**
   - VulkanGpu.kt (JNI interface)
   - ExoVulkanManager.kt (high-level API)
   - DeviceDiscovery.kt (NSD integration)
   - DiscoveredDevice & GpuDeviceInfo (data classes)
   - Unit tests all pass

2. **Build system fully configured**
   - build.gradle.kts with NDK settings
   - CMakeLists.txt correctly links Rust library
   - AndroidManifest.xml with proper permissions

3. **JNI bridge working**
   - VulkanGpu methods call into Rust successfully
   - ExoVulkanManager provides thread-safe API
   - No UnsatisfiedLinkError on properly configured device

4. **Tests pass**
   - Unit tests for manager logic pass
   - JNI tests work on Android device/emulator
   - No segfaults or access violations

5. **Documentation complete**
   - README.md with usage examples
   - DEVELOPMENT.md with setup guide
   - All code has javadoc/kdoc comments

---

## Integration with Phases 2 & 4

**Depends on**: Phase 2 (JNI bindings implemented and compiling)

**Enables**: Phase 4 (iOS equivalent) and Phase 5 (Python FFI integration)

**After Phase 3 complete**, you can:
- Run device enumeration on Android devices
- Allocate GPU memory remotely
- Transfer data to/from GPU
- Discover devices via network
