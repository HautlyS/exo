# Cross-Device GPU Integration Requirements (CORRECTED)

## Executive Summary

This document specifies requirements for implementing full cross-device GPU clustering. **KEY CORRECTIONS**: Performance targets are realistic, security is Phase 1.5 (not Phase 4), and GPU operations use library-based backends (CuPy, ONNX) not raw FFI.

---

## 1. Functional Requirements

### 1.1 Device Discovery and Identification

**REQ-1.1.1** Automatic Platform-Agnostic Device Discovery
- System must discover all available GPU devices without user intervention
- Must handle dynamic attachment/detachment (USB/Thunderbolt expansion)
- Persistent registry indexed by unique identifiers across reboots

**REQ-1.1.2** GPU Capability Detection  
Per discovered GPU:
- Vendor (NVIDIA, AMD, Apple, Intel, Qualcomm), model, architecture family
- Available VRAM in bytes
- Compute capability/SM count or architecture-equivalent metrics
- Driver version and runtime package status
- Support classification: fully supported, partial, experimental, unsupported

**REQ-1.1.3** Platform-Specific Discovery Mechanisms
- **Linux**: Use CuPy for CUDA, CuPy HIP for ROCm (vs. nvidia-smi parsing)
- **Windows**: Use ONNX Runtime for DirectML device enumeration
- **macOS**: Existing Metal device enumeration via MLX
- **Android**: TensorFlow Lite GPU backend
- **iOS**: Metal device enumeration within app sandbox

### 1.2 GPU Backend Abstraction

**REQ-1.2.1** Async, Non-Blocking GPU Interface
All GPU operations flow through platform-agnostic backend interface supporting:
- Device initialization and cleanup with resource tracking
- Memory allocation with explicit ownership and deallocation guarantees
- **Async/non-blocking data transfers** (host-to-device, device-to-device, device-to-host)
- Synchronization primitives (events, fences)
- **Task-based inference execution** (async iterators yielding results)

**REQ-1.2.2** Required Backend Implementations
- **CUDA**: NVIDIA GPUs via CuPy (not raw FFI)
- **ROCm**: AMD GPUs via CuPy HIP backend
- **Metal**: macOS/iOS via existing MLX integration
- **DirectML**: Windows cross-vendor via ONNX Runtime
- **TensorFlow Lite**: Android GPU delegate
- **CPU Fallback**: When no GPU available

**REQ-1.2.3** Runtime Backend Selection
- Automatic selection based on discovered hardware (try CUDA → ROCm → CPU)
- User override capability via configuration
- Graceful fallback to CPU execution when GPU unavailable
- All backend implementations testable with synthetic workloads

### 1.3 Cross-Platform Device Communication

**REQ-1.3.1** Zero-Configuration Networking
Automatic peer discovery using platform-appropriate mechanisms:
- **Linux/macOS**: mDNS with service registration (`_exo-gpu._tcp`)
- **Windows**: WS-Discovery or mDNS fallback
- **Android**: NSD (Network Service Discovery)
- **iOS**: Bonjour/mDNS within app sandbox, Multipeer Connectivity fallback
- **Universal fallback**: Manual peer entry via IP:port

**REQ-1.3.2** Multi-Protocol Transport Support
- **Primary**: QUIC with TLS 1.3 for peer authentication
- **Secondary**: gRPC/HTTP2 for reliability
- **Tertiary**: TCP for maximum compatibility
- **Specialized**: RDMA/RoCE when available (Thunderbolt 5, InfiniBand)

**REQ-1.3.3** Network Characteristic Measurement
Per-peer tracking of:
- Latency (RTT in milliseconds)
- Bandwidth (throughput in Mbps)
- Packet loss percentage
- Path stability/jitter

### 1.4 Heterogeneous Device Orchestration

**REQ-1.4.1** Complete Cluster State Tracking
Master node maintains:
- Device inventory (GPU model, VRAM, compute units, driver version)
- Network topology (latency/bandwidth between all peer pairs)
- Device operational state (idle, computing, thermal throttled, offline)
- Per-device resource utilization (memory used/free, compute %, temperature)

**REQ-1.4.2** Intelligent Sharding Decisions (CSP-Based)
Algorithms must consider:
- Layer-wise compute requirements and data dependencies
- Device memory capacity vs. current utilization
- Network bandwidth and latency between peers
- **Compute capability and precision compatibility** (ops supported on backend)
- **Cross-device communication bottlenecks** (output size vs. bandwidth)
- Thermal headroom tracking on mobile devices

**REQ-1.4.3** Parallelization Strategies
Support multiple approaches:
- **Tensor Parallelism**: For similar-capacity devices with high-bandwidth interconnect
- **Pipeline Parallelism**: For heterogeneous compute capability
- **Hybrid**: Combining both strategies
- **Dynamic Re-sharding**: Adapting when devices join/leave cluster

