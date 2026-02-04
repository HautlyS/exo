# GPU Integration Guide

This guide covers GPU support in exo across different platforms.

## Overview

Exo supports GPU acceleration on the following platforms:

| Platform | GPU Backend | Status | Notes |
|:---|:---|:---|:---|
| **macOS** | Metal (MLX) | ✅ Production | Optimized for Apple Silicon |
| **Linux (NVIDIA)** | CUDA (CuPy) | ✅ Production | Tested on CUDA 11.x and 12.x |
| **Linux (AMD)** | ROCm (HIP) | ✅ Production | Requires ROCm 5.7+ |
| **Windows (NVIDIA)** | CUDA (CuPy) | ✅ Production | Tested on Windows 10/11 |
| **Windows (AMD)** | DirectML + ROCm | 🟡 Beta | Partial support |
| **Android** | Vulkan | 📋 Planned | Coming in Phase 2 |
| **iOS** | Metal | 📋 Planned | Coming in Phase 2 |

## Installation & Setup

### macOS (Metal/MLX)

No additional setup required! MLX is built-in with Apple Silicon Macs.

```bash
# Verify GPU is detected
uv run python -c "from exo.gpu.factory import GPUBackendFactory; import asyncio; print(asyncio.run(GPUBackendFactory.create_backend()))"
```

### Linux with NVIDIA GPU

#### 1. Install CUDA Toolkit

```bash
# Ubuntu/Debian
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt-get update
sudo apt-get install cuda-toolkit

# Or via conda
conda install -c nvidia/label/cuda-12.4.0 cuda
```

#### 2. Install CuPy

```bash
# For CUDA 12.x
pip install cupy-cuda12x

# For CUDA 11.x
pip install cupy-cuda11x
```

#### 3. (Optional) Install nvidia-ml-py for monitoring

```bash
pip install nvidia-ml-py
```

#### 4. Verify Installation

```bash
python -c "import cupy as cp; print(f'CUDA {cp.cuda.runtime.getDeviceCount()} devices found')"
```

### Linux with AMD GPU

#### 1. Install ROCm

```bash
# Ubuntu/Debian
wget -q -O - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
sudo apt-get update
sudo apt-get install rocm-dkms

# Check installation
rocm-smi
```

#### 2. Install CuPy with HIP Support

```bash
pip install cupy[hip]
```

#### 3. Set ROCm environment

```bash
export PATH=$PATH:/opt/rocm/bin
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/opt/rocm/lib
```

### Windows with NVIDIA GPU

#### 1. Install CUDA Toolkit

Download from: https://developer.nvidia.com/cuda-downloads

#### 2. Install CuPy

```bash
pip install cupy-cuda12x
```

## GPU Auto-Detection

Exo automatically detects available GPUs on startup:

```python
from exo.gpu.factory import GPUBackendFactory
import asyncio

async def main():
    backend = await GPUBackendFactory.create_backend()
    devices = backend.list_devices()
    
    for device in devices:
        print(f"Device: {device.name}")
        print(f"  Vendor: {device.vendor}")
        print(f"  Memory: {device.memory_bytes / 1024**3:.1f} GB")
        print(f"  Compute Units: {device.compute_units}")
        print(f"  Bandwidth: {device.bandwidth_gbps:.1f} GB/s")

asyncio.run(main())
```

## Performance Tuning

### Memory Management

Exo manages GPU memory automatically, but you can optimize by:

1. **Pre-allocate memory pools** for models to reduce fragmentation:
   ```python
   # Currently automatic, but can be customized in future versions
   ```

2. **Monitor memory usage**:
   ```python
   info = await backend.get_device_memory_info(device_id)
   print(f"Available: {info['available_bytes'] / 1024**3:.1f} GB")
   print(f"Used: {info['used_bytes'] / 1024**3:.1f} GB")
   ```

3. **Use model quantization** to reduce memory:
   - 8-bit quantization: 25% memory savings
   - 4-bit quantization: 50% memory savings
   - (Future feature)

### Bandwidth Optimization

For optimal performance in multi-GPU clusters:

1. **Enable P2P transfers** when available (automatically done)
2. **Use RDMA** over fast interconnects (macOS Thunderbolt, NVLink)
3. **Consider network topology** when placing model shards

### Temperature Management

Monitor GPU temperature:

```python
# Get current temperature
temp = await backend.get_device_temperature(device_id)
if temp and temp > 80:
    print(f"GPU getting hot: {temp}°C")

# Get power usage
power = await backend.get_device_power_usage(device_id)
print(f"Current power: {power:.1f}W")
```

## Troubleshooting

### "No CUDA devices detected"

**Problem**: CUDA backend initialized but no devices found

**Solutions**:
1. Verify CUDA installation: `nvidia-smi`
2. Check CUDA version: `nvcc --version`
3. Verify CuPy installation: `python -c "import cupy; print(cupy.cuda.Device())"`
4. Check CUDA path: `echo $CUDA_PATH`
5. Try CPU fallback: exo will automatically use CPU if no GPU available

