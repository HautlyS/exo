# Cross-Device GPU Integration: Detailed Technical Design (CORRECTED)

## Executive Summary

This document provides corrected technical architecture for cross-device GPU clustering in exo. **KEY CORRECTION**: GPU operations use event-driven task execution integrated with exo's event-sourcing model, NOT synchronous kernels. We leverage mature GPU libraries (CuPy, ONNX Runtime) instead of low-level FFI bindings.

---

## 1. GPU Abstraction Layer Architecture (Event-Driven)

### 1.1 Core GPU Backend Interface

**Location**: `src/exo/gpu/backend.py` (new module)

**CRITICAL DESIGN DECISION**: All GPU operations are non-blocking, async, and integrate with Worker's task-based execution model (see `src/exo/worker/runner/runner_supervisor.py` pattern).

```python
# Abstract base class - all GPU backends implement this
class GPUBackend(ABC):
    """Platform-agnostic GPU operations interface (async, non-blocking)"""
    
    # ===== Device Management =====
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize GPU backend, detect devices, setup resources"""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup GPU resources, release memory, close handles"""
        pass
    
    @abstractmethod
    def list_devices(self) -> List[GPUDevice]:
        """Return list of available GPU devices with properties"""
        pass
    
    @abstractmethod
    def get_device(self, device_id: str) -> GPUDevice:
        """Return specific device by ID"""
        pass
    
    # ===== Memory Management =====
    @abstractmethod
    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        """Allocate device memory, return opaque handle"""
        pass
    
    @abstractmethod
    async def deallocate(self, handle: MemoryHandle) -> None:
        """Free device memory"""
        pass
    
    @abstractmethod
    async def copy_to_device(
        self, 
        src: bytes, 
        dst_handle: MemoryHandle, 
        offset_bytes: int = 0
    ) -> None:
        """Copy host memory to device (async, non-blocking)"""
        pass
    
    @abstractmethod
    async def copy_from_device(
        self, 
        src_handle: MemoryHandle, 
        offset_bytes: int, 
        size_bytes: int
    ) -> bytes:
        """Copy device memory to host (async)"""
        pass
    
    @abstractmethod
    async def copy_device_to_device(
        self,
        src_handle: MemoryHandle,
        dst_handle: MemoryHandle,
        size_bytes: int
    ) -> None:
        """Copy between devices for multi-GPU setups"""
        pass
    
    # ===== Synchronization =====
    @abstractmethod
    async def synchronize(self, device_id: str) -> None:
        """Wait for all pending GPU operations on device"""
        pass
```

### 1.2 GPU Backend Implementations (Library-Based)

**CRITICAL**: Use mature GPU libraries instead of raw FFI bindings.

#### 1.2.1 CUDA Backend via CuPy

**Location**: `src/exo/gpu/backends/cuda_backend.py`

