"""Unit tests for GPU telemetry aggregation."""

import pytest
from exo.gpu.backend import GPUDevice
from exo.shared.gpu_telemetry_aggregator import (
    GPUTelemetryAggregator,
    ClusterGPUMetrics,
    GPUDeviceScore,
)


# Test fixtures

@pytest.fixture
def nvidia_device():
    """Create a mock NVIDIA GPU device."""
    return GPUDevice(
        device_id="cuda:0",
        name="NVIDIA RTX 4090",
        vendor="nvidia",
        backend="cuda",
        compute_capability="8.9",
        memory_bytes=24 * 1024**3,  # 24 GB
        memory_available=24 * 1024**3,
        compute_units=128,
        tensor_core_count=16384,
        max_threads_per_block=1024,
        clock_rate_mhz=2500,
        bandwidth_gbps=1008.0,
        support_level="full",
        driver_version="535.0",
        backend_name="cuda",
    )


@pytest.fixture
def amd_device():
    """Create a mock AMD GPU device."""
    return GPUDevice(
        device_id="rocm:0",
        name="AMD Radeon RX 7900 XT",
        vendor="amd",
        backend="rocm",
        compute_capability="RDNA3",
        memory_bytes=20 * 1024**3,  # 20 GB
        memory_available=20 * 1024**3,
        compute_units=96,
        tensor_core_count=6144,
        max_threads_per_block=1024,
        clock_rate_mhz=2500,
        bandwidth_gbps=960.0,
        support_level="full",
        driver_version="5.7",
        backend_name="rocm",
    )


@pytest.fixture
def apple_device():
    """Create a mock Apple GPU device."""
    return GPUDevice(
        device_id="metal:0",
        name="Apple M2 Max",
        vendor="apple",
        backend="metal",
        compute_capability="M2",
        memory_bytes=32 * 1024**3,  # 32 GB unified memory
        memory_available=32 * 1024**3,
        compute_units=10,
        tensor_core_count=0,
        max_threads_per_block=256,
        clock_rate_mhz=3500,
        bandwidth_gbps=200.0,
        support_level="full",
        driver_version="Metal 3.0",
        backend_name="metal",
    )


# Tests for aggregate_cluster_metrics

class TestClusterAggregation:
    """Test cluster-level metric aggregation."""

    def test_single_device_cluster(self, nvidia_device):
        """Test aggregation with single device."""
        devices_by_node = {"node1": [nvidia_device]}
        
        metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)
        
        assert metrics.total_devices == 1
        assert metrics.total_memory_bytes == nvidia_device.memory_bytes
        assert metrics.total_compute_units == nvidia_device.compute_units
        assert metrics.bottleneck_bandwidth_gbps == nvidia_device.bandwidth_gbps
        assert metrics.average_bandwidth_gbps == nvidia_device.bandwidth_gbps

    def test_multi_device_cluster(self, nvidia_device, amd_device, apple_device):
        """Test aggregation with multiple heterogeneous devices."""
        devices_by_node = {
            "node1": [nvidia_device, amd_device],
            "node2": [apple_device],
        }
        
        metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)
        
        assert metrics.total_devices == 3
        assert metrics.total_memory_bytes == (
            nvidia_device.memory_bytes +
            amd_device.memory_bytes +
            apple_device.memory_bytes
        )
        assert metrics.total_compute_units == (
            nvidia_device.compute_units +
            amd_device.compute_units +
            apple_device.compute_units
        )
        assert metrics.bottleneck_bandwidth_gbps == apple_device.bandwidth_gbps
        assert metrics.device_count_by_vendor == {"nvidia": 1, "amd": 1, "apple": 1}

    def test_vendor_counting(self, nvidia_device, amd_device):
        """Test vendor counting in multi-device cluster."""
        devices_by_node = {
            "node1": [nvidia_device, nvidia_device],
            "node2": [amd_device],
        }
        
        metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)
        
        assert metrics.device_count_by_vendor["nvidia"] == 2
        assert metrics.device_count_by_vendor["amd"] == 1

    def test_heterogeneous_ratio(self, nvidia_device, apple_device):
        """Test heterogeneity ratio calculation."""
        devices_by_node = {
            "node1": [nvidia_device],
            "node2": [apple_device],
        }
        
        metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)
        
        # Heterogeneity should be > 1 for different device types
        assert metrics.heterogeneous_ratio > 1.0

    def test_empty_cluster(self):
        """Test handling of empty cluster."""
        devices_by_node = {}
        
        metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)
        
        assert metrics.total_devices == 0
        assert metrics.total_memory_bytes == 0
        assert metrics.heterogeneous_ratio == 1.0


# Tests for compute_device_scores

