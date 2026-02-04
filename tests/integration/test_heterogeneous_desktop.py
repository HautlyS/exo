"""Integration tests for heterogeneous GPU clustering on desktop platforms.

Tests cross-platform device discovery, topology measurement, and optimal placement.
Run with: pytest tests/integration/test_heterogeneous_desktop.py -v
"""

import asyncio
import logging
import pytest
from typing import List, Dict

from exo.gpu.factory import GPUBackendFactory
from exo.gpu.backend import GPUBackend, GPUDevice
from exo.shared.gpu_telemetry_aggregator import GPUTelemetryAggregator

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class TestSinglePlatformClusters:
    """Test homogeneous GPU clusters on single platforms."""

    @pytest.mark.asyncio
    async def test_cuda_cluster_discovery(self):
        """Test discovering CUDA devices on Linux/Windows."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        # All devices should be same backend if homogeneous
        if len(devices) > 1:
            backends = {d.backend for d in devices}
            # Could be mixed backends, but in single cluster should be coordinated
            logger.info(f"Discovered {len(devices)} devices with backends: {backends}")
        
        for device in devices:
            assert device.device_id
            assert device.memory_bytes > 0
            assert device.compute_units > 0
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_device_properties_consistency(self):
        """Test that device properties are consistent across queries."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        # Properties should be stable across multiple queries
        for device in devices:
            retrieved = backend.get_device(device.device_id)
            assert retrieved is not None
            assert retrieved.memory_bytes == device.memory_bytes
            assert retrieved.compute_units == device.compute_units
            assert retrieved.vendor == device.vendor
        
        await backend.shutdown()