```python
import cupy as cp
from exo.gpu.backend import GPUBackend, GPUDevice

class CUDABackend(GPUBackend):
    """NVIDIA CUDA backend using CuPy (mature, production-ready)"""
    
    def __init__(self):
        self.cp = cp
        self._devices: Dict[str, GPUDevice] = {}
    
    async def initialize(self) -> None:
        """Detect CUDA devices via CuPy"""
        try:
            device_count = self.cp.cuda.runtime.getDeviceCount()
            logger.info(f"Detected {device_count} CUDA devices")
            
            for i in range(device_count):
                with self.cp.cuda.Device(i):
                    props = self.cp.cuda.Device(i).attributes
                    device = GPUDevice(
                        device_id=f"cuda:{i}",
                        name=str(props.get("deviceName", f"CUDA:{i}")),
                        vendor="nvidia",
                        compute_capability=f"{props.get('computeCapabilityMajor')}.{props.get('computeCapabilityMinor')}",
                        memory_bytes=int(props.get("totalGlobalMem", 0)),
                        memory_available=int(props.get("totalGlobalMem", 0)),
                        compute_units=int(props.get("multiProcessorCount", 0)),
                        tensor_core_count=0,  # CuPy doesn't expose directly
                        max_threads_per_block=int(props.get("maxThreadsPerBlock", 1024)),
                        clock_rate_mhz=int(props.get("clockRate", 1000) / 1000),
                        bandwidth_gbps=500.0,  # Approximate
                        support_level="full",
                        driver_version=str(self.cp.cuda.runtime.getDriverVersion()),
                        backend_name="cuda"
                    )
                    self._devices[device.device_id] = device
        except Exception as e:
            logger.error(f"CUDA initialization failed: {e}")
            raise
    
    async def allocate(self, device_id: str, size_bytes: int) -> MemoryHandle:
        """Allocate device memory using CuPy"""
        device_idx = int(device_id.split(":")[1])
        with self.cp.cuda.Device(device_idx):
            ptr = self.cp.cuda.memory.alloc(size_bytes)
            handle = CUPyMemoryHandle(ptr, device_idx, size_bytes)
            logger.debug(f"Allocated {size_bytes} bytes on {device_id}")
            return handle
    
    async def deallocate(self, handle: MemoryHandle) -> None:
        """Free device memory"""
        with self.cp.cuda.Device(handle.device_idx):
            handle.ptr.free()
            logger.debug(f"Deallocated memory on cuda:{handle.device_idx}")
    
    async def copy_to_device(
        self, 
        src: bytes, 
        dst_handle: MemoryHandle, 
        offset_bytes: int = 0
    ) -> None:
        """Copy host to device using CuPy"""
        with self.cp.cuda.Device(dst_handle.device_idx):
            self.cp.asarray(src).copy(dst_handle.ptr[offset_bytes:])
    
    async def copy_from_device(
        self, 
        src_handle: MemoryHandle, 
        offset_bytes: int, 
        size_bytes: int
    ) -> bytes:
        """Copy device to host"""
        with self.cp.cuda.Device(src_handle.device_idx):
            return self.cp.asnumpy(src_handle.ptr[offset_bytes:offset_bytes+size_bytes])
    
    async def synchronize(self, device_id: str) -> None:
        """Synchronize device"""
        device_idx = int(device_id.split(":")[1])
        with self.cp.cuda.Device(device_idx):
            self.cp.cuda.Stream.null.synchronize()


class CUPyMemoryHandle:
    """Opaque CUDA device memory handle via CuPy"""
    def __init__(self, ptr, device_idx: int, size_bytes: int):
        self.ptr = ptr
        self.device_idx = device_idx
        self.size_bytes = size_bytes
```

**Advantages over raw FFI**:
- ✅ CuPy is battle-tested (NumPy ecosystem)
- ✅ Built-in async support
- ✅ Memory management proven
- ✅ Implementation time: 3-4 days (vs. 12+ for raw FFI)

#### 1.2.2 ROCm Backend via CuPy

**Location**: `src/exo/gpu/backends/rocm_backend.py`

```python
import cupy as cp

class ROCmBackend(GPUBackend):
    """AMD ROCm backend using CuPy HIP interface"""
    
    async def initialize(self) -> None:
        """Detect ROCm devices via CuPy"""
        device_count = cp.cuda.runtime.getDeviceCount()  # CuPy uses HIP transparently
        for i in range(device_count):
            # Query HIP device properties
            # Device detection same as CUDA but identifies as AMD
            pass
    
    # Implementation mirrors CUDABackend but identifies as "rocm" backend
```

#### 1.2.3 DirectML Backend via ONNX Runtime

**Location**: `src/exo/gpu/backends/directml_backend.py`

```python
import onnxruntime as ort

class DirectMLBackend(GPUBackend):
    """Windows DirectML backend via ONNX Runtime"""
    
    async def initialize(self) -> None:
        """Enumerate DirectML adapters"""
        # ONNX Runtime abstracts DirectML
        # Query available EP (execution providers)
        pass
```

