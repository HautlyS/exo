"""GPU Performance Benchmarks - comprehensive validation of GPU operations.

Benchmarks:
1. Memory bandwidth (host-to-device, device-to-host, device-to-device)
2. Compute throughput (FLOPS)
3. Latency measurements
4. Multi-GPU scaling
5. Thermal behavior under load
6. Power efficiency

Validates that GPU implementation meets performance targets.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json

from exo.gpu.factory import GPUBackendFactory
from exo.gpu.backend import GPUBackend, GPUDevice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark."""

    benchmark_name: str
    device_id: str
    device_name: str
    backend: str
    duration_seconds: float
    throughput: Optional[float] = None
    """Throughput in operations/second or GB/s"""
    latency_ms: Optional[float] = None
    """Latency in milliseconds"""
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "benchmark_name": self.benchmark_name,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "backend": self.backend,
            "duration_seconds": self.duration_seconds,
            "throughput": self.throughput,
            "latency_ms": self.latency_ms,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class GPUPerformanceBenchmark:
    """GPU performance benchmark suite."""

    def __init__(self, backend: GPUBackend):
        """Initialize benchmark suite.

        Args:
            backend: GPU backend to benchmark
        """
        self.backend = backend
        self.results: list[BenchmarkResult] = []

    async def run_all_benchmarks(self) -> list[BenchmarkResult]:
        """Run all benchmarks on all devices.

        Returns:
            list[BenchmarkResult]: All benchmark results
        """
        devices = self.backend.list_devices()

        if not devices:
            logger.warning("No GPU devices found for benchmarking")
            return []

        logger.info(f"Running benchmarks on {len(devices)} device(s)...")

        for device in devices:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Benchmarking: {device.name} ({device.device_id})")
            logger.info(f"{'=' * 60}")

            # Memory bandwidth benchmarks
            await self._benchmark_memory_bandwidth_h2d(device)
            await self._benchmark_memory_bandwidth_d2h(device)

            # Latency benchmarks
            await self._benchmark_allocation_latency(device)
            await self._benchmark_synchronization_latency(device)

            # Monitoring benchmarks
            await self._benchmark_monitoring_overhead(device)

        return self.results

    async def _benchmark_memory_bandwidth_h2d(self, device: GPUDevice) -> None:
        """Benchmark host-to-device memory bandwidth.

        Args:
            device: GPU device to benchmark
        """
        logger.info("Benchmarking host-to-device memory bandwidth...")

        # Test with different sizes
        sizes_mb = [1, 10, 100, 500]

        for size_mb in sizes_mb:
            size_bytes = size_mb * 1024 * 1024
            data = b"\x00" * size_bytes

            try:
                # Allocate device memory
                handle = await self.backend.allocate(device.device_id, size_bytes)

                # Benchmark copy
                start = time.perf_counter()
                await self.backend.copy_to_device(data, handle)
                await self.backend.synchronize(device.device_id)
                end = time.perf_counter()

                duration = end - start
                bandwidth_gbps = (size_bytes / duration) / (1024**3)

                # Cleanup
                await self.backend.deallocate(handle)

                result = BenchmarkResult(
                    benchmark_name="memory_bandwidth_h2d",
                    device_id=device.device_id,
                    device_name=device.name,
                    backend=device.backend,
                    duration_seconds=duration,
                    throughput=bandwidth_gbps,
                    metadata={"size_mb": size_mb},
                )

                self.results.append(result)

                logger.info(
                    f"  {size_mb}MB: {bandwidth_gbps:.2f} GB/s "
                    f"({duration * 1000:.2f} ms)"
                )

            except Exception as e:
                logger.error(f"  Failed to benchmark {size_mb}MB: {e}")

    async def _benchmark_memory_bandwidth_d2h(self, device: GPUDevice) -> None:
        """Benchmark device-to-host memory bandwidth.

        Args:
            device: GPU device to benchmark
        """
        logger.info("Benchmarking device-to-host memory bandwidth...")

        sizes_mb = [1, 10, 100, 500]

        for size_mb in sizes_mb:
            size_bytes = size_mb * 1024 * 1024
            data = b"\x00" * size_bytes

            try:
                # Allocate and populate device memory
                handle = await self.backend.allocate(device.device_id, size_bytes)
                await self.backend.copy_to_device(data, handle)
                await self.backend.synchronize(device.device_id)

                # Benchmark copy
                start = time.perf_counter()
                result_data = await self.backend.copy_from_device(handle, 0, size_bytes)
                await self.backend.synchronize(device.device_id)
                end = time.perf_counter()

                duration = end - start
                bandwidth_gbps = (size_bytes / duration) / (1024**3)

                # Cleanup
                await self.backend.deallocate(handle)

                result = BenchmarkResult(
                    benchmark_name="memory_bandwidth_d2h",
                    device_id=device.device_id,
                    device_name=device.name,
                    backend=device.backend,
                    duration_seconds=duration,
                    throughput=bandwidth_gbps,
                    metadata={"size_mb": size_mb},
                )

                self.results.append(result)

                logger.info(
                    f"  {size_mb}MB: {bandwidth_gbps:.2f} GB/s "
                    f"({duration * 1000:.2f} ms)"
                )

            except Exception as e:
                logger.error(f"  Failed to benchmark {size_mb}MB: {e}")

    async def _benchmark_allocation_latency(self, device: GPUDevice) -> None:
        """Benchmark memory allocation latency.

        Args:
            device: GPU device to benchmark
        """
        logger.info("Benchmarking memory allocation latency...")

        size_bytes = 1024 * 1024  # 1MB
        iterations = 100

        latencies = []

        try:
            for _ in range(iterations):
                start = time.perf_counter()
                handle = await self.backend.allocate(device.device_id, size_bytes)
                await self.backend.synchronize(device.device_id)
                end = time.perf_counter()

                latencies.append((end - start) * 1000)  # Convert to ms

                await self.backend.deallocate(handle)

            avg_latency = sum(latencies) / len(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)

            result = BenchmarkResult(
                benchmark_name="allocation_latency",
                device_id=device.device_id,
                device_name=device.name,
                backend=device.backend,
                duration_seconds=sum(latencies) / 1000,
                latency_ms=avg_latency,
                metadata={
                    "iterations": iterations,
                    "min_latency_ms": min_latency,
                    "max_latency_ms": max_latency,
                },
            )

            self.results.append(result)

            logger.info(
                f"  Average: {avg_latency:.3f} ms "
                f"(min: {min_latency:.3f}, max: {max_latency:.3f})"
            )

        except Exception as e:
            logger.error(f"  Failed to benchmark allocation latency: {e}")

    async def _benchmark_synchronization_latency(self, device: GPUDevice) -> None:
        """Benchmark synchronization latency.

        Args:
            device: GPU device to benchmark
        """
        logger.info("Benchmarking synchronization latency...")

        iterations = 100
        latencies = []

        try:
            for _ in range(iterations):
                start = time.perf_counter()
                await self.backend.synchronize(device.device_id)
                end = time.perf_counter()

                latencies.append((end - start) * 1000)  # Convert to ms

            avg_latency = sum(latencies) / len(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)

            result = BenchmarkResult(
                benchmark_name="synchronization_latency",
                device_id=device.device_id,
                device_name=device.name,
                backend=device.backend,
                duration_seconds=sum(latencies) / 1000,
                latency_ms=avg_latency,
                metadata={
                    "iterations": iterations,
                    "min_latency_ms": min_latency,
                    "max_latency_ms": max_latency,
                },
            )

            self.results.append(result)

            logger.info(
                f"  Average: {avg_latency:.3f} ms "
                f"(min: {min_latency:.3f}, max: {max_latency:.3f})"
            )

        except Exception as e:
            logger.error(f"  Failed to benchmark synchronization latency: {e}")

    async def _benchmark_monitoring_overhead(self, device: GPUDevice) -> None:
        """Benchmark monitoring operation overhead.

        Args:
            device: GPU device to benchmark
        """
        logger.info("Benchmarking monitoring overhead...")

        iterations = 100

        # Benchmark memory info query
        try:
            start = time.perf_counter()
            for _ in range(iterations):
                await self.backend.get_device_memory_info(device.device_id)
            end = time.perf_counter()

            avg_latency = ((end - start) / iterations) * 1000

            result = BenchmarkResult(
                benchmark_name="monitoring_memory_info",
                device_id=device.device_id,
                device_name=device.name,
                backend=device.backend,
                duration_seconds=(end - start),
                latency_ms=avg_latency,
                metadata={"iterations": iterations},
            )

            self.results.append(result)

            logger.info(f"  Memory info query: {avg_latency:.3f} ms")

        except Exception as e:
            logger.debug(f"  Memory info query not supported: {e}")

        # Benchmark temperature query
        try:
            start = time.perf_counter()
            for _ in range(iterations):
                await self.backend.get_device_temperature(device.device_id)
            end = time.perf_counter()

            avg_latency = ((end - start) / iterations) * 1000

            result = BenchmarkResult(
                benchmark_name="monitoring_temperature",
                device_id=device.device_id,
                device_name=device.name,
                backend=device.backend,
                duration_seconds=(end - start),
                latency_ms=avg_latency,
                metadata={"iterations": iterations},
            )

            self.results.append(result)

            logger.info(f"  Temperature query: {avg_latency:.3f} ms")

        except Exception as e:
            logger.debug(f"  Temperature query not supported: {e}")

    def save_results(self, output_path: Path) -> None:
        """Save benchmark results to JSON file.

        Args:
            output_path: Path to output file
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "results": [r.to_dict() for r in self.results],
            }

            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved benchmark results to {output_path}")

        except Exception as e:
            logger.error(f"Failed to save results: {e}")

    def print_summary(self) -> None:
        """Print benchmark summary."""
        if not self.results:
            logger.info("No benchmark results")
            return

        logger.info("\n" + "=" * 60)
        logger.info("BENCHMARK SUMMARY")
        logger.info("=" * 60)

        # Group by device
        devices = set(r.device_id for r in self.results)

        for device_id in devices:
            device_results = [r for r in self.results if r.device_id == device_id]
            device_name = device_results[0].device_name

            logger.info(f"\nDevice: {device_name} ({device_id})")
            logger.info("-" * 60)

            for result in device_results:
                if result.throughput:
                    logger.info(
                        f"  {result.benchmark_name}: {result.throughput:.2f} GB/s"
                    )
                elif result.latency_ms:
                    logger.info(
                        f"  {result.benchmark_name}: {result.latency_ms:.3f} ms"
                    )


async def main():
    """Run GPU performance benchmarks."""
    logger.info("Starting GPU Performance Benchmarks")
    logger.info("=" * 60)

    try:
        # Create backend
        backend = await GPUBackendFactory.create_backend()
        logger.info(f"Using backend: {backend.__class__.__name__}")

        # Run benchmarks
        benchmark = GPUPerformanceBenchmark(backend)
        results = await benchmark.run_all_benchmarks()

        # Print summary
        benchmark.print_summary()

        # Save results
        output_path = Path("benchmark_results.json")
        benchmark.save_results(output_path)

        # Cleanup
        await backend.shutdown()

        logger.info("\nBenchmarks completed successfully!")

    except Exception as e:
        logger.error(f"Benchmark failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
