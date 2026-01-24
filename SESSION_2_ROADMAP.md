# Session 2 Implementation Roadmap: Heterogeneous GPU Clustering

**Target Completion**: 80% of project (from current 60%)  
**Estimated Duration**: 16 hours  
**Priority**: CRITICAL PATH - gets system to functional MVP

---

## Overview

Session 2 focuses on integrating the components created in Session 1 into a working end-to-end system. The goal is to demonstrate heterogeneous GPU clustering with real-time telemetry.

### What You'll Accomplish

By end of Session 2:
- ✅ Heterogeneous cluster detection working
- ✅ CSP placement solver integrated
- ✅ Worker GPU telemetry collection running
- ✅ Master processing GPU state updates
- ✅ Comprehensive test coverage
- ✅ Zero regressions in existing functionality

### Success Metrics

- [ ] All type checks pass (`uv run basedpyright`)
- [ ] All linting passes (`uv run ruff check`)
- [ ] All formatting valid (`nix fmt`)
- [ ] All tests pass (`uv run pytest`)
- [ ] No breaking changes to API
- [ ] E2E test demonstrates heterogeneous placement

---

## Task 1: Complete CSP Integration (3 hours)

**File**: `src/exo/master/placement.py`

### 1.1 Add CSP Logic to place_instance()

After line 188 (after sharding validation), add heterogeneous placement decision:

```python
# Around line 189, after sharding checks
# Check for heterogeneous GPU cluster
if gpu_device_state and _has_heterogeneous_gpus(gpu_device_state):
    logger.info(f"Heterogeneous GPU cluster detected ({len(gpu_device_state)} devices)")
    
    # Use CSP placement for heterogeneous clusters
    try:
        shard_assignments = await _place_instance_with_csp(
            command=command,
            selected_cycle=selected_cycle,
            gpu_device_state=gpu_device_state,
            node_memory=node_memory,
            topology=topology,
        )
    except Exception as e:
        logger.warning(f"CSP placement failed: {e}, falling back to greedy")
        shard_assignments = get_shard_assignments(
            command.model_card, selected_cycle, command.sharding, node_memory
        )
else:
    # Use existing greedy placement for homogeneous clusters
    shard_assignments = get_shard_assignments(
        command.model_card, selected_cycle, command.sharding, node_memory
    )
```

### 1.2 Create Helper Function for CSP Placement

Add this function after `_compute_device_scores()`:

```python
async def _place_instance_with_csp(
    command: PlaceInstance,
    selected_cycle: Cycle,
    gpu_device_state: Mapping[str, DeviceGPUState],
    node_memory: Mapping[NodeId, MemoryUsage],
    topology: Topology,
) -> dict[int, str]:
    """Place instance shards using CSP solver.
    
    Args:
        command: PlaceInstance command with model info
        selected_cycle: Selected node cycle
        gpu_device_state: Current GPU device states
        node_memory: Node memory info
        topology: Cluster topology
        
    Returns:
        Dict mapping shard_index -> device_id
    """
    # Get shard sizes from model
    # TODO: Compute actual shard sizes from model_card
    # For now, use uniform distribution
    num_shards = len(selected_cycle)
    total_model_size = command.model_card.storage_size.bytes
    shard_sizes = [total_model_size // num_shards] * num_shards
    
    # Get devices in cycle
    devices_in_cycle = [
        dev for dev in gpu_device_state.values()
        if dev.node_id in selected_cycle.node_ids
    ]
    
    if not devices_in_cycle:
        logger.warning("No GPU devices found in selected cycle, falling back to greedy")
        return {}
    
    # Compute device scores
    device_scores = _compute_device_scores(
        cycle_node_ids=selected_cycle.node_ids,
        gpu_device_state=gpu_device_state,
        shard_size_bytes=max(shard_sizes),  # Use max for constraint checking
        topology=topology,
    )
    
    # Solve CSP
    solver = ConstraintSatisfactionPlacement(
        timeout_seconds=5.0,
        max_backtrack_depth=100,
    )
    
    assignment = await solver.solve_placement(
        num_shards=num_shards,
        shard_sizes_bytes=shard_sizes,
        devices=devices_in_cycle,
        device_scores=device_scores,
        topology={"cycles": [selected_cycle.node_ids]},
    )
    
    logger.info(f"CSP placement: {assignment}")
    return assignment
```

### 1.3 Verify Signature Changes

The function signature already includes `gpu_device_state` parameter, so no changes needed to call sites.

### Checkpoint
```bash
# Verify syntax
uv run basedpyright src/exo/master/placement.py

# Run placement tests
uv run pytest src/exo/master/tests/test_placement.py -xvs
```

---