### "CuPy not installed"

**Problem**: ImportError for CuPy

**Solution**:
```bash
# Install correct version for your CUDA
pip install cupy-cuda12x  # For CUDA 12.x
pip install cupy-cuda11x  # For CUDA 11.x
pip install cupy[hip]      # For ROCm
```

### "Out of memory (OOM) during inference"

**Problem**: Model too large for GPU memory

**Solutions**:
1. Check available memory: `rocm-smi` or `nvidia-smi`
2. Use quantization (8-bit or 4-bit)
3. Use model sharding across multiple GPUs
4. Reduce batch size
5. Switch to CPU (slower but works)

### Poor Performance

**Problem**: GPU inference slower than expected

**Checklist**:
1. Verify GPU is being used: Check `nvidia-smi` / `rocm-smi` during inference
2. Check memory bandwidth: `rocm-smi --showproductname` shows bandwidth
3. Monitor temperature: Thermal throttling may reduce speed
4. Check for other GPU processes: `nvidia-smi` or `rocm-smi`
5. Use profiling tools: `nsys` (NVIDIA) or `rocprof` (AMD)

### "Driver version mismatch"

**Problem**: CUDA driver doesn't match toolkit version

**Solution**:
```bash
# Update NVIDIA driver
sudo apt install nvidia-driver-XXX  # Replace XXX with version

# Update ROCm
sudo apt install rocm-dkms
```

## Testing GPU Support

Run the GPU validation tests:

```bash
# Test telemetry aggregation (no hardware required)
uv run pytest tests/test_telemetry_aggregation.py -v

# Test CUDA backend (requires NVIDIA GPU)
uv run pytest tests/cuda_validation.py -v

# Test ROCm backend (requires AMD GPU)
uv run pytest tests/rocm_validation.py -v

# Integration tests
uv run pytest tests/integration/test_heterogeneous_desktop.py -v
```

## Monitoring GPU Cluster

Use the telemetry aggregator to monitor cluster health:

```python
from exo.shared.gpu_telemetry_aggregator import GPUTelemetryAggregator

# Aggregate metrics from all nodes
metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)

print(metrics.format_cluster_summary())
# Output:
# === GPU Cluster Metrics ===
# Total Devices: 4
# Total Memory: 96.0 GB
# Available Memory: 90.0 GB
# Total Compute Units: 512
# Average Bandwidth: 800.5 GB/s
# Bottleneck Bandwidth: 200.0 GB/s
# Heterogeneity Ratio: 4.32x
# Vendors: nvidia(2), amd(1), apple(1)
```

## Multi-GPU Clustering

For heterogeneous clusters (mixed GPU vendors):

```python
# Get optimal devices for model placement
model_config = {
    "estimated_memory_bytes": 8 * 1024**3,  # 8 GB
    "tensor_operations": 1e12,  # 1 TFLOP
}

optimal_devices = GPUTelemetryAggregator.get_optimal_devices(
    all_devices,
    model_config,
    count=2  # Use top 2 devices
)

print(f"Selected devices: {[d.name for d in optimal_devices]}")
```

## Performance Benchmarks

Expected performance on various hardware:

### Single GPU Inference (tokens/second)

| Hardware | 7B Model | 13B Model | 70B Model |
|:---|---:|---:|---:|
| Apple M2 Max | 45 | 25 | N/A |
| Apple M3 Max | 65 | 40 | N/A |
| NVIDIA RTX 3090 | 120 | 70 | 15 |
| NVIDIA RTX 4090 | 180 | 110 | 25 |
| NVIDIA H100 | 600 | 400 | 100 |
| AMD MI300X | 500 | 350 | 85 |

### Multi-GPU Tensor Parallelism

Expected speedup with multiple GPUs (same model):

| Setup | Speedup |
|:---|---:|
| 2x RTX 4090 | 1.8x |
| 4x RTX 4090 | 3.2x |
| 2x H100 | 1.95x |
| 4x H100 | 3.8x |

## Future Work

- [ ] Vulkan support for Android
- [ ] Metal optimization for iOS
- [ ] DirectML for Windows cross-vendor support
- [ ] CUDA 12.x optimizations
- [ ] ROCm 6.0+ support
- [ ] OpenCL fallback for compatibility
- [ ] Privacy-preserving GPU compute

## References

- [NVIDIA CUDA Documentation](https://docs.nvidia.com/cuda/)
- [AMD ROCm Documentation](https://rocmdocs.amd.com/)
- [Apple MLX Framework](https://ml-explore.github.io/mlx/)
- [CuPy Documentation](https://docs.cupy.dev/en/stable/)

## Support

For issues with GPU support:

1. Check this guide's troubleshooting section
2. Review GPU backend logs: `export EXOD_LOG=DEBUG`
3. Run validation tests: `pytest tests/gpu_validation.py -v`
4. File an issue on GitHub with GPU info: `nvidia-smi` or `rocm-smi` output

