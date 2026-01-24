# GPU Integration - Quick Reference Card

## Project Status
- **Overall**: 60% → 80% target (16 hours)
- **Phase 1 (GPU Backends)**: ✅ 100%
- **Phase 2 (Heterogeneous)**: 🔄 70% (CSP integration pending)

## Critical Path Items

### 1. CSP Integration (3h) - `src/exo/master/placement.py`
```python
# After line 188, add:
if gpu_device_state and _has_heterogeneous_gpus(gpu_device_state):
    shard_assignments = await _place_instance_with_csp(...)
else:
    shard_assignments = get_shard_assignments(...)  # existing
```

### 2. Worker Integration (4h) - `src/exo/worker/main.py`
```python
# In Worker.run():
self.gpu_telemetry = GPUTelemetryCollector(
    node_id=self.node_id,
    gpu_backend=await GPUBackendFactory.create_backend(),
    event_emitter=emit_gpu_event,
)
await self.gpu_telemetry.start_monitoring()
```

### 3. Testing (6h) - Multiple files
```bash
uv run pytest src/exo/master/tests/test_placement_csp_integration.py -xvs
uv run pytest src/exo/worker/tests/test_gpu_telemetry.py -xvs
uv run pytest src/exo/shared/tests/test_gpu_integration_e2e.py -xvs
```

## Key Files & Their Purpose

| File | Purpose | Lines | Status |
|------|---------|-------|--------|
| `src/exo/gpu/backend.py` | GPU abstraction interface | 300 | ✅ |
| `src/exo/master/placement_csp.py` | CSP solver | 410 | ✅ |
| `src/exo/worker/gpu_telemetry.py` | Telemetry collector | 270 | ✅ |
| `src/exo/shared/types/events.py` | GPU events | +25 | ✅ |
| `src/exo/shared/apply.py` | Event handlers | +45 | ✅ |
| `src/exo/master/placement.py` | Placement logic | +100 | 🔄 |
| `src/exo/worker/main.py` | Worker init | +40 | 🔄 |

## Code Snippets

### Check if Heterogeneous
```python
from exo.master.placement import _has_heterogeneous_gpus
if _has_heterogeneous_gpus(gpu_device_state):
    # Use CSP
else:
    # Use greedy
```

### Compute Device Scores
```python
from exo.master.placement import _compute_device_scores
scores = _compute_device_scores(
    cycle_node_ids=selected_cycle.node_ids,
    gpu_device_state=gpu_device_state,
    shard_size_bytes=max(shard_sizes),
    topology=topology,
)
```

### Collect GPU State
```python
from exo.worker.gpu_telemetry import GPUTelemetryCollector
collector = GPUTelemetryCollector(
    node_id=node_id,
    gpu_backend=gpu_backend,
    event_emitter=emit_event,
)
await collector.start_monitoring()
```

### Emit GPU Event
```python
from exo.shared.types.events import DeviceGPUStateUpdated
event = DeviceGPUStateUpdated(device_state=state)
await event_sender.send(event)
```

## Commands Cheatsheet

```bash
# Type checking
uv run basedpyright

# Linting
uv run ruff check

# Formatting
nix fmt

# Test all
uv run pytest

# Test specific
uv run pytest src/exo/master/tests/ -xvs

# Test with coverage
uv run pytest --cov=src/exo/master/

# Run exo
uv run exo -vv
```

## Architecture at 10,000 Feet

```
Worker Node
├── GPU Devices
│   ├── cuda:0 (8GB)
│   └── cuda:1 (16GB) ← Heterogeneous!
└── GPUTelemetryCollector
    └── DeviceGPUStateUpdated Event
        ↓
Master Node
├── Event Handler (apply.py)
│   └── Update State.gpu_device_state
└── Placement Decision
    ├── Detect Heterogeneous
    ├── Compute Scores (memory, thermal, compute, network)
    ├── Solve CSP (optimal shard assignment)
    └── Create Instance with optimal placement
```

## DeviceGPUState Fields

```python
device_id: str                    # e.g., "cuda:0"
node_id: NodeId                   # Owner node
memory_used_bytes: int            # Current usage
memory_total_bytes: int           # Total capacity
compute_utilization_percent: float # 0-100
thermal_temperature_c: float      # Current temp or -1
thermal_throttle_threshold_c: float # Safety limit
is_thermal_throttling: bool       # Currently throttled?
battery_percent: float            # Mobile: 0-100
is_plugged_in: bool              # Mobile: charging?
last_update: datetime             # When measured
```

## CSP Scoring Weights

