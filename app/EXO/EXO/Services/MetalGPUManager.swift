import Foundation
import Metal
import os.log

/// Manages Metal GPU devices and operations
@MainActor
class MetalGPUManager: NSObject, ObservableObject {
    @Published var availableDevices: [GPUDevice] = []
    @Published var selectedDevice: GPUDevice?
    @Published var isSupported: Bool = false
    @Published var errorMessage: String?
    
    private var metalDevices: [MTLDevice] = []
    private let logger = Logger(subsystem: "com.exo.gpu", category: "MetalGPUManager")
    
    static let shared = MetalGPUManager()
    
    override init() {
        super.init()
        checkMetalSupport()
        enumerateDevices()
    }
    
    /// Check if Metal is available on this device
    private func checkMetalSupport() {
        if MTLCreateSystemDefaultDevice() != nil {
            isSupported = true
            logger.info("Metal is supported on this device")
        } else {
            isSupported = false
            errorMessage = "Metal framework not available"
            logger.warning("Metal is not available on this device")
        }
    }
    
    /// Enumerate all available Metal GPU devices
    func enumerateDevices() {
        guard isSupported else {
            errorMessage = "Metal not supported"
            return
        }
        
        var devices: [MTLDevice] = []
        
        // Get all available devices (iOS 16.4+)
        if #available(iOS 16.4, *) {
            devices = MTLCopyAllDevices()
        }
        
        // Add default device if not already present
        if let defaultDevice = MTLCreateSystemDefaultDevice() {
            if !devices.contains { $0 === defaultDevice } {
                devices.append(defaultDevice)
            }
        }
        
        metalDevices = devices
        
        availableDevices = metalDevices.enumerated().map { index, device in
            createGPUDevice(from: device, index: index)
        }
        
        logger.info("Enumerated \(self.availableDevices.count) GPU device(s)")
        
        if !availableDevices.isEmpty {
            selectedDevice = availableDevices[0]
        }
    }
    
    /// Create GPUDevice struct from MTLDevice
    private func createGPUDevice(from device: MTLDevice, index: Int) -> GPUDevice {
        let vendorName = getVendorName(for: device.vendorID)
        let supportsFamily = getSupportedFamily(for: device)
        let computeUnits = getComputeUnits(from: device.name)
        let maxThreads = device.maxThreadsPerThreadgroup
        
        return GPUDevice(
            id: UUID(),
            name: device.name,
            vendorName: vendorName,
            maxMemory: device.recommendedMaxWorkingSetSize,
            recommendedMaxWorkingSetSize: device.recommendedMaxWorkingSetSize,
            supportsFamily: supportsFamily,
            isRemovable: device.isRemovable,
            isLowPower: device.isLowPower,
            computeUnits: computeUnits,
            maxThreadsPerThreadgroupWidth: maxThreads.width,
            maxThreadsPerThreadgroupHeight: maxThreads.height,
            maxThreadsPerThreadgroupDepth: maxThreads.depth,
            maxThreadgroupMemory: device.maxThreadgroupMemoryLength
        )
    }
    
    /// Get vendor name from vendor ID
    private func getVendorName(for vendorID: UInt) -> String {
        switch vendorID {
        case 0x106B:
            return "Apple"
        case 0x10DE:
            return "NVIDIA"
        case 0x1002:
            return "AMD"
        case 0x8086:
            return "Intel"
        default:
            return "Unknown"
        }
    }
    
    /// Get supported Metal feature set
    private func getSupportedFamily(for device: MTLDevice) -> String {
        if #available(iOS 16.0, *) {
            if device.supportsFamily(.apple8) { return "Apple8" }
        }
        if #available(iOS 14.0, *) {
            if device.supportsFamily(.apple7) { return "Apple7" }
        }
        if device.supportsFamily(.apple6) { return "Apple6" }
        if device.supportsFamily(.apple5) { return "Apple5" }
        return "Apple4"
    }
    
    /// Estimate compute units from device name
    private func getComputeUnits(from name: String) -> Int {
        // Apple GPU core counts (approximation)
        if name.contains("Pro Max") { return 8 }
        if name.contains("Pro") { return 6 }
        if name.contains("Plus") { return 6 }
        if name.contains("Max") { return 10 }
        return 4 // Default for base models
    }
    
    /// Allocate GPU memory on selected device
    func allocateMemory(sizeBytes: Int64) -> GPUResult<MTLBuffer> {
        guard !metalDevices.isEmpty else {
            return .failure("No GPU device available")
        }
        
        guard let device = metalDevices.first else {
            return .failure("Cannot access GPU device")
        }
        
        guard sizeBytes > 0 else {
            return .failure("Invalid allocation size: must be greater than 0")
        }
        
        guard let buffer = device.makeBuffer(length: Int(sizeBytes), options: .storageModeShared) else {
            return .failure("Failed to allocate \(sizeBytes) bytes on device \(device.name)")
        }
        
        logger.info("Allocated \(sizeBytes) bytes on device: \(device.name)")
        return .success(buffer)
    }
    
    /// Get device properties for networking
    func getDeviceProperties() -> [String: String] {
        var props: [String: String] = [:]
        
        for device in availableDevices {
            let prefix = "gpu_\(device.id.uuidString)"
            props["\(prefix)_name"] = device.name
            props["\(prefix)_vendor"] = device.vendorName
            props["\(prefix)_memory"] = String(device.maxMemory)
            props["\(prefix)_compute_units"] = String(device.computeUnits)
            props["\(prefix)_supports_family"] = device.supportsFamily
            props["\(prefix)_is_low_power"] = String(device.isLowPower)
        }
        
        return props
    }
    
    /// Get GPU device info for JSON serialization
    func getDeviceInfoJSON() -> [[String: Any]] {
        return availableDevices.map { device in
            [
                "device_id": device.id.uuidString,
                "name": device.name,
                "vendor": device.vendorName,
                "max_memory": device.maxMemory,
                "compute_units": device.computeUnits,
                "supports_family": device.supportsFamily,
                "is_low_power": device.isLowPower,
                "is_removable": device.isRemovable,
                "max_threadgroup_memory": device.maxThreadgroupMemory
            ]
        }
    }
}
