"""GPU performance benchmarking suite.

Measures and reports GPU performance across different backends and operations.
Run with: python benchmarks/gpu_benchmark.py
"""

import asyncio
import time
import logging
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from pathlib import Path

from exo.gpu.factory import GPUBackendFactory
from exo.gpu.backend import GPUDevice
from exo.shared.gpu_telemetry_aggregator import GPUTelemetryAggregator

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark."""

    device_name: str
    device_id: str
    backend: str
    operation: str
    data_size_mb: float
    iterations: int
    total_time_ms: float
    average_time_ms: float
    throughput_gbps: float
    
    @property
    def throughput_mbs(self) -> float:
        """Throughput in MB/s."""
        return self.data_size_mb / (self.average_time_ms / 1000.0)


class GPUBenchmark:
    """GPU performance benchmarking."""

    def __init__(self, results_dir: str = "benchmarks/results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.results: List[BenchmarkResult] = []

    async def benchmark_memory_copy(
        self,
        backend,
        device: GPUDevice,
        size_mb: int,
        iterations: int = 3,
    ) -> Optional[BenchmarkResult]:
        """Benchmark host-to-device memory copy."""
        try:
            size_bytes = size_mb * 1024 * 1024
            
            # Allocate device memory
            handle = await backend.allocate(device.device_id, size_bytes)
            
            # Create test data
            test_data = b'x' * size_bytes
            
            # Warm up
            await backend.copy_to_device(test_data, handle)
            await backend.synchronize(device.device_id)
            
            # Benchmark
            times = []
            for _ in range(iterations):
                start = time.perf_counter()
                await backend.copy_to_device(test_data, handle)
                await backend.synchronize(device.device_id)
                elapsed = (time.perf_counter() - start) * 1000  # ms
                times.append(elapsed)
            
            await backend.deallocate(handle)
            
            avg_time_ms = sum(times) / len(times)
            throughput_gbps = (size_mb / 1024) / (avg_time_ms / 1000)
            
            result = BenchmarkResult(
                device_name=device.name,
                device_id=device.device_id,
                backend=device.backend,
                operation="copy_to_device",
                data_size_mb=size_mb,
                iterations=iterations,
                total_time_ms=sum(times),
                average_time_ms=avg_time_ms,
                throughput_gbps=throughput_gbps,
            )
            
            logger.info(
                f"  {device.name} ({size_mb}MB): {avg_time_ms:.2f}ms "
                f"({throughput_gbps:.1f} GB/s)"
            )
            
            self.results.append(result)
            return result
            
        except Exception as e:
            logger.warning(f"  Failed to benchmark {device.name}: {e}")
            return None

    async def benchmark_memory_copy_device_to_device(
        self,
        backend,
        src_device: GPUDevice,
        dst_device: GPUDevice,
        size_mb: int,
        iterations: int = 3,
    ) -> Optional[BenchmarkResult]:
        """Benchmark device-to-device memory copy (P2P)."""
        try:
            size_bytes = size_mb * 1024 * 1024
            
            # Allocate on both devices
            src_handle = await backend.allocate(src_device.device_id, size_bytes)
            dst_handle = await backend.allocate(dst_device.device_id, size_bytes)
            
            # Write test data to source
            test_data = b'x' * size_bytes
            await backend.copy_to_device(test_data, src_handle)
            
            # Warm up
            await backend.copy_device_to_device(src_handle, dst_handle, size_bytes)
            await backend.synchronize(dst_device.device_id)
            
            # Benchmark
            times = []
            for _ in range(iterations):
                start = time.perf_counter()
                await backend.copy_device_to_device(src_handle, dst_handle, size_bytes)
                await backend.synchronize(dst_device.device_id)
                elapsed = (time.perf_counter() - start) * 1000  # ms
                times.append(elapsed)
            
            await backend.deallocate(src_handle)
            await backend.deallocate(dst_handle)
            
            avg_time_ms = sum(times) / len(times)
            throughput_gbps = (size_mb / 1024) / (avg_time_ms / 1000)
            
            result = BenchmarkResult(
                device_name=f"{src_device.name} → {dst_device.name}",
                device_id=f"{src_device.device_id}→{dst_device.device_id}",
                backend="p2p",
                operation="copy_device_to_device",
                data_size_mb=size_mb,
                iterations=iterations,
                total_time_ms=sum(times),
                average_time_ms=avg_time_ms,
                throughput_gbps=throughput_gbps,
            )
            
            logger.info(
                f"  {src_device.name} → {dst_device.name} ({size_mb}MB): "
                f"{avg_time_ms:.2f}ms ({throughput_gbps:.1f} GB/s)"
            )
            
            self.results.append(result)
            return result
            
        except Exception as e:
            logger.warning(
                f"  Failed to benchmark P2P {src_device.name} → {dst_device.name}: {e}"
            )
            return None

    async def run_all_benchmarks(self):
        """Run all GPU benchmarks."""
        logger.info("Starting GPU Benchmarks...")
        
        try:
            backend = await GPUBackendFactory.create_backend()
        except RuntimeError as e:
            logger.error(f"Failed to create GPU backend: {e}")
            return
        
        devices = backend.list_devices()
        
        if not devices:
            logger.error("No GPU devices found")
            await backend.shutdown()
            return
        
        logger.info(f"Found {len(devices)} GPU devices")
        
        # Benchmark each device
        for device in devices:
            logger.info(f"\nBenchmarking {device.name}...")
            
            # Memory bandwidth test
            logger.info("  Memory bandwidth (host↔device):")
            for size_mb in [10, 100, 256]:
                await self.benchmark_memory_copy(backend, device, size_mb)
        
        # Multi-GPU P2P benchmarks
        if len(devices) >= 2:
            logger.info("\nBenchmarking P2P transfers...")
            for i in range(len(devices)):
                for j in range(i + 1, len(devices)):
                    src, dst = devices[i], devices[j]
                    logger.info(f"  {src.name} ↔ {dst.name}:")
                    for size_mb in [10, 100, 256]:
                        await self.benchmark_memory_copy_device_to_device(
                            backend, src, dst, size_mb
                        )
        
        # Cleanup
        await backend.shutdown()
        
        logger.info("\nBenchmarks complete!")

    def print_summary(self):
        """Print benchmark summary."""
        if not self.results:
            logger.warning("No benchmark results to summarize")
            return
        
        logger.info("\n" + "="*80)
        logger.info("GPU Benchmark Summary")
        logger.info("="*80)
        
        # Group by device
        by_device = {}
        for result in self.results:
            if result.device_id not in by_device:
                by_device[result.device_id] = []
            by_device[result.device_id].append(result)
        
        for device_id, results in by_device.items():
            logger.info(f"\n{results[0].device_name}:")
            
            # Group by operation
            by_op = {}
            for result in results:
                if result.operation not in by_op:
                    by_op[result.operation] = []
                by_op[result.operation].append(result)
            
            for op_name, op_results in by_op.items():
                logger.info(f"  {op_name}:")
                for result in op_results:
                    logger.info(
                        f"    {result.data_size_mb:>3.0f}MB: "
                        f"{result.average_time_ms:>7.2f}ms "
                        f"({result.throughput_gbps:>6.1f} GB/s)"
                    )

    def save_results(self, filename: str = "gpu_benchmark_results.json"):
        """Save benchmark results to JSON."""
        filepath = self.results_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(
                [asdict(r) for r in self.results],
                f,
                indent=2
            )
        
        logger.info(f"Results saved to {filepath}")

    def generate_report(self, filename: str = "gpu_benchmark_report.txt"):
        """Generate a text report of benchmark results."""
        filepath = self.results_dir / filename
        
        with open(filepath, 'w') as f:
            f.write("GPU Benchmark Report\n")
            f.write("=" * 80 + "\n\n")
            
            # Summary stats
            if self.results:
                f.write("Summary Statistics\n")
                f.write("-" * 80 + "\n")
                
                avg_throughput = sum(r.throughput_gbps for r in self.results) / len(self.results)
                max_throughput = max(r.throughput_gbps for r in self.results)
                min_throughput = min(r.throughput_gbps for r in self.results)
                
                f.write(f"Total benchmarks: {len(self.results)}\n")
                f.write(f"Average throughput: {avg_throughput:.1f} GB/s\n")
                f.write(f"Max throughput: {max_throughput:.1f} GB/s\n")
                f.write(f"Min throughput: {min_throughput:.1f} GB/s\n\n")
            
            # Detailed results
            f.write("Detailed Results\n")
            f.write("-" * 80 + "\n")
            f.write("Device | Operation | Size | Time | Throughput\n")
            f.write("-" * 80 + "\n")
            
            for result in self.results:
                f.write(
                    f"{result.device_name:<30} | "
                    f"{result.operation:<20} | "
                    f"{result.data_size_mb:>4.0f}MB | "
                    f"{result.average_time_ms:>7.2f}ms | "
                    f"{result.throughput_gbps:>7.1f} GB/s\n"
                )
        
        logger.info(f"Report saved to {filepath}")


async def main():
    """Run GPU benchmarking suite."""
    benchmark = GPUBenchmark()
    await benchmark.run_all_benchmarks()
    benchmark.print_summary()
    benchmark.save_results()
    benchmark.generate_report()


if __name__ == "__main__":
    asyncio.run(main())
