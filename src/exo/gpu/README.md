# GPU Abstraction Layer

Cross-platform GPU abstraction for distributed AI inference in exo.

## Overview

The GPU layer provides a unified interface for GPU operations across multiple platforms (NVIDIA, AMD, Apple Metal, Windows DirectML, Android/iOS). Uses event-driven async operations to integrate with exo's worker event loop.

**Design Principles**:
- **Non-blocking**: All GPU operations are async
- **Library-based**: Uses CuPy, ONNX Runtime, MLX instead of raw FFI
- **Fallback-safe**: CPU backend available if no GPU
- **Observable**: Device discovery with persistent registry

## Architecture

```
┌─────────────────────────────────────────┐
│        GPU Abstraction Layer            │
├─────────────────────────────────────────┤
│  backend.py     - Abstract interface    │
│  factory.py     - Backend selection     │
│  discovery.py   - Device discovery      │
├─────────────────────────────────────────┤
│        Platform Implementations         │
├─────────────────────────────────────────┤
│  backends/cuda_backend.py     - NVIDIA │
│  backends/rocm_backend.py     - AMD    │
│  backends/metal_backend.py    - Apple  │
│  backends/directml_backend.py - Windows│
│  backends/cpu_backend.py      - Fallback
└─────────────────────────────────────────┘
```

## Usage

### 1. Create Backend

```python
from exo.gpu.factory import GPUBackendFactory

# Auto-detect platform and create appropriate backend
backend = await GPUBackendFactory.create_backend()

# Or explicitly select backend
GPUBackendFactory.set_backend_override("cuda")
backend = await GPUBackendFactory.create_backend()
```

### 2. List Devices

```python
devices = backend.list_devices()
for device in devices:
    print(f"{device.device_id}: {device.name}")
    print(f"  Memory: {device.memory_bytes / 1e9:.1f} GB")
    print(f"  Compute: {device.compute_units} CUs")
```

### 3. Allocate Memory

```python
device_id = devices[0].device_id
handle = await backend.allocate(device_id, size_bytes=1024*1024*1024)  # 1GB
```

### 4. Copy Memory

```python
# Host to device
host_data = b"tensor data"
await backend.copy_to_device(host_data, handle)

# Device to host
result = await backend.copy_from_device(handle, offset_bytes=0, size_bytes=len(host_data))

# Device to device (P2P)
handle2 = await backend.allocate(devices[1].device_id, size_bytes=1024*1024*1024)
await backend.copy_device_to_device(handle, handle2, size_bytes=1024*1024)
```

### 5. Synchronize

```python
# Wait for all pending operations on device
await backend.synchronize(device_id)
```

### 6. Deallocate

```python
await backend.deallocate(handle)
```

### 7. Discover Devices

```python
from exo.gpu.discovery import GPUDiscoveryService

service = GPUDiscoveryService()
result = await service.discover_all_devices()

print(f"Backend: {result['backend_name']}")
print(f"Devices: {len(result['devices'])}")
for device in result['devices']:
    print(f"  {device.device_id}: {device.name}")

await service.shutdown()
```

## Backend Selection

The factory automatically selects the best available backend:

### Linux
1. CUDA (nvidia-ml-py for monitoring)
2. ROCm (HIP)
3. Vulkan (fallback)
4. CPU (always available)

### Windows
1. DirectML (via ONNX Runtime)
2. CUDA
3. ROCm
4. CPU (always available)

### macOS
1. Metal (via MLX)
2. CPU (always available)

### Android/iOS
1. TensorFlow Lite GPU
2. CPU (always available)

## Implementation Status

### Phase 1 Week 1-2 (✅ Complete - 100%)
- [x] Abstract interface (`backend.py` - 300 lines)
- [x] Backend factory (`factory.py` - 259 lines)
- [x] Discovery service (`discovery.py` - 264 lines)
- [x] CPU backend (fully implemented - 178 lines)

### Phase 1 Week 3-8 (✅ Complete - 100%)
- [x] CUDA backend via CuPy (350 lines)
- [x] ROCm backend via CuPy HIP (354 lines)
- [x] Metal backend via MLX (320 lines)
- [x] DirectML backend via ONNX Runtime (370 lines)
- [x] TensorFlow Lite GPU backend (319 lines)
- [x] Platform-specific device detection and monitoring

### Phase 1 Week 5-9 (✅ Complete - 100%)
- [x] GPU Discovery Service (functional)
- [x] Node Information Extension (StaticNodeInformation + GPU fields)
- [x] Device registration in cluster state

### Phase 1 Week 4-8 (⏳ NOT STARTED - 0%)
- [ ] GPU Inference Engine Base Class
- [ ] MLX Engine Refactoring for abstraction
- [ ] Worker integration tests

### Phase 1 Week 9-11 (⏳ NOT STARTED - 0%)
- [ ] GPU Backend Reliability Tests
- [ ] Error recovery scenarios
- [ ] Heterogeneous clustering tests