#### 1.2.4 Android Vulkan Backend via TensorFlow Lite

**Location**: `src/exo/gpu/backends/android_backend.py`

```python
# Use TensorFlow Lite GPU delegate instead of raw Vulkan
# TensorFlow Lite handles NNAPI/Vulkan abstraction
```

---

## 2. Device Discovery System (Corrected)

**Location**: `src/exo/gpu/discovery.py`

GPU discovery runs at Worker startup before runner initialization. Uses CuPy/ONNX to detect devices instead of command-line parsing.

```python
class GPUDiscoveryService:
    """Detects available GPU devices on system startup"""
    
    async def discover_all_devices(self) -> GPUInventory:
        """
        Main discovery entry point.
        Tries each backend in platform-specific priority order.
        """
        
        backends_to_try = self._get_platform_backends()
        discovered = []
        
        for backend_name in backends_to_try:
            try:
                backend = await self._try_initialize_backend(backend_name)
                devices = backend.list_devices()
                discovered.extend(devices)
                logger.info(f"Discovered {len(devices)} devices via {backend_name}")
            except Exception as e:
                logger.debug(f"{backend_name} discovery failed: {e}")
                continue
        
        return GPUInventory(
            discovered_at=datetime.now(),
            devices=discovered,
            platform=platform.system(),
            primary_backend=discovered[0].backend_name if discovered else "cpu",
        )
    
    def _get_platform_backends(self) -> List[str]:
        """Platform-specific backend priority"""
        if platform.system() == "Linux":
            return ["cuda", "rocm"]  # Try CUDA first
        elif platform.system() == "Windows":
            return ["directml", "cuda"]
        elif platform.system() == "Darwin":
            return ["metal"]  # Via MLX
        elif platform.system() == "Android":
            return ["android"]  # TensorFlow Lite
        else:
            return []
```

---

## 3. Heterogeneous Device Orchestration (CSP-Based Placement)

**CRITICAL**: Simple linear scoring fails in real heterogeneous clusters. Use Constraint Satisfaction Problem solver.

**Location**: `src/exo/master/placement_csp.py` (new file)

```python
class ConstraintSatisfactionPlacement:
    """
    Use CSP solver for optimal shard placement.
    
    Variables: shard_i → device_j
    Constraints:
    1. Precision compatibility: output type layer i → input type layer i+1
    2. Memory: sum(layer_memory) <= device.memory
    3. Bandwidth: output_size / edge_bandwidth <= max_latency
    4. Backend capability: all ops in shard supported by device.backend
    """
    
    def solve_placement(
        self,
        model: ModelMetadata,
        devices: List[GPUDevice],
        topology: GPUAwareTopology
    ) -> Dict[LayerRange, DeviceAssignment]:
        """Solve shard placement using backtracking + constraint propagation"""
        
        # Step 1: Compute shard boundaries
        shards = self._compute_shard_boundaries(model, devices)
        
        # Step 2: Build constraint graph
        constraints = []
        for i in range(len(shards)):
            # Precision compatibility
            if i + 1 < len(shards):
                constraints.append(
                    PrecisionMatch(shards[i], shards[i+1])
                )
            
            # Memory constraints
            for device in devices:
                constraints.append(
                    MemoryFits(shards[i], device)
                )
            
            # Bandwidth constraints (cross-device)
            for src_dev in devices:
                for dst_dev in devices:
                    if src_dev.node_id != dst_dev.node_id:
                        constraints.append(
                            BandwidthOK(shards[i], src_dev, dst_dev, topology)
                        )
        
        # Step 3: Backtracking search
        solution = self._backtrack(shards, devices, constraints, {})
        
        if solution:
            return solution
        else:
            # Fallback: greedy packing
            return self._greedy_fallback(shards, devices)
    
    def _backtrack(
        self,
        shards: List[Shard],
        devices: List[GPUDevice],
        constraints: List[Constraint],
        assignment: Dict[Shard, GPUDevice]
    ) -> Optional[Dict[Shard, GPUDevice]]:
        """Backtracking search with constraint propagation"""
        
        if len(assignment) == len(shards):
            return assignment  # All shards assigned
        
        # Select next unassigned shard
        next_shard = next(s for s in shards if s not in assignment)
        
        for device in devices:
            # Check if assigning next_shard to device violates constraints
            if all(c.check(next_shard, device, assignment) for c in constraints):
                assignment[next_shard] = device
                
                result = self._backtrack(
                    shards, devices, constraints, assignment
                )
                if result:
                    return result
                
                del assignment[next_shard]
        
        return None
```

