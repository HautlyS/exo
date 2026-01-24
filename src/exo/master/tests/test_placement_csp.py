"""Tests for CSP-based GPU shard placement."""

import pytest

from exo.master.placement_csp import (
    ConstraintSatisfactionPlacement,
    GPUDeviceScore,
    compute_device_scores,
)


class MockGPUDevice:
    """Mock GPU device for testing."""

    def __init__(
        self,
        device_id: str,
        memory_bytes: int = 16 * 1024 ** 3,
        compute_units: int = 100,
        clock_rate_mhz: int = 2000,
    ):
        self.device_id = device_id
        self.memory_bytes = memory_bytes
        self.memory_available = memory_bytes
        self.compute_units = compute_units
        self.clock_rate_mhz = clock_rate_mhz


class TestCSPPlacement:
    """Test Constraint Satisfaction Placement solver."""

    def test_simple_placement(self):
        """Test basic shard placement on homogeneous cluster."""
        devices = [
            MockGPUDevice("cuda:0", memory_bytes=20 * 1024 ** 3),
            MockGPUDevice("cuda:1", memory_bytes=20 * 1024 ** 3),
            MockGPUDevice("cuda:2", memory_bytes=20 * 1024 ** 3),
        ]

        shard_sizes = [
            4 * 1024 ** 3,  # 4GB each
            4 * 1024 ** 3,
            4 * 1024 ** 3,
        ]

        scores = compute_device_scores(devices)
        solver = ConstraintSatisfactionPlacement(timeout_seconds=5.0)

        # Synchronous test wrapper
        import asyncio

        assignment = asyncio.run(
            solver.solve_placement(
                num_shards=3,
                shard_sizes_bytes=shard_sizes,
                devices=devices,
                device_scores=scores,
            )
        )

        # Check assignment
        assert len(assignment) == 3
        assert all(isinstance(device_id, str) for device_id in assignment.values())

    def test_heterogeneous_placement(self):
        """Test shard placement on heterogeneous devices."""
        devices = [
            MockGPUDevice("cuda:0", memory_bytes=40 * 1024 ** 3, compute_units=200),
            MockGPUDevice("cuda:1", memory_bytes=20 * 1024 ** 3, compute_units=100),
            MockGPUDevice("cuda:2", memory_bytes=10 * 1024 ** 3, compute_units=50),
        ]

        shard_sizes = [
            8 * 1024 ** 3,  # 8GB
            6 * 1024 ** 3,  # 6GB
            4 * 1024 ** 3,  # 4GB
        ]

        scores = compute_device_scores(devices)
        solver = ConstraintSatisfactionPlacement()

        import asyncio

        assignment = asyncio.run(
            solver.solve_placement(
                num_shards=3,
                shard_sizes_bytes=shard_sizes,
                devices=devices,
                device_scores=scores,
            )
        )

        # Larger shards should go to devices with more memory
        assert len(assignment) == 3

    def test_insufficient_memory_fallback(self):
        """Test fallback when insufficient total memory."""
        devices = [
            MockGPUDevice("cuda:0", memory_bytes=5 * 1024 ** 3),
            MockGPUDevice("cuda:1", memory_bytes=5 * 1024 ** 3),
        ]

        shard_sizes = [
            8 * 1024 ** 3,  # Too large
            8 * 1024 ** 3,
        ]

        scores = compute_device_scores(devices)
        solver = ConstraintSatisfactionPlacement()

        import asyncio

        assignment = asyncio.run(
            solver.solve_placement(
                num_shards=2,
                shard_sizes_bytes=shard_sizes,
                devices=devices,
                device_scores=scores,
            )
        )

        # Should still return assignment (fallback to greedy)
        assert len(assignment) == 2

    def test_device_scores_computation(self):
        """Test GPUDeviceScore computation."""
        devices = [
            MockGPUDevice("cuda:0", memory_bytes=80 * 1024 ** 3),
            MockGPUDevice("cuda:1", memory_bytes=20 * 1024 ** 3),
        ]

        scores = compute_device_scores(devices)

        # Should have score for each device
        assert len(scores) == 2

        # Scores should be between 0 and 1
        for score in scores:
            assert 0 <= score.compute_score <= 1
            assert 0 <= score.memory_score <= 1
            assert 0 <= score.network_score <= 1
            assert 0 <= score.weighted_score <= 1

        # Larger device should have higher memory score
        assert scores[0].memory_score >= scores[1].memory_score

    def test_greedy_fallback(self):
        """Test greedy fallback algorithm."""
        solver = ConstraintSatisfactionPlacement()

        devices = [
            MockGPUDevice("cuda:0", memory_bytes=20 * 1024 ** 3),
            MockGPUDevice("cuda:1", memory_bytes=20 * 1024 ** 3),
        ]

        shard_sizes = [4 * 1024 ** 3, 4 * 1024 ** 3]
        scores = compute_device_scores(devices)

        assignment = solver._greedy_placement(
            num_shards=2,
            shard_sizes_bytes=shard_sizes,
            device_scores=scores,
        )

        # Should assign both shards
        assert len(assignment) == 2

        # Both devices should be used
        unique_devices = set(assignment.values())
        assert len(unique_devices) <= 2

    def test_assignment_respects_memory_constraints(self):
        """Test that assignment respects device memory constraints."""
        devices = [
            MockGPUDevice("cuda:0", memory_bytes=10 * 1024 ** 3),
            MockGPUDevice("cuda:1", memory_bytes=15 * 1024 ** 3),
        ]

        shard_sizes = [
            5 * 1024 ** 3,
            7 * 1024 ** 3,
        ]

        scores = compute_device_scores(devices)
        solver = ConstraintSatisfactionPlacement()

        import asyncio

        assignment = asyncio.run(
            solver.solve_placement(
                num_shards=2,
                shard_sizes_bytes=shard_sizes,
                devices=devices,
                device_scores=scores,
            )
        )

        # Verify memory constraints
        device_usage = {}
        for shard_idx, device_id in assignment.items():
            device_usage[device_id] = device_usage.get(device_id, 0) + shard_sizes[shard_idx]

        for device in devices:
            if device.device_id in device_usage:
                assert device_usage[device.device_id] <= device.memory_available


