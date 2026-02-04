"""Cross-platform GPU telemetry aggregation and device scoring.

Aggregates GPU metrics from all devices in the cluster for heterogeneous
placement decisions by the CSP solver.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from exo.gpu.backend import GPUDevice

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GPUDeviceScore:
    """Score for a device relative to model requirements."""

    device_id: str
    name: str
    
    # Component scores (0-1 range, higher is better)
    compute_score: float
    memory_score: float
    bandwidth_score: float
    network_score: float
    thermal_score: float
    
    # Weighted composite score
    total_score: float
    
    # Diagnostic info
    compute_capability: str
    memory_bytes: int
    available_memory_bytes: int
    bandwidth_gbps: float


@dataclass(frozen=True)
class ClusterGPUMetrics:
    """Aggregated GPU metrics across entire cluster."""

    total_devices: int
    total_memory_bytes: int
    total_available_memory: int
    
    # Aggregated performance metrics
    average_bandwidth_gbps: float
    bottleneck_bandwidth_gbps: float  # Slowest link
    total_compute_units: int
    
    # Heterogeneity metrics
    heterogeneous_ratio: float  # max_perf / min_perf (higher = more diverse)
    device_count_by_vendor: Dict[str, int]
    
    # Device listing
    devices: List[GPUDevice]


class GPUTelemetryAggregator:
    """Aggregates GPU telemetry across cluster."""

    @staticmethod
    def aggregate_cluster_metrics(
        devices_by_node: Dict[str, List[GPUDevice]],
    ) -> ClusterGPUMetrics:
        """Aggregate GPU metrics across all nodes in cluster.
        
        Args:
            devices_by_node: Dict mapping node_id to list of GPUDevices on that node
            
        Returns:
            ClusterGPUMetrics with aggregated information
        """
        all_devices: List[GPUDevice] = []
        total_memory = 0
        total_available = 0
        total_compute_units = 0
        vendor_counts: Dict[str, int] = {}
        bandwidths: List[float] = []
        
        # Flatten and aggregate device metrics
        for node_id, devices in devices_by_node.items():
            for device in devices:
                all_devices.append(device)
                total_memory += device.memory_bytes
                total_available += device.memory_available
                total_compute_units += device.compute_units
                bandwidths.append(device.bandwidth_gbps)
                
                # Count vendors
                vendor = device.vendor
                vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
                
                logger.debug(
                    f"Device {device.device_id}: {device.compute_units} CUs, "
                    f"{device.memory_bytes / 1024**3:.1f}GB, {device.bandwidth_gbps:.0f}GB/s"
                )
        
        # Compute aggregate metrics
        total_devices = len(all_devices)
        
        if not bandwidths:
            avg_bandwidth = 0.0
            bottleneck = 0.0
        else:
            avg_bandwidth = sum(bandwidths) / len(bandwidths)
            bottleneck = min(bandwidths)  # Slowest link is the bottleneck
        
        # Heterogeneity: compute ratio of max to min performance
        if all_devices:
            compute_scores = [
                d.compute_units * d.bandwidth_gbps * d.clock_rate_mhz / 1000.0
                for d in all_devices
            ]
            max_compute = max(compute_scores)
            min_compute = min(compute_scores)
            heterogeneous_ratio = max_compute / min_compute if min_compute > 0 else 1.0
        else:
            heterogeneous_ratio = 1.0
        
        return ClusterGPUMetrics(
            total_devices=total_devices,
            total_memory_bytes=total_memory,
            total_available_memory=total_available,
            average_bandwidth_gbps=avg_bandwidth,
            bottleneck_bandwidth_gbps=bottleneck,
            total_compute_units=total_compute_units,
            heterogeneous_ratio=heterogeneous_ratio,
            device_count_by_vendor=vendor_counts,
            devices=all_devices,
        )

    @staticmethod
    def compute_device_scores(
        devices: List[GPUDevice],
        model_config: Dict,
    ) -> Dict[str, GPUDeviceScore]:
        """Score devices for placement of specific model shard.
        
        Args:
            devices: List of available GPUDevices
            model_config: Model configuration with keys:
                - estimated_memory_bytes: Memory needed for this shard
                - tensor_operations: Approximate FLOPs needed
                
        Returns:
            Dict mapping device_id -> GPUDeviceScore
        """
        scores = {}
        
        estimated_memory = model_config.get("estimated_memory_bytes", 1024 * 1024)
        tensor_ops = model_config.get("tensor_operations", 1e9)  # 1B FLOPs default
        
        # Get reference device for normalization
        reference_compute = max(
            (d.compute_units * d.bandwidth_gbps * d.clock_rate_mhz / 1000.0
             for d in devices),
            default=1.0
        )
        
        for device in devices:
            # Compute capability scoring
            # Based on: compute units * memory bandwidth * clock rate
            device_compute = (
                device.compute_units * 
                device.bandwidth_gbps * 
                device.clock_rate_mhz / 1000.0
            )
            compute_score = min(1.0, device_compute / reference_compute) if reference_compute > 0 else 0.5
            
            # Memory fit scoring
            # Penalize if insufficient memory
            if device.memory_available >= estimated_memory:
                memory_score = min(
                    1.0,
                    device.memory_available / (estimated_memory * 2)  # Bonus for extra memory
                )
            else:
                # Insufficient memory: penalize heavily
                memory_score = 0.3 * (device.memory_available / estimated_memory)
            
            # Bandwidth scoring (relative to average)
            avg_bandwidth = sum(d.bandwidth_gbps for d in devices) / len(devices) if devices else 1.0
            bandwidth_score = min(1.0, device.bandwidth_gbps / avg_bandwidth) if avg_bandwidth > 0 else 0.5
            
            # Network position scoring (placeholder - would be updated by topology-aware placement)
            network_score = 0.8  # Default: not penalized until topology info available
            
            # Thermal scoring (for mobile devices)
            # Assume 1.0 for now, mobile devices would reduce this
            thermal_score = 0.9  # Conservative default (slight headroom)
            
            # Weighted composite score
            total_score = (
                compute_score * 0.40 +    # 40% compute capability
                memory_score * 0.30 +     # 30% memory fit
                bandwidth_score * 0.15 +  # 15% bandwidth
                network_score * 0.10 +    # 10% network position
                thermal_score * 0.05      # 5% thermal headroom
            )
            
            scores[device.device_id] = GPUDeviceScore(
                device_id=device.device_id,
                name=device.name,
                compute_score=compute_score,
                memory_score=memory_score,
                bandwidth_score=bandwidth_score,
                network_score=network_score,
                thermal_score=thermal_score,
                total_score=total_score,
                compute_capability=device.compute_capability,
                memory_bytes=device.memory_bytes,
                available_memory_bytes=device.memory_available,
                bandwidth_gbps=device.bandwidth_gbps,
            )
            
            logger.debug(
                f"Device {device.device_id} score: {total_score:.3f} "
                f"(compute={compute_score:.2f}, memory={memory_score:.2f}, "
                f"bandwidth={bandwidth_score:.2f})"
            )
        
        return scores

    @staticmethod
    def get_optimal_devices(
        devices: List[GPUDevice],
        model_config: Dict,
        count: int = 1,
    ) -> List[GPUDevice]:
        """Get top N devices for placing a model shard.
        
        Args:
            devices: Available GPU devices
            model_config: Model configuration
            count: Number of devices to return
            
        Returns:
            List of top devices for placement
        """
        scores = GPUTelemetryAggregator.compute_device_scores(devices, model_config)
        
        # Sort by score (descending)
        sorted_devices = sorted(
            scores.items(),
            key=lambda x: x[1].total_score,
            reverse=True
        )
        
        # Return top N device IDs
        device_map = {d.device_id: d for d in devices}
        result = []
        
        for device_id, score in sorted_devices[:count]:
            if device_id in device_map:
                result.append(device_map[device_id])
        
        return result

    @staticmethod
    def estimate_transfer_time(
        src_device: GPUDevice,
        dst_device: GPUDevice,
        size_bytes: int,
        cluster_metrics: Optional[ClusterGPUMetrics] = None,
    ) -> float:
        """Estimate time to transfer data between devices.
        
        Args:
            src_device: Source GPU device
            dst_device: Destination GPU device
            size_bytes: Number of bytes to transfer
            cluster_metrics: Optional cluster metrics for link info
            
        Returns:
            Estimated transfer time in seconds
        """
        # Placeholder: assumes network bandwidth = device bandwidth
        # In reality, would use actual network topology metrics
        
        if src_device.device_id == dst_device.device_id:
            # Same device, no transfer needed
            return 0.0
        
        # Assume P2P if same vendor, network otherwise
        if src_device.vendor == dst_device.vendor:
            # P2P transfer - use faster of the two devices
            bandwidth = min(src_device.bandwidth_gbps, dst_device.bandwidth_gbps)
        else:
            # Cross-vendor transfer - use network bandwidth if available
            if cluster_metrics:
                bandwidth = cluster_metrics.bottleneck_bandwidth_gbps
            else:
                # Conservative estimate: assume 10GB/s network
                bandwidth = 10.0
        
        # Add latency estimate (microseconds converted to seconds)
        latency = 1e-5  # 10 microseconds
        
        # Calculate transfer time
        transfer_time = (size_bytes / (1024**3)) / bandwidth if bandwidth > 0 else float('inf')
        
        return latency + transfer_time

    @staticmethod
    def format_cluster_summary(metrics: ClusterGPUMetrics) -> str:
        """Format cluster metrics as human-readable summary.
        
        Args:
            metrics: ClusterGPUMetrics to format
            
        Returns:
            Formatted string summary
        """
        lines = [
            "=== GPU Cluster Metrics ===",
            f"Total Devices: {metrics.total_devices}",
            f"Total Memory: {metrics.total_memory_bytes / 1024**3:.1f} GB",
            f"Available Memory: {metrics.total_available_memory / 1024**3:.1f} GB",
            f"Total Compute Units: {metrics.total_compute_units}",
            f"Average Bandwidth: {metrics.average_bandwidth_gbps:.1f} GB/s",
            f"Bottleneck Bandwidth: {metrics.bottleneck_bandwidth_gbps:.1f} GB/s",
            f"Heterogeneity Ratio: {metrics.heterogeneous_ratio:.2f}x",
            f"Vendors: {', '.join(f'{v}({c})' for v, c in metrics.device_count_by_vendor.items())}",
        ]
        
        return "\n".join(lines)


# Singleton aggregator for easy access
_aggregator = GPUTelemetryAggregator()


def get_aggregator() -> GPUTelemetryAggregator:
    """Get the global GPU telemetry aggregator."""
    return _aggregator