### Phase 1.5 & Phase 2 (⏳ Future)
- [ ] Worker integration
- [ ] Master placement with CSP solver
- [ ] Security & access control
- [ ] Mobile platform support

## Testing

### Unit Tests

```bash
# Test backend interface
uv run pytest src/exo/gpu/tests/test_backend_interface.py

# Test factory
uv run pytest src/exo/gpu/tests/test_factory.py

# Test discovery
uv run pytest src/exo/gpu/tests/test_discovery.py

# All GPU tests
uv run pytest src/exo/gpu/tests/
```

### Benchmarking

```python
from exo.gpu.benchmarks.cupy_evaluation import (
    benchmark_cupy_cuda_init,
    benchmark_cupy_memory_operations,
    print_evaluation_report
)

init_time = await benchmark_cupy_cuda_init()
memory_ops = await benchmark_cupy_memory_operations()
print_evaluation_report()
```

## Performance Targets

| Metric | Target | Status |
|--------|--------|--------|
| GPU initialization | <3 seconds | ⏳ Week 2 |
| Memory copy bandwidth | Near theoretical max | ⏳ Week 2 |
| Device discovery startup | <1 second | ⏳ Week 2 |
| Multi-GPU P2P copy | >80% of theoretical | ⏳ Week 2 |

## Error Handling

All backend methods raise `RuntimeError` on failure with descriptive messages:

```python
try:
    handle = await backend.allocate(device_id, size_bytes=huge_size)
except RuntimeError as e:
    print(f"Allocation failed: {e}")
    # Fall back to CPU or smaller allocation
```

## Adding a New Backend

1. Create new file in `backends/` (e.g., `my_gpu_backend.py`)
2. Implement `GPUBackend` abstract class
3. Add to `factory.py` in `_create_specific_backend()`
4. Add platform priority in `PLATFORM_BACKEND_PRIORITY`
5. Create tests in `tests/test_my_gpu.py`

Example:

```python
# backends/my_gpu_backend.py
from exo.gpu.backend import GPUBackend

class MyGPUBackend(GPUBackend):
    async def initialize(self) -> None:
        # Detect devices, initialize backend
        pass
    
    # ... implement 13 other abstract methods
```

## Dependencies

### Required
- Python 3.13+
- pydantic >= 2.11.7
- aiofiles (async I/O)

### Optional (per backend)
- `cupy-cuda11x` or `cupy-cuda12x` - CUDA backend
- `cupy` with HIP - ROCm backend
- `mlx` - Metal backend (macOS)
- `onnxruntime-directml` - DirectML backend (Windows)
- `tensorflow` - TFLite GPU backend (mobile)

## Integration with Worker

The GPU layer integrates with exo's worker:

```python
# In src/exo/worker/main.py
class Worker:
    async def run(self):
        # Initialize GPU backend
        self.gpu_backend = await GPUBackendFactory.create_backend()
        
        # Discover devices
        discovery = GPUDiscoveryService(self.gpu_backend)
        gpu_info = await discovery.discover_all_devices()
        
        # Store device info in node metadata
        self.node_info.gpu_devices = gpu_info['devices']
        
        # Emit GPU discovery event
        await self.event_sender.send(
            NodeGatheredInfo(node_id=self.node_id, info=self.node_info)
        )
```

## Integration with Master

The master uses GPU info for placement:

```python
# In src/exo/master/placement.py
from exo.gpu.placement_csp import ConstraintSatisfactionPlacement

async def place_instance(command: CreateInstance, state: State) -> State:
    # Extract GPU devices from node info
    gpu_devices = extract_gpu_devices(state)
    
    # Solve placement using CSP
    solver = ConstraintSatisfactionPlacement()
    assignment = solver.solve_placement(
        model=state.model,
        devices=gpu_devices,
        topology=state.cluster_topology
    )
    
    # Place shards on devices
    return place_shards(state, assignment)
```

## Monitoring & Observability

Each backend provides monitoring:

```python
memory_info = await backend.get_device_memory_info(device_id)
temp = await backend.get_device_temperature(device_id)
power = await backend.get_device_power_usage(device_id)
clock = await backend.get_device_clock_rate(device_id)
```

## Troubleshooting

### No devices detected

```python
from exo.gpu.factory import detect_available_backends

available = await detect_available_backends()
print(f"Available backends: {available}")
```

### CUDA not found

```bash
pip install cupy-cuda12x  # for CUDA 12.x
# or
pip install cupy-cuda11x  # for CUDA 11.x
```

### Memory allocation fails

- Check device memory usage: `nvidia-smi`
- Reduce allocation size
- Ensure device is not in use by other processes

### Slow initialization

- Expected: <500ms for CUDA via CuPy (design target <3s with all backends)
- Check GPU driver version: `nvidia-smi`
- Ensure GPU is not under high load

## References

- [Design Document](../../design.md)
- [Tasks](../../tasks.md)
- [CuPy Documentation](https://docs.cupy.dev/)
- [ONNX Runtime](https://onnxruntime.ai/)
- [MLX Documentation](https://ml-explore.github.io/mlx/)
