package com.exo.gpu

import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.content.Context
import android.util.Log
import kotlinx.serialization.Serializable

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
    private var discoveryListener: NsdManager.DiscoveryListener? = null

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

        discoveryListener = object : NsdManager.DiscoveryListener {
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
        if (nsdManager != null && discoveryListener != null) {
            try {
                nsdManager.stopServiceDiscovery(discoveryListener!!)
                Log.d(TAG, "Stopping discovery")
            } catch (e: Exception) {
                Log.e(TAG, "Error stopping discovery: ${e.message}", e)
            }
        }
    }

    /**
     * Get all discovered devices.
     */
    fun getDiscoveredDevices(): List<DiscoveredDevice> {
        return discoveredDevices.toList()
    }
}
