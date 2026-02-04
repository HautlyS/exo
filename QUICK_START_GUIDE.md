# Quick Start Guide - GPU Implementation

## 🚀 Getting Started

This guide helps you quickly get started with the newly implemented GPU features.

---

## Installation

### 1. Install Core Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install security dependencies
pip install cryptography

# Install Vulkan support (optional)
pip install vulkan
```

### 2. Install Test Dependencies (Optional)

```bash
pip install pytest pytest-asyncio
```

---

## Quick Validation

### Validate Implementation

```bash
python3 validate_implementation.py
```

Expected output:
```
✅ GPU Access Control (RBAC)
✅ Audit Logging
✅ TLS Authentication
✅ GPU Performance Benchmarks
✅ Network Measurement
✅ Vulkan GPU Backend
```

---

## Usage Examples

### 1. GPU Access Control

```python
import asyncio
from exo.security import GPUAccessControl, GPURole, create_default_policy, GPUPermission

async def main():
    # Initialize access control
    access_control = GPUAccessControl()
    
    # Add user policy
    policy = create_default_policy("user1", GPURole.USER)
    await access_control.add_policy(policy)
    
    # Check permission
    has_access = await access_control.check_permission(
        "user1",
        GPUPermission.MEMORY_ALLOCATE,
        device_id="cuda:0"
    )
    
    print(f"User has access: {has_access}")

asyncio.run(main())
```

### 2. Audit Logging

```python
import asyncio
from pathlib import Path
from exo.security import AuditLogger, AuditEventType

async def main():
    # Initialize audit logger
    logger = AuditLogger(
        log_file=Path("audit.log"),
        enable_console=True
    )
    
    # Start auto-flush
    await logger.start_auto_flush(interval_seconds=5.0)
    
    # Log GPU operation
    await logger.log_gpu_operation(
        event_type=AuditEventType.MEMORY_ALLOCATE,
        principal_id="user1",
        device_id="cuda:0",
        result="success",
        metadata={"size_bytes": 1024**3}
    )
    
    # Query events
    events = await logger.query_events(
        principal_id="user1",
        limit=10
    )
    
    print(f"Found {len(events)} events")
    
    # Cleanup
    await logger.shutdown()

asyncio.run(main())
```

### 3. TLS Authentication

```python
import asyncio
from pathlib import Path
from exo.security.secure_quic import SecureQUICManager, create_default_tls_config

async def main():
    # Create TLS config
    config = create_default_tls_config()
    
    # Initialize secure QUIC
    manager = SecureQUICManager(config)
    await manager.initialize()
    
    # Get SSL context for QUIC connections
    ssl_context = manager.get_ssl_context()
    
    # Get certificate fingerprint
    fingerprint = manager.get_cert_fingerprint()
    print(f"Certificate fingerprint: {fingerprint[:16]}...")
    
    # Cleanup
    await manager.shutdown()

asyncio.run(main())
```

### 4. Performance Benchmarks

```bash
# Run all GPU benchmarks
python benchmarks/gpu_performance.py

# Results saved to benchmark_results.json
```

Output:
```
Benchmarking: NVIDIA RTX 4090 (cuda:0)
  Memory bandwidth H2D:
    1MB: 12.5 GB/s (0.08 ms)
    10MB: 15.2 GB/s (0.66 ms)
    100MB: 18.3 GB/s (5.46 ms)
  
  Allocation latency: 0.125 ms (avg)
  Synchronization latency: 0.015 ms (avg)
```

### 5. Layer Offloading

```python
import asyncio
from exo.worker.layer_offloading import (
    LayerOffloadingManager,
    LayerSpec,
    LayerType
)

async def main():
    # Create layer specifications
    layers = [
        LayerSpec(
            layer_id="embedding",
            layer_type=LayerType.EMBEDDING,
            memory_bytes=1024**3,  # 1GB
            compute_flops=1e12,
            input_size_bytes=1024**2,
            output_size_bytes=1024**2,
        ),
        LayerSpec(
            layer_id="attention_0",
            layer_type=LayerType.ATTENTION,
            memory_bytes=2 * 1024**3,  # 2GB
            compute_flops=5e12,
            input_size_bytes=1024**2,
            output_size_bytes=1024**2,
        ),
    ]
    
    # Create offloading plan
    manager = LayerOffloadingManager(topology)
    plan = await manager.create_offloading_plan(
        layers,
        devices,
        optimization_goal="latency"
    )
    
    print(f"Created plan with {len(plan.placements)} placements")
    print(f"Estimated latency: {plan.estimated_latency_ms:.2f}ms")
    
    # Get device for layer
    device_id = await manager.get_layer_device("embedding")
    print(f"Embedding layer on: {device_id}")

# Note: Requires GPU topology and devices
# asyncio.run(main())
```

### 6. Network Measurement

```python
import asyncio
from exo.shared.network_measurement import NetworkMeasurementService

