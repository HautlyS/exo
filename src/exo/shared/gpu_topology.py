"""GPU-aware cluster topology with network metrics.

Extends the base Topology with GPU-specific information:
- Device capabilities per node
- Link metrics (latency, bandwidth, P2P feasibility)
- Network-aware scoring for shard placement
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from exo.shared.topology import Topology
from exo.shared.types.common import NodeId

logger = logging.getLogger(__name__)


@dataclass
class GPUAwareLinkMetrics:
    """Metrics for network link between two nodes with GPUs.
    
    Used for placement decisions and bandwidth estimation.
    """

    source_node: NodeId
    sink_node: NodeId
    latency_ms: float  # Round-trip latency
    bandwidth_gbps: float  # Available bandwidth
    p2p_supported: bool = False  # Direct GPU-to-GPU transfer possible
    p2p_bandwidth_gbps: float = 0.0  # P2P bandwidth if supported
    link_type: str = "socket"  # 'socket', 'ethernet', 'rdma', 'thunderbolt'


@dataclass
class GPUAwareTopology(Topology):
    """Extended topology with GPU device tracking and link metrics."""

    # Device capabilities per node
    _node_gpu_devices: dict[NodeId, list[dict]] = field(default_factory=dict)
    
    # Link metrics between nodes
    _link_metrics: dict[tuple[NodeId, NodeId], GPUAwareLinkMetrics] = field(
        default_factory=dict
    )

    def set_node_gpu_devices(self, node_id: NodeId, devices: list[dict]) -> None:
        """Register GPU devices for a node.
        
        Args:
            node_id: Node identifier
            devices: List of device dicts with (device_id, name, memory_bytes, etc.)
        """
        self.add_node(node_id)  # Ensure node exists
        self._node_gpu_devices[node_id] = devices
        logger.info(f"Registered {len(devices)} GPU(s) on node {node_id}")

    def get_node_gpu_devices(self, node_id: NodeId) -> list[dict]:
        """Get GPU devices for a node."""
        return self._node_gpu_devices.get(node_id, [])

    def set_link_metrics(
        self,
        source: NodeId,
        sink: NodeId,
        metrics: GPUAwareLinkMetrics,
    ) -> None:
        """Register link metrics between two nodes.
        
        Args:
            source: Source node
            sink: Sink node
            metrics: Link metrics (latency, bandwidth, P2P support)
        """
        self.add_node(source)
        self.add_node(sink)
        
        # Store both directions
        self._link_metrics[(source, sink)] = metrics
        self._link_metrics[(sink, source)] = GPUAwareLinkMetrics(
            source_node=sink,
            sink_node=source,
            latency_ms=metrics.latency_ms,
            bandwidth_gbps=metrics.bandwidth_gbps,
            p2p_supported=metrics.p2p_supported,
            p2p_bandwidth_gbps=metrics.p2p_bandwidth_gbps,
            link_type=metrics.link_type,
        )
        logger.debug(
            f"Set link metrics {source} -> {sink}: "
            f"{metrics.latency_ms}ms, {metrics.bandwidth_gbps}Gbps"
        )

    def get_link_metrics(
        self,
        source: NodeId,
        sink: NodeId,
    ) -> Optional[GPUAwareLinkMetrics]:
        """Get link metrics between two nodes."""
        return self._link_metrics.get((source, sink))

    def get_bandwidth_between(self, source: NodeId, sink: NodeId) -> float:
        """Get available bandwidth (Gbps) between nodes, with P2P if possible."""
        metrics = self.get_link_metrics(source, sink)
        if not metrics:
            return 0.0
        
        # Prefer P2P if available
        if metrics.p2p_supported and metrics.p2p_bandwidth_gbps > 0:
            return metrics.p2p_bandwidth_gbps
        
        return metrics.bandwidth_gbps

    def get_latency_between(self, source: NodeId, sink: NodeId) -> float:
        """Get latency (ms) between nodes."""
        metrics = self.get_link_metrics(source, sink)
        return metrics.latency_ms if metrics else float("inf")

    def estimate_transfer_time_ms(
        self,
        source: NodeId,
        sink: NodeId,
        data_size_bytes: int,
    ) -> float:
        """Estimate time to transfer data between nodes.
        
        Accounts for bandwidth and latency.
        """
        bandwidth_gbps = self.get_bandwidth_between(source, sink)
        if bandwidth_gbps <= 0:
            return float("inf")
        
        latency_ms = self.get_latency_between(source, sink)
        
        # Data transfer time + latency
        transfer_ms = (data_size_bytes * 8 / (bandwidth_gbps * 1e9)) * 1000
        return latency_ms + transfer_ms

    def find_p2p_capable_pairs(self) -> list[tuple[NodeId, NodeId]]:
        """Find all node pairs that support GPU P2P."""
        p2p_pairs = []
        for (src, sink), metrics in self._link_metrics.items():
            if metrics.p2p_supported:
                p2p_pairs.append((src, sink))
        return p2p_pairs

    def get_cluster_diameter_ms(self) -> float:
        """Get maximum latency between any two nodes (cluster diameter)."""
        max_latency = 0.0
        for metrics in self._link_metrics.values():
            max_latency = max(max_latency, metrics.latency_ms)
        return max_latency

    def get_average_bandwidth_gbps(self) -> float:
        """Get average bandwidth across all links."""
        if not self._link_metrics:
            return 0.0
        
        total = sum(m.bandwidth_gbps for m in self._link_metrics.values())
        return total / len(self._link_metrics)

    def print_topology_summary(self) -> str:
        """Generate human-readable topology summary."""
        lines = []
        lines.append("=== GPU-Aware Cluster Topology ===")
        
        # Nodes and devices
        lines.append(f"\nNodes: {len(self._vertex_indices)}")
        for node_id, devices in self._node_gpu_devices.items():
            total_memory = sum(d.get("memory_bytes", 0) for d in devices)
            lines.append(f"  {node_id}: {len(devices)} GPU(s), {total_memory / 1e9:.1f}GB")
        
        # Links
        links_seen = set()
        lines.append(f"\nLinks:")
        for (src, sink), metrics in self._link_metrics.items():
            if (src, sink) not in links_seen and (sink, src) not in links_seen:
                p2p_str = " [P2P]" if metrics.p2p_supported else ""
                lines.append(
                    f"  {src} <-> {sink}: "
                    f"{metrics.latency_ms:.1f}ms, {metrics.bandwidth_gbps:.1f}Gbps{p2p_str}"
                )
                links_seen.add((src, sink))
        
        # Summary
        lines.append(f"\nCluster diameter: {self.get_cluster_diameter_ms():.1f}ms")
        lines.append(f"Average bandwidth: {self.get_average_bandwidth_gbps():.1f}Gbps")
        
        return "\n".join(lines)


@dataclass
class GPUClusterMetrics:
    """Overall cluster-level metrics derived from GPU-aware topology."""

    total_devices: int = 0
    total_memory_bytes: int = 0
    average_latency_ms: float = 0.0
    average_bandwidth_gbps: float = 0.0
    p2p_capable_nodes: int = 0
    num_bottleneck_links: int = 0


async def measure_cluster_bandwidth(
    topology: GPUAwareTopology,
) -> tuple[float, dict[tuple[NodeId, NodeId], float]]:
    """Measure available bandwidth between all node pairs.
    
    Performs lightweight bandwidth probes (async).
    
    Returns:
        (average_bandwidth, per_link_bandwidth)
    """
    # TODO: Implement actual bandwidth measurement
    # For now, return placeholder
    return topology.get_average_bandwidth_gbps(), {}


async def measure_cluster_latency(
    topology: GPUAwareTopology,
) -> tuple[float, dict[tuple[NodeId, NodeId], float]]:
    """Measure latency between all node pairs.
    
    Performs ping-pong latency tests (async).
    
    Returns:
        (average_latency, per_link_latency)
    """
    # TODO: Implement actual latency measurement
    return topology.get_cluster_diameter_ms(), {}


def compute_cluster_metrics(topology: GPUAwareTopology) -> GPUClusterMetrics:
    """Compute overall metrics from GPU-aware topology."""
    metrics = GPUClusterMetrics()
    
    # Count devices and memory
    for devices in topology._node_gpu_devices.values():
        metrics.total_devices += len(devices)
        metrics.total_memory_bytes += sum(d.get("memory_bytes", 0) for d in devices)
    
    # Network metrics
    if topology._link_metrics:
        metrics.average_bandwidth_gbps = topology.get_average_bandwidth_gbps()
        metrics.average_latency_ms = sum(
            m.latency_ms for m in topology._link_metrics.values()
        ) / len(topology._link_metrics)
        
        # Count P2P capable links
        metrics.p2p_capable_nodes = len(topology.find_p2p_capable_pairs())
        
        # Identify bottleneck links (< 100 Gbps)
        metrics.num_bottleneck_links = sum(
            1 for m in topology._link_metrics.values() if m.bandwidth_gbps < 100
        )
    
    return metrics