class TestMultiDeviceClustering:
    """Test multi-device GPU clustering."""

    @pytest.mark.asyncio
    async def test_cluster_metrics_aggregation(self):
        """Test aggregating metrics from multiple devices."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if len(devices) < 2:
            pytest.skip("Need 2+ devices for multi-device tests")
        
        # Simulate multi-node cluster
        devices_by_node = {
            "node1": devices[:len(devices)//2],
            "node2": devices[len(devices)//2:],
        }
        
        metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)
        
        assert metrics.total_devices == len(devices)
        assert metrics.total_memory_bytes > 0
        assert metrics.average_bandwidth_gbps > 0
        assert metrics.bottleneck_bandwidth_gbps > 0
        
        logger.info(metrics.format_cluster_summary())
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_optimal_device_selection(self):
        """Test selecting optimal devices for model placement."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        model_config = {
            "estimated_memory_bytes": 8 * 1024**3,  # 8 GB
            "tensor_operations": 1e12,
        }
        
        # Get optimal device
        selected = GPUTelemetryAggregator.get_optimal_devices(
            devices,
            model_config,
            count=min(2, len(devices))
        )
        
        assert len(selected) > 0
        assert selected[0] in devices
        
        logger.info(f"Selected devices: {[d.name for d in selected]}")
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_p2p_transfer_estimation(self):
        """Test P2P transfer time estimation between devices."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if len(devices) < 2:
            pytest.skip("Need 2+ devices for P2P tests")
        
        dev1, dev2 = devices[0], devices[1]
        size = 1024 * 1024 * 1024  # 1 GB
        
        transfer_time = GPUTelemetryAggregator.estimate_transfer_time(
            dev1, dev2, size
        )
        
        assert transfer_time >= 0
        logger.info(f"Estimated P2P transfer time: {transfer_time:.3f}s for {size/1024**3:.0f}GB")
        
        await backend.shutdown()


class TestHeterogeneousClusters:
    """Test heterogeneous clustering across platforms."""

    @pytest.mark.asyncio
    async def test_heterogeneous_device_scoring(self):
        """Test device scoring in heterogeneous environment."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        model_config = {
            "estimated_memory_bytes": 4 * 1024**3,  # 4 GB
            "tensor_operations": 1e12,
        }
        
        scores = GPUTelemetryAggregator.compute_device_scores(devices, model_config)
        
        # All devices should be scored
        assert len(scores) == len(devices)
        
        # Scores should be between 0 and 1
        for device_id, score in scores.items():
            assert 0 <= score.compute_score <= 1.0
            assert 0 <= score.memory_score <= 1.0
            assert 0 <= score.total_score <= 1.0
            
            logger.info(
                f"Device {score.name}: score={score.total_score:.3f} "
                f"(compute={score.compute_score:.2f}, memory={score.memory_score:.2f})"
            )
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_heterogeneity_detection(self):
        """Test detection of cluster heterogeneity."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        devices_by_node = {"node1": devices}
        metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)
        
        # Homogeneous cluster should have ratio ~1.0
        # Heterogeneous would have > 1.0
        assert metrics.heterogeneous_ratio >= 1.0
        
        if metrics.heterogeneous_ratio > 1.5:
            logger.info("Cluster is heterogeneous (ratio={:.2f}x)".format(
                metrics.heterogeneous_ratio
            ))
        else:
            logger.info("Cluster is homogeneous")
        
        await backend.shutdown()


class TestClusterMemoryManagement:
    """Test memory management across cluster."""

    @pytest.mark.asyncio
    async def test_memory_availability_tracking(self):
        """Test tracking available memory across devices."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        # Check memory info for all devices
        memory_info = {}
        for device in devices:
            info = await backend.get_device_memory_info(device.device_id)
            memory_info[device.device_id] = info
            
            total = info["total_bytes"] / 1024**3
            available = info["available_bytes"] / 1024**3
            
            logger.info(f"{device.name}: {available:.1f}GB / {total:.1f}GB available")
        
        # Calculate cluster memory
        total_cluster = sum(info["total_bytes"] for info in memory_info.values())
        avail_cluster = sum(info["available_bytes"] for info in memory_info.values())
        
        logger.info(f"Cluster total: {avail_cluster/1024**3:.1f}GB / {total_cluster/1024**3:.1f}GB")
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_memory_fit_for_model(self):
        """Test checking if cluster has enough memory for model."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        # Get total available memory
        total_available = 0
        for device in devices:
            info = await backend.get_device_memory_info(device.device_id)
            total_available += info["available_bytes"]
        
        # Check various model sizes
        model_sizes = [
            (1 * 1024**3, "1B parameter model (4GB)"),
            (7 * 1024**3, "7B parameter model (28GB)"),
            (13 * 1024**3, "13B parameter model (52GB)"),
            (70 * 1024**3, "70B parameter model (280GB)"),
        ]
        
        for model_memory, description in model_sizes:
            can_fit = total_available >= model_memory
            status = "✓ CAN FIT" if can_fit else "✗ INSUFFICIENT"
            logger.info(f"{description}: {status}")
        
        await backend.shutdown()


class TestClusterNetworkTopology:
    """Test network topology measurement for cluster."""

    @pytest.mark.asyncio
    async def test_bottleneck_bandwidth_detection(self):
        """Test identification of cluster bottleneck link."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        devices_by_node = {"node1": devices}
        metrics = GPUTelemetryAggregator.aggregate_cluster_metrics(devices_by_node)
        
        # Bottleneck should be minimum bandwidth
        assert metrics.bottleneck_bandwidth_gbps > 0
        assert metrics.bottleneck_bandwidth_gbps <= metrics.average_bandwidth_gbps
        
        logger.info(f"Average bandwidth: {metrics.average_bandwidth_gbps:.1f} GB/s")
        logger.info(f"Bottleneck bandwidth: {metrics.bottleneck_bandwidth_gbps:.1f} GB/s")
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_bandwidth_aware_placement(self):
        """Test that placement considers bandwidth constraints."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        # Large memory model should go to device with best bandwidth
        model_config = {
            "estimated_memory_bytes": 20 * 1024**3,  # 20 GB
            "tensor_operations": 1e15,  # Heavy compute
        }
        
        scores = GPUTelemetryAggregator.compute_device_scores(devices, model_config)
        
        # Device with best bandwidth score should be near top
        sorted_scores = sorted(scores.items(), key=lambda x: x[1].bandwidth_score, reverse=True)
        best_bandwidth_device = sorted_scores[0][0]
        
        logger.info(f"Device with best bandwidth: {best_bandwidth_device}")
        
        await backend.shutdown()


class TestClusterThermalMonitoring:
    """Test thermal monitoring across cluster (for future mobile support)."""

    @pytest.mark.asyncio
    async def test_device_temperature_monitoring(self):
        """Test monitoring device temperatures."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        temperatures = {}
        for device in devices:
            temp = await backend.get_device_temperature(device.device_id)
            if temp is not None:
                temperatures[device.device_id] = temp
                logger.info(f"{device.name}: {temp:.1f}°C")
        
        if not temperatures:
            logger.info("Temperature monitoring not available on this platform")
        
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_device_power_monitoring(self):
        """Test monitoring device power usage."""
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError:
            pytest.skip("No GPU backend available")
        
        devices = backend.list_devices()
        
        if not devices:
            pytest.skip("No GPU devices found")
        
        power_usage = {}
        for device in devices:
            power = await backend.get_device_power_usage(device.device_id)
            if power is not None:
                power_usage[device.device_id] = power
                logger.info(f"{device.name}: {power:.1f}W")
        
        if not power_usage:
            logger.info("Power monitoring not available on this platform")
        
        await backend.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