---

## 4. Mobile Thermal Management (Prediction-Based)

**CRITICAL**: Don't react to thermal throttling, predict it and adapt BEFORE hitting limit.

**Location**: `src/exo/worker/thermal_executor.py` (new file)

```python
class ThermalModel:
    """Physics-based thermal RC model for device"""
    
    def __init__(self, device_id: str):
        # Device-specific thermal parameters (calibrated at factory init)
        self.thermal_capacity = device_config[device_id].thermal_capacity  # J/°C
        self.heat_transfer_coeff = device_config[device_id].heat_transfer  # W/°C
        self.ambient_temp = device_config[device_id].ambient_temp  # °C
    
    def predict_temperature(
        self,
        current_temp: float,
        compute_power_watts: float,
        duration_seconds: float
    ) -> float:
        """
        Predict max temperature using RC thermal model:
        dT/dt = (P - h*(T - T_ambient)) / C
        
        Returns: maximum predicted temperature in celsius
        """
        
        T = current_temp
        dt = 0.01  # 10ms timesteps
        max_T = current_temp
        
        for _ in range(int(duration_seconds / dt)):
            dT_dt = (
                compute_power_watts - 
                self.heat_transfer_coeff * (T - self.ambient_temp)
            ) / self.thermal_capacity
            T += dT_dt * dt
            max_T = max(max_T, T)
        
        return max_T


class AdaptiveInferenceExecutor:
    """Execute inference with thermal awareness"""
    
    THERMAL_CRITICAL = 43.0  # °C - device-specific
    THERMAL_SAFE = 38.0      # °C - leave headroom
    
    async def execute_with_thermal_awareness(
        self,
        model: ModelMetadata,
        layers: List[ModelLayer]
    ) -> InferenceResult:
        """Execute inference while respecting thermal envelope"""
        
        current_temp = await self.monitor.get_temperature()
        
        for layer in layers:
            # Estimate layer compute power
            power_watts = self._estimate_power(layer)
            duration_sec = self._estimate_duration(layer)
            
            # Predict thermal trajectory
            max_predicted_temp = self.thermal_model.predict_temperature(
                current_temp,
                power_watts,
                duration_sec
            )
            
            if max_predicted_temp > self.THERMAL_SAFE:
                # Pause BEFORE computation to cool down
                pause_seconds = self._calculate_pause(
                    max_predicted_temp,
                    self.THERMAL_SAFE
                )
                logger.info(f"Thermal prediction {max_predicted_temp:.1f}°C, pausing {pause_seconds:.1f}s")
                await asyncio.sleep(pause_seconds)
            
            # Execute layer
            result = await self._execute_layer(layer)
            current_temp = max_predicted_temp
        
        return result
    
    def _calculate_pause(self, current: float, target: float) -> float:
        """Calculate pause time to cool from current to target"""
        
        tau = self.thermal_model.thermal_capacity / self.thermal_model.heat_transfer_coeff
        ratio = (target - self.ambient_temp) / (current - self.ambient_temp)
        
        if ratio <= 0:
            return 0.0
        
        pause_time = -tau * math.log(ratio)
        return max(0.1, pause_time)
```

---

## 5. Security Architecture (NEW - Phase 1.5)

