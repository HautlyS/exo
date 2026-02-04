import Foundation
import SwiftUI

@MainActor
class GPUViewModel: NSObject, ObservableObject {
    @Published var gpuDevices: [GPUDevice] = []
    @Published var selectedDevice: GPUDevice?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var successMessage: String?
    @Published var allocatedMemory: [String: String] = [:]
    
    private let gpuManager: MetalGPUManager
    private var refreshTimer: Timer?
    
    override init() {
        self.gpuManager = MetalGPUManager.shared
        super.init()
        updateDevices()
        startPeriodicRefresh()
    }
    
    deinit {
        refreshTimer?.invalidate()
    }
    
    func updateDevices() {
        gpuDevices = gpuManager.availableDevices
        selectedDevice = gpuManager.selectedDevice
    }
    
    func selectDevice(_ device: GPUDevice) {
        selectedDevice = device
    }
    
    func allocateMemory(sizeBytes: Int64) async {
        isLoading = true
        defer { isLoading = false }
        
        guard sizeBytes > 0 else {
            errorMessage = "Size must be greater than 0"
            return
        }
        
        guard let device = selectedDevice else {
            errorMessage = "No device selected"
            return
        }
        
        let result = gpuManager.allocateMemory(sizeBytes: sizeBytes)
        
        switch result {
        case .success(let buffer):
            let key = "alloc_\(Date().timeIntervalSince1970)"
            let displayName = "Memory \(buffer.length / (1024*1024))MB on \(device.name)"
            allocatedMemory[key] = displayName
            successMessage = "Successfully allocated \(buffer.length) bytes"
            errorMessage = nil
            
        case .failure(let error):
            errorMessage = error
            successMessage = nil
        }
    }
    
    func clearError() {
        errorMessage = nil
    }
    
    func clearSuccess() {
        successMessage = nil
    }
    
    func clearAllMessages() {
        errorMessage = nil
        successMessage = nil
    }
    
    private func startPeriodicRefresh() {
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            Task {
                await self?.updateDevices()
            }
        }
    }
    
    func stopPeriodicRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
}
