# GPU Clustering & Scheduling

Phase 6 implements multi-GPU clustering and intelligent workload distribution.

## Features

### Device Registration and Management
- Register heterogeneous GPU devices (NVIDIA, AMD, Intel, Apple, Qualcomm)
- Query device capabilities and current metrics
- Track device availability and health

### Intelligent Device Selection
- Score devices based on:
  - Available memory (60% weight)
  - Compute utilization (40% weight)
  - Temperature penalties (high temp reduces score)
- Select best device for workload
- Support memory requirements constraints

### Workload Distribution
- Uniform distribution across devices
- Capacity-aware distribution (weighted by compute capability)
- Respect device constraints (max items per device)

### Telemetry Collection
- Collect real-time GPU metrics (memory, utilization, temperature, power)
- Maintain metrics history per device
- Aggregate metrics across cluster
- Timestamp and correlate measurements

## Usage

### Basic Device Management

```python
from exo.gpu.clustering import GPUClusteringManager

manager = GPUClusteringManager()

# Register devices
for device in discovered_devices:
    manager.register_device(device)

# List devices
devices = manager.list_devices()
```

### Recording Metrics

```python
from exo.gpu.telemetry_protocol import GPUMetrics

metrics = GPUMetrics(
    device_id="cuda:0",
    timestamp=1707043200.0,
    memory_used_bytes=8_000_000_000,
    memory_total_bytes=24_000_000_000,
    compute_utilization_percent=50.0,
    power_watts=150.0,
    temperature_celsius=65.0,
    clock_rate_mhz=2500,
)

await manager.record_metrics(metrics)
```

### Device Selection

```python
# Select best device
best_device = manager.select_best_device()

# Select device with minimum memory requirement
best_device = manager.select_best_device(min_memory_bytes=8_000_000_000)
```

### Workload Distribution

```python
# Uniform distribution
distribution = manager.distribute_workload(
    tasks=tasks,
    strategy="uniform",
)

# Capacity-aware distribution
distribution = manager.distribute_workload(
    tasks=tasks,
    strategy="capacity",
    capacities={"cuda:0": 1.0, "cuda:1": 2.0},
)
```

### Telemetry Aggregation

```python
# Get aggregated metrics
agg = manager.get_aggregated_metrics()
print(f"Total devices: {agg['device_count']}")
print(f"Total memory: {agg['total_memory_bytes']} bytes")
print(f"Average utilization: {agg['average_utilization_percent']}%")
```

## Architecture

### Components

1. **GPUClusteringManager**: Central coordinator
   - Device registration
   - Metrics collection
   - Workload distribution
   - Device selection

2. **DeviceSelector**: Device ranking
   - Scores devices by metrics
   - Ranks devices by capability
   - Selects best device with constraints

3. **TelemetryCollector**: Metrics aggregation
   - Records per-device metrics
   - Maintains metrics history
   - Aggregates cluster-wide metrics

4. **WorkloadDistributor**: Task distribution
   - Uniform distribution
   - Capacity-aware distribution
   - Constraint enforcement

## Performance Characteristics

| Operation | Time |
|-----------|------|
| Device registration | < 1ms |
| Device selection | < 10ms |
| Metrics recording | < 1ms |
| Workload distribution | < 50ms |
| Aggregation | < 10ms |

## Testing

Run tests with:

```bash
# Unit tests
pytest tests/test_gpu_clustering.py -v

# Integration tests
pytest tests/integration/test_gpu_clustering_integration.py -v

# All GPU tests
pytest tests/ -k gpu -v
```

## Future Enhancements

- Dynamic load balancing
- Device affinity and locality
- Heterogeneous precision support
- Performance prediction models
- Network topology optimization
