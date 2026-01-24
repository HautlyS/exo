"""Tests for GPU-aware topology."""

import pytest

from exo.shared.gpu_topology import (
    GPUAwareLinkMetrics,
    GPUAwareTopology,
    GPUClusterMetrics,
    compute_cluster_metrics,
)
from exo.shared.types.common import NodeId


class TestGPUAwareTopology:
    """Test GPU-aware topology functionality."""

    def test_basic_topology_creation(self):
        """Test creating a GPU-aware topology."""
        topology = GPUAwareTopology()
        assert topology is not None

    def test_register_gpu_devices(self):
        """Test registering GPU devices to nodes."""
        topology = GPUAwareTopology()

        node_id: NodeId = "node_1"
        devices = [
            {
                "device_id": "cuda:0",
                "name": "NVIDIA A100",
                "memory_bytes": 40 * 1024 ** 3,
            },
            {
                "device_id": "cuda:1",
                "name": "NVIDIA A100",
                "memory_bytes": 40 * 1024 ** 3,
            },
        ]

        topology.set_node_gpu_devices(node_id, devices)

        # Verify registration
        retrieved = topology.get_node_gpu_devices(node_id)
        assert len(retrieved) == 2
        assert retrieved[0]["device_id"] == "cuda:0"

    def test_link_metrics(self):
        """Test setting and retrieving link metrics."""
        topology = GPUAwareTopology()

        source = NodeId("node_1")
        sink = NodeId("node_2")

        metrics = GPUAwareLinkMetrics(
            source_node=source,
            sink_node=sink,
            latency_ms=5.0,
            bandwidth_gbps=200.0,
            p2p_supported=True,
            p2p_bandwidth_gbps=300.0,
            link_type="rdma",
        )

        topology.set_link_metrics(source, sink, metrics)

        # Verify both directions
        forward = topology.get_link_metrics(source, sink)
        backward = topology.get_link_metrics(sink, source)

        assert forward.bandwidth_gbps == 200.0
        assert backward.bandwidth_gbps == 200.0

    def test_bandwidth_selection_with_p2p(self):
        """Test that P2P bandwidth is preferred when available."""
        topology = GPUAwareTopology()

        source = NodeId("node_1")
        sink = NodeId("node_2")

        metrics = GPUAwareLinkMetrics(
            source_node=source,
            sink_node=sink,
            latency_ms=5.0,
            bandwidth_gbps=100.0,
            p2p_supported=True,
            p2p_bandwidth_gbps=300.0,
            link_type="rdma",
        )

        topology.set_link_metrics(source, sink, metrics)

        bandwidth = topology.get_bandwidth_between(source, sink)
        assert bandwidth == 300.0  # P2P preferred

    def test_transfer_time_estimation(self):
        """Test data transfer time estimation."""
        topology = GPUAwareTopology()

        source = NodeId("node_1")
        sink = NodeId("node_2")

        metrics = GPUAwareLinkMetrics(
            source_node=source,
            sink_node=sink,
            latency_ms=1.0,
            bandwidth_gbps=100.0,
            p2p_supported=False,
            link_type="ethernet",
        )

        topology.set_link_metrics(source, sink, metrics)

        # 1GB data, 100 Gbps link
        # Transfer time = 1GB * 8 bits/byte / 100 Gbps = 80ms
        data_size = 1024 ** 3
        estimated_ms = topology.estimate_transfer_time_ms(source, sink, data_size)

        # Should include latency + transfer
        assert estimated_ms > 1.0  # At least latency
        assert estimated_ms < 100.0  # Less than naive estimate

    def test_find_p2p_capable_pairs(self):
        """Test finding P2P capable node pairs."""
        topology = GPUAwareTopology()

        node1 = NodeId("node_1")
        node2 = NodeId("node_2")
        node3 = NodeId("node_3")

        # P2P between node1 and node2
        metrics1 = GPUAwareLinkMetrics(
            source_node=node1,
            sink_node=node2,
            latency_ms=1.0,
            bandwidth_gbps=100.0,
            p2p_supported=True,
            p2p_bandwidth_gbps=300.0,
        )
        topology.set_link_metrics(node1, node2, metrics1)

        # No P2P between node2 and node3
        metrics2 = GPUAwareLinkMetrics(
            source_node=node2,
            sink_node=node3,
            latency_ms=10.0,
            bandwidth_gbps=50.0,
            p2p_supported=False,
        )
        topology.set_link_metrics(node2, node3, metrics2)

        p2p_pairs = topology.find_p2p_capable_pairs()

        # Should find node1 <-> node2
        assert len([p for p in p2p_pairs if p in [(node1, node2), (node2, node1)]]) >= 1

    def test_cluster_diameter(self):
        """Test cluster diameter calculation."""
        topology = GPUAwareTopology()

        node1 = NodeId("node_1")
        node2 = NodeId("node_2")
        node3 = NodeId("node_3")

        # Edges with different latencies
        metrics1 = GPUAwareLinkMetrics(
            source_node=node1,
            sink_node=node2,
            latency_ms=5.0,
            bandwidth_gbps=100.0,
        )
        topology.set_link_metrics(node1, node2, metrics1)

        metrics2 = GPUAwareLinkMetrics(
            source_node=node2,
            sink_node=node3,
            latency_ms=20.0,
            bandwidth_gbps=50.0,
        )
        topology.set_link_metrics(node2, node3, metrics2)

        diameter = topology.get_cluster_diameter_ms()
        assert diameter == 20.0  # Maximum latency

    def test_average_bandwidth(self):
        """Test average bandwidth calculation."""
        topology = GPUAwareTopology()

        node1 = NodeId("node_1")
        node2 = NodeId("node_2")

        metrics = GPUAwareLinkMetrics(
            source_node=node1,
            sink_node=node2,
            latency_ms=5.0,
            bandwidth_gbps=100.0,
        )
        topology.set_link_metrics(node1, node2, metrics)

        avg_bw = topology.get_average_bandwidth_gbps()

        # Both directions have same bandwidth
        assert avg_bw == 100.0

    def test_topology_summary(self):
        """Test topology summary generation."""
        topology = GPUAwareTopology()

        node1 = NodeId("node_1")
        node2 = NodeId("node_2")

        # Register devices
        devices1 = [
            {
                "device_id": "cuda:0",
                "name": "A100",
                "memory_bytes": 40 * 1024 ** 3,
            }
        ]
        topology.set_node_gpu_devices(node1, devices1)

        devices2 = [
            {
                "device_id": "cuda:0",
                "name": "A100",
                "memory_bytes": 40 * 1024 ** 3,
            }
        ]
        topology.set_node_gpu_devices(node2, devices2)

        # Add link
        metrics = GPUAwareLinkMetrics(
            source_node=node1,
            sink_node=node2,
            latency_ms=5.0,
            bandwidth_gbps=100.0,
        )
        topology.set_link_metrics(node1, node2, metrics)

        summary = topology.print_topology_summary()

        assert "Nodes: 2" in summary
        assert "node_1" in summary  # Node info instead of device ID
        assert "100.0Gbps" in summary