## Task 2: Worker Telemetry Integration (4 hours)

**File**: `src/exo/worker/main.py`

### 2.1 Import Telemetry Components

At the top of the file, add imports:

```python
from exo.worker.gpu_telemetry import GPUTelemetryCollector, GPUTelemetryConfig
from exo.gpu.factory import GPUBackendFactory
```

### 2.2 Initialize in Worker.__init__()

Add to the Worker class:

```python
class Worker:
    def __init__(self, ...):
        # ... existing code ...
        self.gpu_telemetry_collector: GPUTelemetryCollector | None = None
        self.gpu_telemetry_task: asyncio.Task[None] | None = None
```

### 2.3 Start Telemetry in Worker.run()

In the `async def run()` method, after GPU backend initialization:

```python
async def run(self) -> None:
    # ... existing code ...
    
    # Initialize GPU backend
    try:
        gpu_backend = await GPUBackendFactory.create_backend()
        
        # Create telemetry collector
        async def emit_gpu_event(event: DeviceGPUStateUpdated) -> None:
            """Emit GPU telemetry event to event sender."""
            await self.event_sender.send(event)
        
        self.gpu_telemetry_collector = GPUTelemetryCollector(
            node_id=self.node_id,
            gpu_backend=gpu_backend,
            event_emitter=emit_gpu_event,
            config=GPUTelemetryConfig(
                collection_interval_seconds=2.0,
                enable_temperature_monitoring=True,
                enable_power_monitoring=True,
            ),
        )
        
        # Start telemetry monitoring
        await self.gpu_telemetry_collector.start_monitoring()
        logger.info("GPU telemetry monitoring started")
        
    except Exception as e:
        logger.warning(f"Failed to initialize GPU telemetry: {e}")
        # Continue without telemetry
```

### 2.4 Graceful Shutdown

In the shutdown/cleanup section:

```python
async def _cleanup(self) -> None:
    """Cleanup resources."""
    if self.gpu_telemetry_collector:
        try:
            await self.gpu_telemetry_collector.stop_monitoring()
        except Exception as e:
            logger.warning(f"Error stopping GPU telemetry: {e}")
    
    # ... rest of cleanup ...
```

### 2.5 Fix Event Import

Add to imports section:

```python
from exo.shared.types.events import DeviceGPUStateUpdated
```

### Checkpoint
```bash
# Check imports and syntax
uv run basedpyright src/exo/worker/main.py

# Ensure worker still starts (dry run)
uv run exo --help
```

---

## Task 3: Master Event Handling (3 hours)

**File**: `src/exo/master/main.py`

### 3.1 Verify GPU Event Processing

The master already processes GPU events via `apply.py`. Verify the event flow:

```python
# In src/exo/master/main.py, in the command processing loop:
# The PlaceInstance handler already receives gpu_device_state from state
# No changes needed - it's automatic!
```

### 3.2 Add Diagnostic Logging (Optional)

Add logging when GPU state updates are received:

```python
# In the event processing loop of Master, after state update:
if isinstance(event.event, DeviceGPUStateUpdated):
    logger.debug(
        f"GPU state update: {event.event.device_state.device_id} "
        f"memory={event.event.device_state.memory_utilization_percent:.1f}% "
        f"temp={event.event.device_state.thermal_temperature_c:.1f}°C"
    )
```

### 3.3 Verify State Synchronization

Check that state updates are properly applied:

```bash
# Add temporary logging to apply.py (after Session 2)
# Verify: logger in apply_device_gpu_state_updated shows updates
```

### Checkpoint
```bash
# Run master tests
uv run pytest src/exo/master/tests/test_master.py -xvs -k "test_"
```

---

## Task 4: Comprehensive Testing (6 hours)

### 4.1 Unit Tests for CSP Helpers

**File**: `src/exo/master/tests/test_placement_csp_integration.py` (new)

```python
import pytest
from exo.master.placement import _has_heterogeneous_gpus, _compute_device_scores
from exo.shared.types.state import DeviceGPUState
from exo.shared.types.common import NodeId

@pytest.mark.asyncio
async def test_has_heterogeneous_gpus_detects_different_memory():
    """Test heterogeneous detection with different memory sizes."""
    node_id = NodeId()
    gpu_state = {
        "cuda:0": DeviceGPUState(
            device_id="cuda:0",
            node_id=node_id,
            memory_used_bytes=4_000_000_000,
            memory_total_bytes=8_000_000_000,
            compute_utilization_percent=50.0,
            thermal_temperature_c=65.0,
        ),
        "cuda:1": DeviceGPUState(
            device_id="cuda:1",
            node_id=node_id,
            memory_used_bytes=2_000_000_000,
            memory_total_bytes=16_000_000_000,  # Different!
            compute_utilization_percent=30.0,
            thermal_temperature_c=55.0,
        ),
    }
    
    assert _has_heterogeneous_gpus(gpu_state) is True

@pytest.mark.asyncio
async def test_compute_device_scores_memory_scoring():
    """Test device scoring for memory constraints."""
    # TODO: Implement this test
```