**CRITICAL**: GPU access control must be integrated from Day 1, not Phase 4.

### 5.1 GPU Access Control

**Location**: `src/exo/security/gpu_access.py` (new file)

```python
@dataclass(frozen=True)
class GPUAccessToken(TaggedModel):
    """Token authorizing GPU access for a specific user/session"""
    user_id: str
    gpu_device_id: str
    issued_at: datetime
    expires_at: datetime
    access_id: str  # UUID for audit logging
    scopes: List[str] = field(default_factory=list)  # e.g., ["allocate", "compute"]


class GPUAccessController:
    """Control and audit GPU resource access"""
    
    async def request_gpu_access(
        self,
        user_id: str,
        gpu_device_id: str,
        duration_seconds: int,
        purpose: str
    ) -> GPUAccessToken:
        """Allocate GPU access to user"""
        
        token = GPUAccessToken(
            user_id=user_id,
            gpu_device_id=gpu_device_id,
            issued_at=datetime.now(tz=timezone.utc),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=duration_seconds),
            access_id=str(uuid4())
        )
        
        # Audit log
        await self._audit_log.record(
            event="gpu_access_granted",
            user_id=user_id,
            gpu_device=gpu_device_id,
            purpose=purpose,
            token_id=token.access_id
        )
        
        return token
    
    async def verify_token(self, token: GPUAccessToken) -> bool:
        """Verify token is valid and not expired"""
        return (
            token.expires_at > datetime.now(tz=timezone.utc) and
            token.access_id in self._active_tokens
        )
    
    async def revoke_token(self, token: GPUAccessToken):
        """Revoke GPU access"""
        self._active_tokens.discard(token.access_id)
        
        await self._audit_log.record(
            event="gpu_access_revoked",
            token_id=token.access_id
        )
```

### 5.2 Secure Inter-Device Communication

**Location**: `src/exo/networking/secure_quic.py` (new file)

```python
class SecureQuicTransport:
    """QUIC transport with TLS 1.3 peer authentication"""
    
    async def initialize(self):
        """Setup TLS certificates using node's libp2p keypair"""
        
        # Convert libp2p keypair to TLS certificate
        self.node_keypair = get_node_id_keypair()
        self.tls_cert = self._libp2p_to_tls_cert(self.node_keypair)
        
        # Load peer certificate store
        self.peer_ca = await self._load_peer_certificates()
    
    async def send_tensor_authenticated(
        self,
        peer_id: str,
        tensor: TensorBuffer,
        access_token: GPUAccessToken
    ) -> None:
        """Send tensor with peer verification"""
        
        # Verify peer certificate
        peer_cert = await self._fetch_peer_certificate(peer_id)
        if not self._verify_certificate(peer_cert):
            raise SecurityError(f"Peer {peer_id} certificate verification failed")
        
        # Establish TLS 1.3 connection
        async with self._establish_tls_connection(peer_id, peer_cert) as conn:
            await conn.send(
                EncryptedTensor(
                    data=tensor,
                    access_token=access_token  # For audit trail
                )
            )
```

---

## 6. File Organization

Complete directory structure:

