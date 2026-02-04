import Foundation
import Metal

/// Represents a Metal GPU device with its properties
@MainActor
struct GPUDevice: Identifiable, Codable, Hashable {
    let id: UUID
    let name: String
    let vendorName: String
    let maxMemory: Int64
    let recommendedMaxWorkingSetSize: Int64
    let supportsFamily: String
    let isRemovable: Bool
    let isLowPower: Bool
    let computeUnits: Int
    let maxThreadsPerThreadgroupWidth: Int
    let maxThreadsPerThreadgroupHeight: Int
    let maxThreadsPerThreadgroupDepth: Int
    let maxThreadgroupMemory: Int
    
    var displayName: String {
        "\(name) (\(vendorName))"
    }
    
    var memoryGB: Double {
        Double(maxMemory) / (1024 * 1024 * 1024)
    }
    
    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
    
    static func == (lhs: GPUDevice, rhs: GPUDevice) -> Bool {
        lhs.id == rhs.id
    }
}

/// Result type for GPU operations
enum GPUResult<T> {
    case success(T)
    case failure(String)
}

/// GPU operation errors
enum GPUError: LocalizedError {
    case deviceNotFound
    case metalNotAvailable
    case allocationFailed(String)
    case transferFailed(String)
    case invalidSize
    case operationCancelled
    
    var errorDescription: String? {
        switch self {
        case .deviceNotFound:
            return "GPU device not found"
        case .metalNotAvailable:
            return "Metal is not available on this device"
        case .allocationFailed(let reason):
            return "Memory allocation failed: \(reason)"
        case .transferFailed(let reason):
            return "Data transfer failed: \(reason)"
        case .invalidSize:
            return "Invalid allocation size (must be > 0)"
        case .operationCancelled:
            return "Operation was cancelled"
        }
    }
    
    var recoverySuggestion: String? {
        switch self {
        case .metalNotAvailable:
            return "This device requires iOS 14.0+ with A12 Bionic or later"
        case .allocationFailed:
            return "Try allocating a smaller amount of memory"
        case .invalidSize:
            return "Size must be greater than 0 bytes"
        default:
            return nil
        }
    }
}

/// GPU vendor identification
enum GPUVendor: String, Codable {
    case apple = "Apple"
    case nvidia = "NVIDIA"
    case amd = "AMD"
    case intel = "Intel"
    case unknown = "Unknown"
    
    init(from vendorID: UInt) {
        switch vendorID {
        case 0x106B:
            self = .apple
        case 0x10DE:
            self = .nvidia
        case 0x1002:
            self = .amd
        case 0x8086:
            self = .intel
        default:
            self = .unknown
        }
    }
}
