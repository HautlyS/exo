# Critical Path Implementation Plan

## Phase 1: Master Placement Integration (2-3 hours)

### 1.1 Modify placement.py to use CSP solver
- Import CSP placement solver
- Create a new `place_instance_with_gpu_awareness()` function
- Add toggle/configuration to use CSP for heterogeneous clusters
- Maintain backward compatibility with existing MLX placement

### 1.2 Add GPU topology validation
- Check if cluster has heterogeneous GPUs
- If yes, use CSP; if no, use existing logic
- Add logging to track placement decisions

---

## Phase 2: Cluster State Extension & Events (4-6 hours)

### 2.1 Create GPU telemetry events
- Add GPU-specific events to event.py
- DeviceGPUStateUpdated event
- MeasureGPUBandwidth event

### 2.2 Master GPU state tracking
- Listen for GPU telemetry events
- Update gpu_device_state in State
- Aggregate per-node GPU info

---

## Phase 3: GPU Telemetry Integration (6-8 hours)

### 3.1 Worker GPU telemetry collection
- Create worker telemetry task
- Periodic GPU monitoring
- Event emission

### 3.2 Master GPU event handling
- Handle incoming GPU state updates
- Update cluster state
- Track historical metrics

---

## Phase 4: Dashboard GPU Visualization (16-20 hours)

### 4.1 Backend API endpoints
- /api/gpu/devices - List GPUs
- /api/gpu/topology - Cluster topology
- /api/gpu/metrics - Real-time metrics

### 4.2 Frontend components
- GPU device card
- Cluster topology diagram
- Resource utilization gauges

---

## Total: ~35 hours to get heterogeneous clustering working end-to-end