```
src/exo/gpu/                          # GPU ABSTRACTION LAYER
├── __init__.py
├── backend.py                         # Abstract GPUBackend interface
├── factory.py                         # Backend selection logic
├── discovery.py                       # Device discovery service
├── monitoring.py                      # GPU telemetry
├── backends/
│   ├── __init__.py
│   ├── cuda_backend.py               # CUDA via CuPy
│   ├── rocm_backend.py               # ROCm via CuPy
│   ├── metal_backend.py              # Metal (macOS/iOS) via MLX
│   ├── directml_backend.py           # DirectML via ONNX Runtime
│   └── android_backend.py            # TensorFlow Lite GPU
└── tests/
    ├── test_backend_interface.py
    ├── test_discovery.py
    ├── test_reliability.py           # Kernel timeout, failures
    └── test_precision_loss.py

src/exo/master/                       # PLACEMENT & ORCHESTRATION
├── placement_csp.py                  # CSP-based placement (NEW)
├── placement.py                      # (existing, integrate CSP)
└── tests/
    └── test_placement_csp.py

src/exo/worker/                       # WORKER INTEGRATION
├── thermal_executor.py               # Thermal-aware execution (NEW)
├── layer_offloading.py               # Layer eviction management
├── engines/
│   ├── gpu_engine.py                # GPU inference engine (NEW)
│   └── mlx/                         # (refactored for abstraction)
└── tests/
    └── test_thermal_adaptation.py

src/exo/security/                     # SECURITY (NEW)
├── gpu_access.py                     # GPU access control
├── audit_log.py                      # Audit logging
└── tests/
    └── test_gpu_access_control.py

src/exo/networking/                   # NETWORKING
├── secure_quic.py                    # TLS 1.3 QUIC transport (NEW)
├── quic/
│   └── gpu_transport.py             # GPU-optimized QUIC
└── discovery/
    └── gpu_discovery_protocol.py     # mDNS GPU services
```

---

## 7. Integration Points with Existing Exo

### 7.1 Worker Integration

GPU backend integrated at Worker startup:

```python
# src/exo/worker/main.py (existing)
class Worker:
    async def run(self):
        # New: Initialize GPU backend before runners
        self.gpu_backend = await GPUBackendFactory.create_backend()
        self.gpu_discovery = GPUDiscoveryService(self.gpu_backend)
        
        # Emit GPU discovery event
        gpu_info = await self.gpu_discovery.discover_all_devices()
        await self.event_sender.send(
            NodeGatheredInfo(
                node_id=self.node_id,
                info=GatheredInfo(
                    gpu_devices=gpu_info.devices,
                    gpu_backend=gpu_info.primary_backend
                )
            )
        )
        
        # Start runners with GPU context
        await tg.start_soon(self._run_gpu_tasks)
```

### 7.2 Master Integration

Master uses CSP-based placement:

```python
# src/exo/master/placement.py (modified)
async def place_instance(command: CreateInstance, state: State) -> State:
    # Use CSP placement instead of greedy
    placement_solver = ConstraintSatisfactionPlacement()
    
    shard_assignments = placement_solver.solve_placement(
        model=state.model,
        devices=extract_gpu_devices(state),
        topology=state.gpu_cluster_topology
    )
    
    # Rest of placement logic uses shard_assignments
    return state
```

### 7.3 Node Info Extension

```python
# src/exo/utils/info_gatherer/info_gatherer.py (modified)
@dataclass(frozen=True)
class StaticNodeInformation(TaggedModel):
    # ... existing fields ...
    
    # GPU fields (NEW)
    gpu_backend: str                        # "cuda", "rocm", "metal", etc.
    gpu_devices: List[GPUCapabilities]
    gpu_discovery_timestamp: datetime
    primary_gpu_device_id: str
```

---

## Key Design Decisions

1. **Library-Based GPU Support**: Use CuPy, ONNX Runtime, TensorFlow Lite instead of raw FFI
   - Reduces implementation time: 12 days → 3-4 days per backend
   - Production-tested error handling
   - Better community support

2. **Event-Driven Architecture**: GPU ops emit events, integrate with Worker task model
   - Avoids deadlocks in async system
   - Proper cancellation/cleanup
   - Integrates with existing event sourcing

3. **CSP-Based Placement**: Constraint satisfaction for heterogeneous clusters
   - Optimal shard assignments
   - Precision compatibility guaranteed
   - Bandwidth constraints respected

4. **Thermal Prediction**: Proactive not reactive
   - Predict overheating before it happens
   - Pause early, avoid oscillation
   - Better user experience

5. **Security from Day 1**: GPU access control in Phase 1.5
   - Token-based access
   - Audit logging for all operations
   - TLS 1.3 peer authentication
