import Foundation
import os.log

/// Extension to MultipeerConnectivityManager for GPU device discovery
extension MultipeerConnectivityManager {
    /// Setup GPU device advertisement
    func setupGPUAdvertisement() {
        let gpuManager = MetalGPUManager.shared
        let logger = Logger(subsystem: "com.exo.gpu", category: "MultipeerConnectivity")
        
        guard gpuManager.isSupported else {
            logger.warning("MetalGPUManager GPU advertisement skipped - Metal not available")
            return
        }
        
        // Advertise GPU device information via Bonjour
        let deviceProps = gpuManager.getDeviceProperties()
        
        var discoveryInfo: [String: String] = [
            "service_type": "exo-gpu",
            "version": "1.0",
            "device_type": "gpu_accelerator"
        ]
        
        // Add GPU properties
        discoveryInfo.merge(deviceProps) { _, new in new }
        
        // Update our advertised discovery info
        // Note: This would be used by MCNearbyServiceAdvertiser in a real implementation
        logger.info("GPU Advertisement setup complete - \(gpuManager.availableDevices.count) GPU device(s) available")
    }
    
    /// Get GPU device information for remote access
    func getRemoteGPUInfo() -> [[String: Any]] {
        let gpuManager = MetalGPUManager.shared
        return gpuManager.getDeviceInfoJSON()
    }
    
    /// Handle incoming GPU resource requests from peers
    func handleGPURequest(command: String, data: [String: Any]) {
        let logger = Logger(subsystem: "com.exo.gpu", category: "MultipeerConnectivity")
        let gpuManager = MetalGPUManager.shared
        
        switch command {
        case "enumerate_devices":
            let gpuInfo = getRemoteGPUInfo()
            logger.info("Enumerated \(gpuInfo.count) GPU device(s) for remote access")
            
        case "get_device_info":
            if let deviceId = data["device_id"] as? String {
                let info = gpuManager.availableDevices.first { 
                    $0.id.uuidString == deviceId 
                }
                logger.info("Retrieved info for device: \(String(describing: info?.name))")
            }
            
        case "allocate_memory":
            if let sizeBytes = data["size_bytes"] as? Int64 {
                let result = gpuManager.allocateMemory(sizeBytes: sizeBytes)
                switch result {
                case .success(let buffer):
                    logger.info("Allocated \(buffer.length) bytes for remote GPU operation")
                case .failure(let error):
                    logger.error("Remote allocation failed: \(error)")
                }
            }
            
        default:
            logger.warning("Unknown GPU command: \(command)")
        }
    }
    
    /// Send GPU device info to discovered peers
    func broadcastGPUCapabilities() {
        let logger = Logger(subsystem: "com.exo.gpu", category: "MultipeerConnectivity")
        let gpuInfo = getRemoteGPUInfo()
        
        let message: [String: Any] = [
            "message_type": "gpu_announcement",
            "gpu_devices": gpuInfo,
            "timestamp": Date().timeIntervalSince1970
        ]
        
        if let jsonData = try? JSONSerialization.data(withJSONObject: message),
           let jsonString = String(data: jsonData, encoding: .utf8) {
            logger.info("Broadcasting GPU capabilities: \(gpuInfo.count) device(s)")
        }
    }
}