class TestGPUClusterMetrics:
    """Test GPU cluster metrics."""

    def test_metrics_computation(self):
        """Test computing metrics from topology."""
        topology = GPUAwareTopology()

        node1 = NodeId("node_1")
        node2 = NodeId("node_2")

        # Register large and small devices
        devices1 = [
            {
                "device_id": "cuda:0",
                "name": "A100",
                "memory_bytes": 40 * 1024 ** 3,
            }
        ]
        topology.set_node_gpu_devices(node1, devices1)

        devices2 = [
            {
                "device_id": "cuda:0",
                "name": "L40S",
                "memory_bytes": 48 * 1024 ** 3,
            }
        ]
        topology.set_node_gpu_devices(node2, devices2)

        # Add link
        metrics = GPUAwareLinkMetrics(
            source_node=node1,
            sink_node=node2,
            latency_ms=5.0,
            bandwidth_gbps=100.0,
            p2p_supported=True,
        )
        topology.set_link_metrics(node1, node2, metrics)

        # Compute metrics
        cluster_metrics = compute_cluster_metrics(topology)

        assert cluster_metrics.total_devices == 2
        assert cluster_metrics.total_memory_bytes == (40 + 48) * 1024 ** 3
        assert cluster_metrics.p2p_capable_nodes >= 1

    def test_bottleneck_detection(self):
        """Test detection of low-bandwidth links."""
        topology = GPUAwareTopology()

        node1 = NodeId("node_1")
        node2 = NodeId("node_2")

        # Very slow link
        metrics = GPUAwareLinkMetrics(
            source_node=node1,
            sink_node=node2,
            latency_ms=50.0,
            bandwidth_gbps=10.0,  # Bottleneck
        )
        topology.set_link_metrics(node1, node2, metrics)

        cluster_metrics = compute_cluster_metrics(topology)

        # Should detect bottleneck
        assert cluster_metrics.num_bottleneck_links > 0
