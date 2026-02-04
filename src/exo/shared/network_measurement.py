"""Network Bandwidth and Latency Measurement - real-time network performance monitoring.

Measures:
- Point-to-point bandwidth between nodes
- Round-trip latency
- Packet loss
- Jitter
- Network topology discovery

Integrates with GPU topology for heterogeneous placement decisions.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, List
from statistics import mean, stdev

logger = logging.getLogger(__name__)


@dataclass
class LatencyMeasurement:
    """Latency measurement result."""

    source_node: str
    target_node: str
    rtt_ms: float
    """Round-trip time in milliseconds"""
    jitter_ms: float
    """Jitter (standard deviation of RTT)"""
    packet_loss: float
    """Packet loss percentage (0.0 to 1.0)"""
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class BandwidthMeasurement:
    """Bandwidth measurement result."""

    source_node: str
    target_node: str
    bandwidth_mbps: float
    """Measured bandwidth in Mbps"""
    transfer_size_bytes: int
    """Size of test transfer"""
    duration_seconds: float
    """Transfer duration"""
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class NetworkTopology:
    """Network topology with measured performance."""

    nodes: List[str]
    """List of node IDs"""

    latencies: Dict[tuple[str, str], LatencyMeasurement]
    """Latency measurements between node pairs"""

    bandwidths: Dict[tuple[str, str], BandwidthMeasurement]
    """Bandwidth measurements between node pairs"""

    bottleneck_link: Optional[tuple[str, str]] = None
    """Link with lowest bandwidth"""

    average_latency_ms: float = 0.0
    """Average latency across all links"""

    average_bandwidth_mbps: float = 0.0
    """Average bandwidth across all links"""


class NetworkMeasurementService:
    """Service for measuring network performance between nodes."""

    def __init__(self):
        """Initialize network measurement service."""
        self._measurements: Dict[tuple[str, str], List[LatencyMeasurement]] = {}
        self._bandwidth_cache: Dict[tuple[str, str], BandwidthMeasurement] = {}
        self._lock = asyncio.Lock()

        logger.info("Network measurement service initialized")

    async def measure_latency(
        self,
        source_node: str,
        target_node: str,
        num_probes: int = 10,
        probe_size_bytes: int = 64,
    ) -> LatencyMeasurement:
        """Measure latency between two nodes.

        Args:
            source_node: Source node ID
            target_node: Target node ID
            num_probes: Number of ping probes
            probe_size_bytes: Size of each probe

        Returns:
            LatencyMeasurement: Latency measurement result
        """
        logger.debug(
            f"Measuring latency: {source_node} -> {target_node} "
            f"({num_probes} probes)"
        )

        rtts = []
        lost_packets = 0

        for i in range(num_probes):
            try:
                # Simulate network probe (in real implementation, use actual network call)
                start = time.perf_counter()
                await self._send_probe(target_node, probe_size_bytes)
                end = time.perf_counter()

                rtt = (end - start) * 1000  # Convert to ms
                rtts.append(rtt)

            except Exception as e:
                logger.debug(f"Probe {i} failed: {e}")
                lost_packets += 1

        if not rtts:
            raise RuntimeError(f"All probes failed to {target_node}")

        # Calculate statistics
        avg_rtt = mean(rtts)
        jitter = stdev(rtts) if len(rtts) > 1 else 0.0
        packet_loss = lost_packets / num_probes

        measurement = LatencyMeasurement(
            source_node=source_node,
            target_node=target_node,
            rtt_ms=avg_rtt,
            jitter_ms=jitter,
            packet_loss=packet_loss,
        )

        # Cache measurement
        async with self._lock:
            key = (source_node, target_node)
            if key not in self._measurements:
                self._measurements[key] = []
            self._measurements[key].append(measurement)

            # Keep only recent measurements (last 100)
            if len(self._measurements[key]) > 100:
                self._measurements[key] = self._measurements[key][-100:]

        logger.info(
            f"Latency {source_node} -> {target_node}: "
            f"{avg_rtt:.2f}ms (jitter: {jitter:.2f}ms, loss: {packet_loss*100:.1f}%)"
        )

        return measurement

    async def measure_bandwidth(
        self,
        source_node: str,
        target_node: str,
        transfer_size_mb: int = 10,
    ) -> BandwidthMeasurement:
        """Measure bandwidth between two nodes.

        Args:
            source_node: Source node ID
            target_node: Target node ID
            transfer_size_mb: Size of test transfer in MB

        Returns:
            BandwidthMeasurement: Bandwidth measurement result
        """
        logger.debug(
            f"Measuring bandwidth: {source_node} -> {target_node} "
            f"({transfer_size_mb}MB)"
        )

        transfer_size_bytes = transfer_size_mb * 1024 * 1024

        try:
            # Perform bandwidth test
            start = time.perf_counter()
            await self._send_data(target_node, transfer_size_bytes)
            end = time.perf_counter()

            duration = end - start
            bandwidth_mbps = (transfer_size_bytes * 8) / (duration * 1e6)

            measurement = BandwidthMeasurement(
                source_node=source_node,
                target_node=target_node,
                bandwidth_mbps=bandwidth_mbps,
                transfer_size_bytes=transfer_size_bytes,
                duration_seconds=duration,
            )

            # Cache measurement
            async with self._lock:
                key = (source_node, target_node)
                self._bandwidth_cache[key] = measurement

            logger.info(
                f"Bandwidth {source_node} -> {target_node}: "
                f"{bandwidth_mbps:.2f} Mbps ({duration:.2f}s)"
            )

            return measurement

        except Exception as e:
            logger.error(f"Bandwidth measurement failed: {e}")
            raise RuntimeError(f"Bandwidth measurement failed: {e}") from e

    async def _send_probe(self, target_node: str, size_bytes: int) -> None:
        """Send network probe to target node.

        Args:
            target_node: Target node ID
            size_bytes: Probe size

        Note: This is a placeholder. Real implementation would use actual network calls.
        """
        # Simulate network delay (1-10ms)
        await asyncio.sleep(0.001 + (hash(target_node) % 10) / 1000)

    async def _send_data(self, target_node: str, size_bytes: int) -> None:
        """Send data to target node for bandwidth test.

        Args:
            target_node: Target node ID
            size_bytes: Data size

        Note: This is a placeholder. Real implementation would use actual network calls.
        """
        # Simulate transfer at ~1 Gbps
        simulated_bandwidth_bps = 1e9
        duration = size_bytes * 8 / simulated_bandwidth_bps
        await asyncio.sleep(duration)

    async def measure_full_topology(
        self,
        nodes: List[str],
        source_node: str,
    ) -> NetworkTopology:
        """Measure full network topology from source node to all other nodes.

        Args:
            nodes: List of all node IDs
            source_node: Source node for measurements

        Returns:
            NetworkTopology: Complete topology with measurements
        """
        logger.info(
            f"Measuring full topology from {source_node} to {len(nodes)-1} nodes"
        )

        latencies = {}
        bandwidths = {}

        for target_node in nodes:
            if target_node == source_node:
                continue

            try:
                # Measure latency
                latency = await self.measure_latency(source_node, target_node)
                latencies[(source_node, target_node)] = latency

                # Measure bandwidth
                bandwidth = await self.measure_bandwidth(source_node, target_node)
                bandwidths[(source_node, target_node)] = bandwidth

            except Exception as e:
                logger.warning(f"Failed to measure {source_node} -> {target_node}: {e}")

        # Calculate topology metrics
        if latencies:
            avg_latency = mean(m.rtt_ms for m in latencies.values())
        else:
            avg_latency = 0.0

        if bandwidths:
            avg_bandwidth = mean(m.bandwidth_mbps for m in bandwidths.values())
            bottleneck = min(bandwidths.items(), key=lambda x: x[1].bandwidth_mbps)
            bottleneck_link = bottleneck[0]
        else:
            avg_bandwidth = 0.0
            bottleneck_link = None

        topology = NetworkTopology(
            nodes=nodes,
            latencies=latencies,
            bandwidths=bandwidths,
            bottleneck_link=bottleneck_link,
            average_latency_ms=avg_latency,
            average_bandwidth_mbps=avg_bandwidth,
        )

        logger.info(
            f"Topology measured: avg latency={avg_latency:.2f}ms, "
            f"avg bandwidth={avg_bandwidth:.2f}Mbps"
        )

        return topology

    async def get_cached_latency(
        self,
        source_node: str,
        target_node: str,
    ) -> Optional[LatencyMeasurement]:
        """Get most recent cached latency measurement.

        Args:
            source_node: Source node ID
            target_node: Target node ID

        Returns:
            LatencyMeasurement or None if not cached
        """
        async with self._lock:
            key = (source_node, target_node)
            measurements = self._measurements.get(key, [])

            if measurements:
                return measurements[-1]

            return None

    async def get_cached_bandwidth(
        self,
        source_node: str,
        target_node: str,
    ) -> Optional[BandwidthMeasurement]:
        """Get cached bandwidth measurement.

        Args:
            source_node: Source node ID
            target_node: Target node ID

        Returns:
            BandwidthMeasurement or None if not cached
        """
        async with self._lock:
            key = (source_node, target_node)
            return self._bandwidth_cache.get(key)

    async def estimate_transfer_time(
        self,
        source_node: str,
        target_node: str,
        size_bytes: int,
    ) -> float:
        """Estimate transfer time between nodes.

        Args:
            source_node: Source node ID
            target_node: Target node ID
            size_bytes: Transfer size

        Returns:
            float: Estimated transfer time in seconds
        """
        # Get cached measurements
        latency = await self.get_cached_latency(source_node, target_node)
        bandwidth = await self.get_cached_bandwidth(source_node, target_node)

        if latency is None or bandwidth is None:
            # No cached data, measure now
            latency = await self.measure_latency(source_node, target_node)
            bandwidth = await self.measure_bandwidth(source_node, target_node)

        # Estimate: latency + (size / bandwidth)
        latency_s = latency.rtt_ms / 1000
        bandwidth_bps = bandwidth.bandwidth_mbps * 1e6
        transfer_time = latency_s + (size_bytes * 8 / bandwidth_bps)

        return transfer_time

    async def clear_cache(self) -> None:
        """Clear all cached measurements."""
        async with self._lock:
            self._measurements.clear()
            self._bandwidth_cache.clear()
            logger.info("Cleared network measurement cache")


# ===== Helper Functions =====


async def measure_cluster_network(
    nodes: List[str],
    source_node: str,
) -> NetworkTopology:
    """Convenience function to measure cluster network topology.

    Args:
        nodes: List of node IDs
        source_node: Source node for measurements

    Returns:
        NetworkTopology: Measured topology
    """
    service = NetworkMeasurementService()
    return await service.measure_full_topology(nodes, source_node)


def format_topology_summary(topology: NetworkTopology) -> str:
    """Format topology summary for logging.

    Args:
        topology: Network topology

    Returns:
        str: Formatted summary
    """
    lines = [
        "Network Topology Summary",
        "=" * 60,
        f"Nodes: {len(topology.nodes)}",
        f"Average Latency: {topology.average_latency_ms:.2f}ms",
        f"Average Bandwidth: {topology.average_bandwidth_mbps:.2f}Mbps",
    ]

    if topology.bottleneck_link:
        src, dst = topology.bottleneck_link
        bw = topology.bandwidths[topology.bottleneck_link]
        lines.append(
            f"Bottleneck Link: {src} -> {dst} ({bw.bandwidth_mbps:.2f}Mbps)"
        )

    return "\n".join(lines)
