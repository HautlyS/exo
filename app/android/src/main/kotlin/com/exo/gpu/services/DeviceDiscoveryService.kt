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