```python
GPUDeviceScore.weighted_score = (
    compute_score * 0.40 +      # Critical
    memory_score * 0.30 +       # Important
    network_score * 0.15 +      # Moderate
    thermal_score * 0.10 +      # Mobile safety
    bandwidth_score * 0.05      # Optimization
)
```

## Event Types

### DeviceGPUStateUpdated
```python
@dataclass
class DeviceGPUStateUpdated(BaseEvent):
    device_state: DeviceGPUState  # Updated metrics
```
**Emitter**: GPUTelemetryCollector  
**Handler**: apply_device_gpu_state_updated()  
**Effect**: Updates State.gpu_device_state[device_id]

### GPUBandwidthMeasured
```python
@dataclass
class GPUBandwidthMeasured(BaseEvent):
    source_device_id: str
    dest_device_id: str
    bandwidth_mbps: float
    latency_ms: float
    measurement_count: int
```
**Emitter**: (Topology measurement phase)  
**Handler**: apply_gpu_bandwidth_measured()  
**Effect**: (TODO: Update GPU topology)

## Testing Strategy

### Unit Tests (Fast, Isolated)
- `_has_heterogeneous_gpus()` with different device configs
- `_compute_device_scores()` with various states
- `GPUTelemetryCollector` with mocked backend
- Event handlers apply state correctly

### Integration Tests (Components Interact)
- Mock cluster with heterogeneous devices
- Verify CSP called instead of greedy
- Verify events applied to state
- Verify placement uses latest state

### E2E Tests (Full System)
- Real or synthetic GPU devices
- Full placement decision pipeline
- Telemetry collection → event → state → placement
- Verify optimal assignments

### Regression Tests (Nothing Broke)
- Existing MLX placement still works
- Non-heterogeneous clusters unchanged
- Event ordering maintained
- State consistency preserved

## Common Mistakes

❌ Forgetting to import DeviceGPUState  
❌ Using `Optional[DeviceGPUState]` instead of checking with `.get()`  
❌ Not handling None GPU backend gracefully  
❌ Emitting telemetry events too frequently  
❌ Breaking existing MLX placement logic  
❌ Not testing error cases  
❌ Forgetting to stop telemetry on shutdown  

## Performance Targets

| Metric | Target | How to Measure |
|--------|--------|----------------|
| GPU init | <3s | Time `GPUBackendFactory.create_backend()` |
| Telemetry overhead | <5% | Compare inference with/without telemetry |
| CSP placement | <100ms | Time CSP solver or use greedy fallback |
| State update latency | <500ms | Time from event emission to state update |
| Memory overhead | <50MB | Monitor process memory for gpu_device_state |

## Debugging Tips

### GPU Events Not Emitted
1. Check worker startup logs for "GPU telemetry monitoring started"
2. Verify GPU backend initialization succeeds
3. Check `_is_running` flag in collector
4. Add logging to _monitoring_loop()

### CSP Solver Not Used
1. Check `_has_heterogeneous_gpus()` return value
2. Verify gpu_device_state has >1 device
3. Check if memory sizes are different
4. Add logging in place_instance()

### Type Checker Failures
1. Check import paths are correct
2. Verify Mapping vs Sequence types
3. Use `basedpyright --version` to check compiler
4. Look for None-related type errors

### Test Failures
1. Run with `-xvs` for verbose output
2. Use `--pdb` to debug
3. Check mock setup is correct
4. Verify fixture parameters

## Decision Tree: When to Use CSP

```
├─ gpu_device_state exists?
│  ├─ No → Use greedy placement
│  └─ Yes
│     ├─ _has_heterogeneous_gpus()?
│     │  ├─ No → Use greedy placement
│     │  └─ Yes
│     │     ├─ Try CSP placement
│     │     ├─ Timeout? → Use greedy fallback
│     │     └─ Success → Use CSP assignments
```

## Session 2 Checklist

### Day 1: Integration
- [ ] Add CSP logic to placement.py
- [ ] Initialize telemetry in worker.py
- [ ] Verify master receives events
- [ ] Smoke test: no crashes

### Day 2: Testing & Polish
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Regression tests pass
- [ ] Performance OK (<5% overhead)
- [ ] All quality checks pass
- [ ] Documentation updated

## References

| Document | Purpose |
|----------|---------|
| SESSION_2_ROADMAP.md | Step-by-step implementation |
| ANALYSIS_AND_ROADMAP.md | Requirements vs implementation |
| README_GPU_INTEGRATION.md | Architecture overview |
| IMPLEMENTATION_STATUS.md | Current status tracking |
| EXECUTIVE_SUMMARY.md | Business impact |

---

**Keep this handy while implementing Session 2!**
