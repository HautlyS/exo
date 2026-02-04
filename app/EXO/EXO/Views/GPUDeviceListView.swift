import SwiftUI

struct GPUDeviceListView: View {
    @StateObject private var viewModel = GPUViewModel()
    
    var body: some View {
        NavigationStack {
            Group {
                if viewModel.gpuDevices.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 48))
                            .foregroundColor(.orange)
                        Text("No GPU Devices Found")
                            .font(.headline)
                        Text("This device may not have Metal GPU support. Requires iOS 14+ with A12 Bionic or later.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding()
                } else {
                    List {
                        Section(header: Text("Available GPU Devices")) {
                            ForEach(viewModel.gpuDevices) { device in
                                NavigationLink(destination: GPUDeviceDetailView(device: device, viewModel: viewModel)) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack {
                                            Image(systemName: "internaldrive.fill")
                                                .foregroundColor(.blue)
                                            Text(device.name)
                                                .font(.headline)
                                            Spacer()
                                            if device.isLowPower {
                                                Label("LP", systemImage: "battery.25")
                                                    .font(.caption2)
                                                    .foregroundColor(.yellow)
                                            }
                                        }
                                        HStack(spacing: 12) {
                                            Label(device.vendorName, systemImage: "building.2")
                                                .font(.caption)
                                                .foregroundColor(.secondary)
                                            Spacer()
                                            Label("\(device.memoryGB, specifier: "%.1f") GB", 
                                                  systemImage: "internaldrive")
                                                .font(.caption)
                                                .foregroundColor(.secondary)
                                        }
                                    }
                                    .padding(.vertical, 4)
                                }
                            }
                        }
                        
                        Section(header: Text("Summary")) {
                            HStack {
                                Text("Total GPU Memory:")
                                Spacer()
                                Text(String(format: "%.1f GB", 
                                    viewModel.gpuDevices.reduce(0.0) { $0 + $1.memoryGB }))
                                    .fontWeight(.semibold)
                            }
                            HStack {
                                Text("Total Compute Units:")
                                Spacer()
                                Text(String(viewModel.gpuDevices.reduce(0) { $0 + $1.computeUnits }))
                                    .fontWeight(.semibold)
                            }
                        }
                    }
                }
            }
            .navigationTitle("GPU Devices")
            .onAppear {
                viewModel.updateDevices()
            }
            .refreshable {
                viewModel.updateDevices()
            }
        }
    }
}

#Preview {
    GPUDeviceListView()
}