**REQ-1.4.4** Scheduling Optimization Goals
- Minimize inter-device communication volume
- Balance computational load fairly across devices
- Respect device memory constraints absolutely
- Minimize critical path latency
- Ensure precision compatibility across device chain

### 1.5 Mobile-Specific Constraints

**REQ-1.5.1** Mobile Environment Monitoring
On Android/iOS, system tracks:
- Device thermal state (normal, warm, throttled, critical)
- Battery percentage and charging state
- Foreground application state
- Available system memory from other applications

**REQ-1.5.2** Thermal Management (Prediction-Based)
- **Predict** thermal trajectory using RC thermal model
- Pause inference BEFORE thermal limit reached (proactive, not reactive)
- Reduce compute precision when necessary
- Graceful pause/resume without data loss

**REQ-1.5.3** Android Background Handling
- Gracefully handle Doze mode suspension
- Respect background processing limitations
- Resume inference when app returns to foreground
- Conservative wake lock usage

**REQ-1.5.4** Memory Efficiency
- Layer-by-layer model offloading (load/unload as needed)
- Quantization support (8-bit, 4-bit) with dynamic precision scaling
- Immediate GPU cache clearing after inference

---

## 2. User Experience Requirements

### 2.1 Installation and Setup

**REQ-2.1.1** Zero-Configuration Clustering
- Start exo on multiple devices → automatic discovery via mDNS
- Cluster formation without manual peer configuration
- Dashboard immediately accessible at standard URL/port

**REQ-2.1.2** Platform-Specific Installation
- **macOS**: Continue native app bundle
- **Linux**: Single `uv run exo` command or system package
- **Windows**: MSI installer with system tray integration
- **Android**: Google Play Store
- **iOS**: App Store

### 2.2 Dashboard and Monitoring

**REQ-2.2.1** GPU Cluster Visualization
- Real-time display of all discovered devices with GPU specs
- Network topology visualization (latency/bandwidth between peers)
- Per-device resource utilization: GPU %, memory, temperature
- Model shard placement across GPU devices

**REQ-2.2.2** Alerting and Diagnostics
- Visual indicators for mobile device thermal throttling
- GPU driver failure/incompatibility notifications
- Detailed logs for network connectivity issues
- Performance warnings for poorly-balanced heterogeneous clusters

### 2.3 Model Management

**REQ-2.3.1** Intuitive Model Selection
- Selection from standard sources (HuggingFace Hub, Ollama)
- Automatic optimal sharding based on cluster composition
- Optional user override for sharding strategy
- Per-device download progress indication

**REQ-2.3.2** Graceful Device Removal Handling
- Pause inference gracefully if device leaves mid-inference
- Auto-resume when device rejoins (without full reload)
- Dashboard shows missing shards and affected devices

---

## 3. Integration Requirements

### 3.1 Codebase Integration Points

**REQ-3.1.1** Worker Layer Integration (`src/exo/worker/`)
- GPU backend factory initializes at Worker startup
- Runner engines use GPU backend abstraction
- GPU operations emit events to event queue (non-blocking)

**REQ-3.1.2** Node Information Extension (`src/exo/utils/info_gatherer/`)
- `StaticNodeInformation` extended with GPU-specific fields
- `NodeConfig` includes backend selection and capability flags
- GPU discovery runs during node startup before runner initialization

**REQ-3.1.3** Topology Integration (`src/exo/shared/topology.py`)
- Network topology uses measured GPU-to-GPU latency/bandwidth
- Topology analysis incorporates GPU memory constraints
- Heterogeneous device scoring integrated into placement

**REQ-3.1.4** Master Orchestration (`src/exo/master/`)
- CSP-based shard placement algorithm
- Event sourcing tracks GPU state (thermal, VRAM usage)
- Backend compatibility verification between peers

**REQ-3.1.5** Security Integration (NEW - Phase 1.5)
- GPU access control tokens for per-user GPU allocation
- Audit logging of all GPU operations
- TLS 1.3 peer authentication for inter-device communication

### 3.2 External Dependencies

**REQ-3.2.1** GPU Support Libraries (Library-Based, NOT Raw FFI)
- **CUDA**: `cupy-cuda12x>=13.0` (CuPy, not raw CUDA FFI)
- **ROCm**: CuPy HIP backend (not raw hip-rs)
- **Metal**: Existing MLX integration (no new dependencies)
- **DirectML**: `onnxruntime-gpu>=1.18` (ONNX Runtime abstraction)
- **TensorFlow Lite**: `tensorflow>=2.14` (Android GPU)
- **mDNS**: `zeroconf>=0.132.0` or `mdns-sd` crate

**REQ-3.2.2** Dependency Constraints
- Maintain Python 3.13+ requirement
- Mature, production-tested libraries only (no experimental FFI)
- MIT/Apache2/BSD licensing only
- Minimal native dependency footprint

### 3.3 Platform-Specific Integration

**REQ-3.3.1** Linux Integration
- CuPy/ONNX abstracts GPU driver variations
- System service file for daemon execution
- GPU driver compatibility matrix in documentation