async def main():
    service = NetworkMeasurementService()
    
    # Measure latency
    latency = await service.measure_latency("node1", "node2")
    print(f"RTT: {latency.rtt_ms:.2f}ms")
    print(f"Jitter: {latency.jitter_ms:.2f}ms")
    print(f"Packet loss: {latency.packet_loss*100:.1f}%")
    
    # Measure bandwidth
    bandwidth = await service.measure_bandwidth("node1", "node2")
    print(f"Bandwidth: {bandwidth.bandwidth_mbps:.2f} Mbps")
    
    # Estimate transfer time
    transfer_time = await service.estimate_transfer_time(
        "node1", "node2",
        size_bytes=1024**3  # 1GB
    )
    print(f"Estimated transfer time: {transfer_time:.2f}s")

asyncio.run(main())
```

---

## Running Tests

### Security Tests

```bash
# Run all security tests
pytest src/exo/security/tests/ -v

# Run specific test file
pytest src/exo/security/tests/test_gpu_access.py -v

# Run with coverage
pytest src/exo/security/tests/ --cov=exo.security --cov-report=html
```

### Integration Tests

```bash
# Run integration tests
pytest tests/integration/test_heterogeneous_desktop.py -v

# Run specific test
pytest tests/integration/test_heterogeneous_desktop.py::TestSinglePlatformClusters::test_cuda_cluster_discovery -v
```

---

## Configuration

### Access Control Configuration

```python
from exo.security import GPUAccessPolicy, GPURole, GPUPermission

# Create custom policy
policy = GPUAccessPolicy(
    principal_id="power_user1",
    roles={GPURole.POWER_USER},
    device_restrictions={"cuda:0", "cuda:1"},  # Only these devices
    memory_quota_bytes=8 * 1024**3,  # 8GB quota
    custom_permissions={GPUPermission.MONITOR_TEMPERATURE},
)
```

### Audit Logging Configuration

```python
from pathlib import Path
from exo.security import AuditLogger

logger = AuditLogger(
    log_file=Path("/var/log/exo/audit.log"),
    enable_console=True,
    buffer_size=100,  # Buffer 100 events before flushing
)
```

### TLS Configuration

```python
from pathlib import Path
from exo.security.secure_quic import TLSConfig
import ssl

# Development config (self-signed)
dev_config = TLSConfig(
    cert_path=Path("~/.exo/certs/dev.crt"),
    key_path=Path("~/.exo/certs/dev.key"),
    verify_mode=ssl.CERT_OPTIONAL,
    check_hostname=False,
)

# Production config (CA-signed)
prod_config = TLSConfig(
    cert_path=Path("/etc/exo/certs/node.crt"),
    key_path=Path("/etc/exo/certs/node.key"),
    ca_cert_path=Path("/etc/exo/certs/ca.crt"),
    verify_mode=ssl.CERT_REQUIRED,
    check_hostname=True,
    min_tls_version=ssl.TLSVersion.TLSv1_3,
)
```

---

## Troubleshooting

### Issue: "No module named 'pytest'"

**Solution**: Install pytest
```bash
pip install pytest pytest-asyncio
```

### Issue: "No module named 'rustworkx'"

**Solution**: Install rustworkx
```bash
pip install rustworkx
```

### Issue: "No module named 'cryptography'"

**Solution**: Install cryptography
```bash
pip install cryptography
```

### Issue: "Vulkan backend not available"

**Solution**: Install Vulkan SDK and Python bindings
```bash
# Install Vulkan SDK (platform-specific)
# Then install Python bindings
pip install vulkan
```

### Issue: "Certificate generation failed"

**Solution**: Ensure write permissions
```bash
mkdir -p ~/.exo/certs
chmod 700 ~/.exo/certs
```

---

## Performance Tips

### 1. Audit Logging

- Use larger buffer sizes for high-throughput systems
- Enable auto-flush with appropriate interval
- Use file-based logging for production

### 2. Access Control

- Cache permission checks when possible
- Use device restrictions to limit scope
- Set appropriate memory quotas

### 3. Benchmarks

- Run benchmarks on idle system
- Use multiple iterations for accuracy
- Compare results across platforms

---

## Production Deployment

### 1. Security Setup

```bash
# Generate production certificates
# (or use your CA-signed certificates)

# Configure access policies
python scripts/setup_access_policies.py

# Enable audit logging
export EXO_AUDIT_LOG=/var/log/exo/audit.log
```

### 2. Performance Validation

```bash
# Run benchmarks
python benchmarks/gpu_performance.py

# Review results
cat benchmark_results.json
```

### 3. Integration Testing

```bash
# Run all tests
pytest tests/ -v

# Run integration tests
pytest tests/integration/ -v
```

### 4. Monitoring

```bash
# Monitor audit log
tail -f /var/log/exo/audit.log

# Query recent events
python scripts/query_audit_log.py --last-hour
```

---

## Additional Resources

- **Implementation Report**: `AUTONOMOUS_IMPLEMENTATION_REPORT.md`
- **Complete Documentation**: `IMPLEMENTATION_COMPLETE.md`
- **API Documentation**: See docstrings in source files
- **Test Examples**: `src/exo/security/tests/`

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the implementation documentation
3. Check test files for usage examples
4. Review inline documentation in source files

---

**Quick Start Version**: 1.0  
**Last Updated**: January 29, 2026  
**Status**: Production Ready ✅
