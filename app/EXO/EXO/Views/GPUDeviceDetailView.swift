import SwiftUI

struct GPUDeviceDetailView: View {
    let device: GPUDevice
    @ObservedObject var viewModel: GPUViewModel
    @State private var allocationSize: String = "1048576" // 1MB default
    @State private var showingAllocationSheet = false
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Device Header
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Image(systemName: "internaldrive.fill")
                            .foregroundColor(.blue)
                            .font(.title2)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(device.name)
                                .font(.title2)
                                .fontWeight(.bold)
                            Text(device.vendorName)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding(.bottom, 8)
                
                Divider()
                
                // Properties Grid
                VStack(alignment: .leading, spacing: 12) {
                    Text("Properties")
                        .font(.headline)
                        .padding(.horizontal, 4)
                    
                    Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 12) {
                        GridRow {
                            Text("Memory")
                                .fontWeight(.semibold)
                            Spacer()
                            Text("\(device.memoryGB, specifier: "%.2f") GB")
                        }
                        
                        GridRow {
                            Text("Compute Units")
                                .fontWeight(.semibold)
                            Spacer()
                            Text("\(device.computeUnits)")
                        }
                        
                        GridRow {
                            Text("Family")
                                .fontWeight(.semibold)
                            Spacer()
                            Text(device.supportsFamily)
                        }
                        
                        GridRow {
                            Text("Low Power")
                                .fontWeight(.semibold)
                            Spacer()
                            Image(systemName: device.isLowPower ? "checkmark.circle.fill" : "xmark.circle")
                                .foregroundColor(device.isLowPower ? .yellow : .green)
                        }
                        
                        GridRow {
                            Text("Removable")
                                .fontWeight(.semibold)
                            Spacer()
                            Image(systemName: device.isRemovable ? "checkmark.circle.fill" : "xmark.circle")
                                .foregroundColor(.blue)
                        }
                        
                        GridRow {
                            Text("Max Threadgroup")
                                .fontWeight(.semibold)
                            Spacer()
                            Text("\(device.maxThreadsPerThreadgroupWidth)x\(device.maxThreadsPerThreadgroupHeight)x\(device.maxThreadsPerThreadgroupDepth)")
                        }
                        
                        GridRow {
                            Text("Threadgroup Memory")
                                .fontWeight(.semibold)
                            Spacer()
                            Text("\(device.maxThreadgroupMemory / 1024) KB")
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
                }
                
                Divider()
                
                // Memory Allocation Section
                VStack(alignment: .leading, spacing: 12) {
                    Text("Memory Allocation")
                        .font(.headline)
                    
                    HStack {
                        TextField("Size (bytes)", text: $allocationSize)
                            .textFieldStyle(.roundedBorder)
                            .keyboardType(.numberPad)
                        
                        Button(action: {
                            Task {
                                if let size = Int64(allocationSize) {
                                    await viewModel.allocateMemory(sizeBytes: size)
                                } else {
                                    viewModel.errorMessage = "Invalid size format"
                                }
                            }
                        }) {
                            Text("Allocate")
                                .fontWeight(.semibold)
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    
                    if let successMsg = viewModel.successMessage {
                        HStack {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.green)
                            Text(successMsg)
                                .font(.caption)
                                .lineLimit(2)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.green.opacity(0.1))
                        .cornerRadius(6)
                    }
                    
                    if !viewModel.allocatedMemory.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Allocated Memory")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundColor(.secondary)
                            
                            ForEach(Array(viewModel.allocatedMemory.values), id: \.self) { value in
                                HStack {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundColor(.green)
                                    Text(value)
                                        .font(.caption)
                                        .lineLimit(1)
                                    Spacer()
                                }
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color.green.opacity(0.05))
                        .cornerRadius(6)
                    }
                }
                
                Spacer()
            }
            .padding()
        }
        .navigationTitle("Device Details")
        .navigationBarTitleDisplayMode(.inline)
        .alert("Error", isPresented: .constant(viewModel.errorMessage != nil)) {
            Button("OK") { viewModel.clearError() }
        } message: {
            if let error = viewModel.errorMessage {
                Text(error)
            }
        }
        .onAppear {
            viewModel.selectDevice(device)
        }
    }
}

#Preview {
    NavigationStack {
        GPUDeviceDetailView(
            device: GPUDevice(
                id: UUID(),
                name: "A17 Pro",
                vendorName: "Apple",
                maxMemory: 8 * 1024 * 1024 * 1024,
                recommendedMaxWorkingSetSize: 5 * 1024 * 1024 * 1024,
                supportsFamily: "Apple8",
                isRemovable: false,
                isLowPower: false,
                computeUnits: 6,
                maxThreadsPerThreadgroupWidth: 256,
                maxThreadsPerThreadgroupHeight: 256,
                maxThreadsPerThreadgroupDepth: 256,
                maxThreadgroupMemory: 32 * 1024
            ),
            viewModel: GPUViewModel()
        )
    }
}