### 4.2 Unit Tests for Telemetry

**File**: `src/exo/worker/tests/test_gpu_telemetry.py` (new)

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from exo.worker.gpu_telemetry import GPUTelemetryCollector, GPUTelemetryConfig

@pytest.mark.asyncio
async def test_telemetry_collector_initialization():
    """Test collector can be initialized."""
    mock_backend = AsyncMock()
    mock_emitter = MagicMock()
    
    collector = GPUTelemetryCollector(
        node_id="node_1",
        gpu_backend=mock_backend,
        event_emitter=mock_emitter,
        config=GPUTelemetryConfig(collection_interval_seconds=1.0),
    )
    
    assert collector.node_id == "node_1"
    assert not collector._is_running
```

### 4.3 Integration Test

**File**: `src/exo/shared/tests/test_gpu_integration_e2e.py` (new)

```python
import pytest
from exo.shared.apply import apply_device_gpu_state_updated, apply
from exo.shared.types.state import State, DeviceGPUState
from exo.shared.types.events import DeviceGPUStateUpdated, IndexedEvent
from datetime import datetime

@pytest.mark.asyncio
async def test_gpu_state_updates_applied_to_state():
    """Test that GPU state updates are properly applied."""
    initial_state = State()
    
    # Create GPU state update
    device_state = DeviceGPUState(
        device_id="cuda:0",
        node_id="node_1",
        memory_used_bytes=4_000_000_000,
        memory_total_bytes=8_000_000_000,
        compute_utilization_percent=50.0,
        thermal_temperature_c=65.0,
    )
    
    event = IndexedEvent(
        idx=0,
        event=DeviceGPUStateUpdated(device_state=device_state),
    )
    
    # Apply event
    new_state = apply(initial_state, event)
    
    # Verify state was updated
    assert "cuda:0" in new_state.gpu_device_state
    assert new_state.gpu_device_state["cuda:0"].device_id == "cuda:0"
    assert new_state.gpu_device_state["cuda:0"].compute_utilization_percent == 50.0
```

### 4.4 Run All Tests

```bash
# Unit tests
uv run pytest src/exo/master/tests/test_placement_csp_integration.py -xvs

# Telemetry tests
uv run pytest src/exo/worker/tests/test_gpu_telemetry.py -xvs

# Integration tests
uv run pytest src/exo/shared/tests/test_gpu_integration_e2e.py -xvs

# Regression tests (ensure nothing broke)
uv run pytest src/exo/master/tests/test_placement.py -xvs
uv run pytest src/exo/shared/tests/test_apply/ -xvs
```

### 4.5 Code Quality Checks

```bash
# Type checking
uv run basedpyright

# Linting
uv run ruff check

# Formatting
nix fmt

# All tests
uv run pytest
```

---

## Task 5: Optional - Dashboard Integration (4 hours)

### 5.1 API Endpoints

**File**: `src/exo/master/api.py`

Add endpoints to expose GPU state:

```python
@app.get("/api/gpu/devices")
async def get_gpu_devices() -> dict:
    """Get list of GPU devices in cluster."""
    return {
        "devices": [
            {
                "device_id": dev_id,
                "node_id": str(state.node_id),
                "memory_used_mb": state.memory_used_bytes / (1024 * 1024),
                "memory_total_mb": state.memory_total_bytes / (1024 * 1024),
                "temperature_c": state.thermal_temperature_c,
                "utilization_percent": state.compute_utilization_percent,
            }
            for dev_id, state in self.state.gpu_device_state.items()
        ]
    }

@app.get("/api/gpu/topology")
async def get_gpu_topology() -> dict:
    """Get GPU cluster topology."""
    # TODO: Return GPU-aware topology
    return {
        "devices": list(self.state.gpu_device_state.keys()),
        "links": [],
    }