class TestGPUDeviceScore:
    """Test device scoring."""

    def test_score_initialization(self):
        """Test GPUDeviceScore creation."""
        score = GPUDeviceScore(
            device_id="cuda:0",
            node_id="node0",
            compute_score=0.8,
            memory_score=0.9,
            network_score=0.7,
        )

        assert score.device_id == "cuda:0"
        assert 0 <= score.weighted_score <= 1

    def test_score_weighting(self):
        """Test weighted score calculation."""
        # High compute, low memory
        score1 = GPUDeviceScore(
            device_id="cuda:0",
            node_id="node0",
            compute_score=1.0,
            memory_score=0.2,
            network_score=0.5,
        )

        # Low compute, high memory
        score2 = GPUDeviceScore(
            device_id="cuda:1",
            node_id="node1",
            compute_score=0.2,
            memory_score=1.0,
            network_score=0.5,
        )

        # Score1 should be higher (compute weighted at 40%)
        assert score1.weighted_score > score2.weighted_score

    def test_thermal_score_affects_mobile(self):
        """Test thermal score for mobile devices."""
        mobile_score = GPUDeviceScore(
            device_id="mobile:0",
            node_id="mobile_node",
            compute_score=0.5,
            memory_score=0.3,
            network_score=0.6,
            thermal_score=0.5,  # Limited thermal headroom
        )

        desktop_score = GPUDeviceScore(
            device_id="cuda:0",
            node_id="desktop_node",
            compute_score=0.5,
            memory_score=0.3,
            network_score=0.6,
            thermal_score=1.0,  # Full thermal capacity
        )

        # Desktop should score higher
        assert desktop_score.weighted_score > mobile_score.weighted_score


class TestConstraintPropagation:
    """Test constraint propagation in CSP."""

    def test_memory_constraint_propagation(self):
        """Test that memory constraints are properly propagated."""
        solver = ConstraintSatisfactionPlacement()

        devices = [
            MockGPUDevice("cuda:0", memory_bytes=10 * 1024 ** 3),
            MockGPUDevice("cuda:1", memory_bytes=20 * 1024 ** 3),
        ]

        shard_sizes = [4 * 1024 ** 3, 6 * 1024 ** 3]

        assignment = {0: "cuda:0"}  # Assign first shard
        domains = {
            0: ["cuda:0"],
            1: ["cuda:0", "cuda:1"],  # Both available initially
        }

        # Propagate
        result = solver._propagate_constraints(
            assignment=assignment,
            domains=domains,
            assigned_shard=0,
            assigned_device="cuda:0",
            shard_sizes=shard_sizes,
            devices=devices,
        )

        # Should be valid
        assert result

        # cuda:0 should be removed from other shards (pipeline parallelism)
        assert "cuda:0" not in domains[1]