**REQ-3.3.2** Windows Integration
- Visual C++ Redistributable transparent to user
- ONNX Runtime DirectML provider used
- Windows service management via `pywin32`
- System tray icon user control

**REQ-3.3.3** macOS Integration
- Continue native app approach with Metal backend
- No changes to secure enclave handling

**REQ-3.3.4** Android Integration
- TensorFlow Lite GPU delegate for compute
- Custom launcher activity with runtime permissions
- Material Design 3 UI matching platform
- ABI targets: arm64-v8a, armeabi-v7a, x86_64

**REQ-3.3.5** iOS Integration
- Native Swift app using Metal backend
- App Groups for shared model storage
- Network framework for peer discovery (sandbox compliance)

---

## 4. Performance Requirements (CORRECTED)

**REQ-4.1** Device-to-Device Latency Targets
- **Wired (Ethernet/Thunderbolt)**: <10ms RTT ✅ Achievable
- **WiFi (5GHz)**: <50ms RTT ✅ Achievable
- **Mobile networks**: <200ms RTT ✅ Acceptable with adaptive perf

**REQ-4.2** Data Transfer Throughput Targets
- **Wired**: >1Gbps ✅ Achievable (PCIe 5.0 = 128GB/s)
- **WiFi**: >100Mbps ✅ Achievable
- **Mobile**: Graceful degradation below 50Mbps

**REQ-4.3** GPU Initialization Overhead (CORRECTED)
- **Single device initialization**: <3 seconds (was <2s)
  - CUDA runtime: ~1.0s
  - ROCm runtime: ~1.5s
  - Device capability query: ~0.5s
  - Total: ~2-2.5s average ✅ Achievable

- **Multi-GPU initialization** (4 devices): <5 seconds
  - Can run in parallel per device ✅

**REQ-4.4** Inference Throughput
- <5% overhead for distributed inference vs. single-device ✅ Achievable (well-designed)
- **Heterogeneous cluster speedup**: minimum 1.3x for 2-device mixed clusters (CORRECTED from 1.5x)
  - Example: A100 (100 TFLOPS) + Adreno (2 TFLOPS)
  - Realistic speedup: ~1.3x with careful placement

---

## 5. Testing and Validation Requirements

**REQ-5.1** Unit Test Coverage
- GPU backend abstraction: 100% interface coverage
- Device discovery: 95%+ platform coverage
- Memory management: 100% allocation/deallocation paths
- Network communication: 95%+ protocol negotiation

**REQ-5.2** Integration Testing
- All backend combinations tested (CUDA+ROCm on Linux, Metal on macOS)
- Mixed-platform clustering: 2-4 device clusters across OS types
- Dynamic device add/remove with cluster resilience
- Network failure scenarios: latency spikes, packet loss, offline devices
- **Reliability tests**: GPU kernel timeout recovery, multi-GPU P2P failures

**REQ-5.3** Performance Validation
- Heterogeneous cluster speedup benchmarks
- Thermal scaling validation on mobile (automated temperature injection)
- Memory stress tests (repeated inference cycles)
- Network protocol overhead measurement vs. baseline
- **Precision loss validation**: quantization accuracy across device chain

**REQ-5.4** Compatibility Validation
- Matrix testing: [GPU type] × [GPU model] × [Driver version] × [OS]
- Minimum 10 device pairs per GPU type for clustering tests
- Automated driver compatibility detection

---

## 6. Security and Privacy Requirements (NEW - Phase 1.5)

**REQ-7.1** GPU Access Control
- Token-based GPU allocation (per user/session)
- Tokens include expiration and scopes (allocate, compute)
- Revocation immediately stops GPU operations
- No data leakage between concurrent inference jobs

**REQ-7.2** Network Security
- TLS 1.3 for inter-device communication
- Peer certificate verification (mutual authentication)
- Forward secrecy (session key rotation)
- Rate limiting to prevent DoS

**REQ-7.3** Audit Logging
- All GPU operations logged (allocate, deallocate, compute)
- User tracking (who executed what)
- Tamper-evident append-only logs
- Log rotation and archival policies

**REQ-7.4** Mobile-Specific Security
- App sandbox restriction compliance
- No privilege elevation beyond declared capabilities
- Clear user consent for network access and model caching
- Runtime permission requests (Android/iOS)

---

## 7. Success Criteria

A successful implementation must achieve:

1. **Functional Completeness**: GPU clustering on all platforms (Linux/Windows/macOS/Android/iOS)
2. **User Experience**: Zero-configuration clustering with intuitive dashboard
3. **Performance**: >1.3x speedup in heterogeneous clusters vs. single device
4. **Stability**: 99.9% uptime with automatic re-sharding on device failure
5. **Security**: Token-based access control, TLS authentication, audit logging
6. **Test Coverage**: >95% code coverage with integration tests across platforms
7. **Reliability**: Handles network failures, device removal, driver issues gracefully
8. **Production-Ready**: <3s GPU init, thermal prediction working, CSP placement optimal