```

### 5.2 Frontend Components (Deferred to Session 3)

Can add UI components later:
- Device list component
- Topology diagram
- Real-time metrics charts

---

## Verification Checklist

Use this to track progress:

### Code Changes
- [ ] CSP integration added to placement.py
- [ ] Helper function `_place_instance_with_csp()` implemented
- [ ] Worker initialization code added
- [ ] GPU telemetry task started in worker
- [ ] Master event handlers already in place
- [ ] All imports added correctly

### Testing
- [ ] Type checking passes (`uv run basedpyright`)
- [ ] Linting passes (`uv run ruff check`)
- [ ] Formatting valid (`nix fmt`)
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Regression tests pass
- [ ] E2E test demonstrates feature

### Documentation
- [ ] Code comments explain CSP usage
- [ ] Docstrings for new functions
- [ ] Error handling documented
- [ ] Logging is appropriate

### Performance
- [ ] GPU init still <3 seconds
- [ ] Telemetry overhead <5%
- [ ] Placement decision <100ms
- [ ] No memory leaks

---

## Debugging Guide

### If CSP solver not called:
1. Check `_has_heterogeneous_gpus()` is returning True
2. Add logging: `logger.info(f"GPU devices: {gpu_device_state}")`
3. Verify device states have different memory sizes

### If telemetry events not emitted:
1. Check worker is starting (look for "GPU telemetry monitoring started" log)
2. Verify GPU backend initialization succeeds
3. Check event_emitter callback is working
4. Monitor logs for "GPU state update" messages

### If tests fail:
1. Run with `-xvs` flags for detailed output
2. Check imports are correct
3. Verify mocks are set up properly
4. Use `pytest --pdb` for debugging

### If type checking fails:
1. Review error messages carefully
2. Check DeviceGPUState imports
3. Verify Mapping/Sequence types are correct
4. Use `basedpyright --version` to check compiler

---

## Quick Reference: Modified Files

| File | Changes | Lines |
|------|---------|-------|
| src/exo/master/placement.py | Add CSP logic + helpers | +50 |
| src/exo/worker/main.py | Initialize telemetry | +40 |
| src/exo/master/tests/test_placement_csp_integration.py | New unit tests | 100+ |
| src/exo/worker/tests/test_gpu_telemetry.py | New unit tests | 100+ |
| src/exo/shared/tests/test_gpu_integration_e2e.py | New integration tests | 100+ |

**Total new code**: ~440 lines (mostly tests)

---

## Success Criteria

After completing all tasks:

1. ✅ `uv run basedpyright` passes
2. ✅ `uv run ruff check` passes
3. ✅ `nix fmt` has no changes
4. ✅ `uv run pytest` passes
5. ✅ GPU state updates visible in master logs
6. ✅ CSP placement used for heterogeneous clusters
7. ✅ No regression in existing MLX placement
8. ✅ Project reaches 75-80% completion

---

## Estimated Timeline

| Task | Duration | Status |
|------|----------|--------|
| CSP Integration | 3h | Ready to start |
| Worker Integration | 4h | Ready to start |
| Master Handling | 3h | Ready to start |
| Testing | 6h | Ready to start |
| **Total** | **16h** | **~2 days focused work** |

---

## Common Pitfalls to Avoid

1. ❌ Forgetting to import new event types
2. ❌ Not handling None values for GPU state
3. ❌ Breaking existing MLX placement logic
4. ❌ Telemetry events emitted too frequently
5. ❌ Not testing error cases (missing GPU, device offline)
6. ❌ Forgetting to stop telemetry on shutdown
7. ❌ Type checker issues with Mapping types

---

## Questions to Answer Before Starting

1. **Should CSP be default for all clusters?**
   - Answer: No, only for heterogeneous (preserve MLX for homogeneous)

2. **What if GPU backend isn't available?**
   - Answer: Gracefully degrade (no telemetry, no CSP, use greedy)

3. **How often should telemetry be collected?**
   - Answer: 2 seconds (configurable, tune based on overhead)

4. **Should old clients work with new events?**
   - Answer: Yes, events are additive (backward compatible)

5. **How to test without real GPU?**
   - Answer: Mock GPUBackend, create synthetic device states

---

## Post-Session Actions

After completing Session 2:

1. **Update Status**: Mark completion in IMPLEMENTATION_STATUS.md
2. **Merge Code**: Create PR with all changes
3. **Deploy**: Test on staging cluster if available
4. **Document**: Update user guide with GPU features
5. **Plan Session 3**: Mobile apps or dashboard visualization

---

## Resources

- **CSP Placement**: `src/exo/master/placement_csp.py` (410+ lines)
- **GPU Backend**: `src/exo/gpu/backend.py` (300+ lines)
- **Telemetry Module**: `src/exo/worker/gpu_telemetry.py` (270 lines)
- **Event System**: `src/exo/shared/types/events.py`
- **State Management**: `src/exo/shared/apply.py`

---

## Final Notes

This roadmap provides detailed, actionable steps to complete the critical path for heterogeneous GPU clustering. Follow it sequentially, run tests frequently, and commit often.

The implementation is straightforward (mostly integration of existing components) and low-risk (existing event system handles state management).

**Go forth and cluster! 🚀**