class TestDeviceScoring:
    """Test device scoring for shard placement."""

    def test_single_device_scoring(self, nvidia_device):
        """Test scoring with single device."""
        model_config = {
            "estimated_memory_bytes": 8 * 1024**3,  # 8 GB
            "tensor_operations": 1e12,  # 1 TFLOP
        }
        
        scores = GPUTelemetryAggregator.compute_device_scores([nvidia_device], model_config)
        
        assert nvidia_device.device_id in scores
        score = scores[nvidia_device.device_id]
        assert 0 <= score.compute_score <= 1.0
        assert 0 <= score.memory_score <= 1.0
        assert 0 <= score.total_score <= 1.0

    def test_heterogeneous_scoring(self, nvidia_device, apple_device):
        """Test scoring with heterogeneous devices."""
        model_config = {
            "estimated_memory_bytes": 8 * 1024**3,
            "tensor_operations": 1e12,
        }
        
        scores = GPUTelemetryAggregator.compute_device_scores(
            [nvidia_device, apple_device],
            model_config
        )
        
        # NVIDIA should score higher for compute
        nvidia_score = scores[nvidia_device.device_id].total_score
        apple_score = scores[apple_device.device_id].total_score
        assert nvidia_score > apple_score

    def test_memory_insufficient(self, apple_device):
        """Test scoring when device has insufficient memory."""
        model_config = {
            "estimated_memory_bytes": 40 * 1024**3,  # 40 GB (more than device has)
            "tensor_operations": 1e12,
        }
        
        scores = GPUTelemetryAggregator.compute_device_scores([apple_device], model_config)
        
        score = scores[apple_device.device_id]
        # Memory score should be penalized
        assert score.memory_score < 0.5

    def test_memory_abundant(self, apple_device):
        """Test scoring when device has abundant memory."""
        model_config = {
            "estimated_memory_bytes": 2 * 1024**3,  # 2 GB
            "tensor_operations": 1e12,
        }
        
        scores = GPUTelemetryAggregator.compute_device_scores([apple_device], model_config)
        
        score = scores[apple_device.device_id]
        # Memory score should be high
        assert score.memory_score > 0.8


# Tests for get_optimal_devices

class TestOptimalDeviceSelection:
    """Test selection of optimal devices for placement."""

    def test_single_best_device(self, nvidia_device, apple_device):
        """Test selecting single best device."""
        model_config = {
            "estimated_memory_bytes": 8 * 1024**3,
            "tensor_operations": 1e12,
        }
        
        result = GPUTelemetryAggregator.get_optimal_devices(
            [nvidia_device, apple_device],
            model_config,
            count=1
        )
        
        assert len(result) == 1
        assert result[0].device_id == nvidia_device.device_id

    def test_multiple_devices(self, nvidia_device, amd_device, apple_device):
        """Test selecting multiple devices ranked by score."""
        model_config = {
            "estimated_memory_bytes": 8 * 1024**3,
            "tensor_operations": 1e12,
        }
        
        result = GPUTelemetryAggregator.get_optimal_devices(
            [nvidia_device, amd_device, apple_device],
            model_config,
            count=2
        )
        
        assert len(result) == 2
        # Should be high-performance devices
        device_ids = {d.device_id for d in result}
        assert nvidia_device.device_id in device_ids

    def test_request_more_than_available(self, nvidia_device):
        """Test requesting more devices than available."""
        model_config = {
            "estimated_memory_bytes": 8 * 1024**3,
            "tensor_operations": 1e12,
        }
        
        result = GPUTelemetryAggregator.get_optimal_devices(
            [nvidia_device],
            model_config,
            count=5
        )
        
        assert len(result) == 1


# Tests for estimate_transfer_time

class TestTransferTimeEstimation:
    """Test data transfer time estimation."""

    def test_same_device_transfer(self, nvidia_device):
        """Test transfer time for same device (should be 0)."""
        time = GPUTelemetryAggregator.estimate_transfer_time(
            nvidia_device,
            nvidia_device,
            1024 * 1024 * 1024,  # 1 GB
        )
        
        assert time == 0.0

    def test_p2p_transfer(self, nvidia_device, amd_device):
        """Test P2P transfer between different vendors."""
        time = GPUTelemetryAggregator.estimate_transfer_time(
            nvidia_device,
            amd_device,
            1024 * 1024 * 1024,  # 1 GB
        )
        
        # Should include latency and transfer time
        assert time > 0
        # Should be reasonable (less than 1 second for 1GB on 10GB/s network)
        assert time < 1.0

    def test_large_transfer(self, nvidia_device):
        """Test transfer time estimation for large data."""
        size = 10 * 1024 * 1024 * 1024  # 10 GB
        time = GPUTelemetryAggregator.estimate_transfer_time(
            nvidia_device,
            nvidia_device,
            size,
        )
        
        # Same device, should be 0
        assert time == 0.0


# Tests for format_cluster_summary

class TestClusterSummaryFormatting:
    """Test cluster metrics formatting."""

    def test_summary_format(self, nvidia_device, amd_device):
        """Test that summary formats correctly."""
        devices_by_node = {"node1": [nvidia_device, amd_device]}
        metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)
        
        summary = GPUTelemetryAggregator.format_cluster_summary(metrics)
        
        assert "GPU Cluster Metrics" in summary
        assert "Total Devices: 2" in summary
        assert "nvidia(1)" in summary
        assert "amd(1)" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
