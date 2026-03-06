"""
API Performance Testing Module.

Measures latency percentiles, error rates, availability, and throughput
following Google SRE SLI/SLO standards.
"""

import asyncio
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from .config import get_config, get_model_endpoint
from .invoker import ModelInvoker, InvokeResult


class ErrorType(Enum):
    """Classification of API errors."""
    NONE = "none"
    HTTP_4XX = "http_4xx"
    HTTP_5XX = "http_5xx"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    UNKNOWN = "unknown"


@dataclass
class LatencyStats:
    """Latency statistics with percentiles."""
    count: int = 0
    min_ms: float = 0
    max_ms: float = 0
    mean_ms: float = 0
    median_ms: float = 0
    p50_ms: float = 0
    p90_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0
    std_dev_ms: float = 0
    samples: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "mean_ms": round(self.mean_ms, 2),
            "median_ms": round(self.median_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p90_ms": round(self.p90_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "std_dev_ms": round(self.std_dev_ms, 2),
        }


@dataclass
class ErrorStats:
    """Error rate statistics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    error_rate: float = 0.0
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "error_rate_percent": round(self.error_rate * 100, 4),
            "errors_by_type": self.errors_by_type,
        }


@dataclass 
class SLOResult:
    """SLO validation result."""
    name: str
    target: float
    actual: float
    passed: bool
    unit: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "actual": round(self.actual, 2),
            "passed": self.passed,
            "unit": self.unit,
        }


@dataclass
class PerfTestResult:
    """Complete performance test result."""
    model: str
    endpoint: str
    timestamp: str
    latency: LatencyStats
    errors: ErrorStats
    slo_results: List[SLOResult]
    duration_seconds: float
    requests_per_second: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "endpoint": self.endpoint,
            "timestamp": self.timestamp,
            "latency": self.latency.to_dict(),
            "errors": self.errors.to_dict(),
            "slo_results": [s.to_dict() for s in self.slo_results],
            "duration_seconds": round(self.duration_seconds, 2),
            "requests_per_second": round(self.requests_per_second, 4),
        }
    
    def passed_all_slos(self) -> bool:
        return all(slo.passed for slo in self.slo_results)


@dataclass
class ConcurrentStats:
    """Concurrent/throughput test statistics."""
    concurrent_requests: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    throughput_rps: float = 0.0  # Requests per second
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "concurrent_requests": self.concurrent_requests,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "throughput_rps": round(self.throughput_rps, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_ms, 2),
            "duration_seconds": round(self.duration_seconds, 2),
        }


@dataclass
class StabilityStats:
    """Stability test statistics - long-running performance trends."""
    total_requests: int = 0
    test_duration_seconds: float = 0.0
    latency_trend: List[float] = field(default_factory=list)  # Latencies over time
    error_count_trend: List[int] = field(default_factory=list)  # Errors per window
    avg_latency_first_half_ms: float = 0.0
    avg_latency_second_half_ms: float = 0.0
    latency_degradation_percent: float = 0.0  # Positive = got slower
    stability_score: float = 100.0  # 100 = perfectly stable
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "test_duration_seconds": round(self.test_duration_seconds, 2),
            "latency_trend_ms": [round(l, 2) for l in self.latency_trend],
            "error_count_trend": self.error_count_trend,
            "avg_latency_first_half_ms": round(self.avg_latency_first_half_ms, 2),
            "avg_latency_second_half_ms": round(self.avg_latency_second_half_ms, 2),
            "latency_degradation_percent": round(self.latency_degradation_percent, 2),
            "stability_score": round(self.stability_score, 2),
        }


@dataclass
class TTFBStats:
    """Time To First Byte statistics for streaming responses."""
    count: int = 0
    min_ms: float = 0
    max_ms: float = 0
    mean_ms: float = 0
    p50_ms: float = 0
    p99_ms: float = 0
    samples: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "mean_ms": round(self.mean_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
        }


@dataclass
class FullPerfResult:
    """Complete performance test result with all metrics."""
    model: str
    endpoint: str
    timestamp: str
    test_type: str  # "basic", "concurrent", "stability", "full"
    
    # Core metrics
    latency: LatencyStats = field(default_factory=LatencyStats)
    errors: ErrorStats = field(default_factory=ErrorStats)
    slo_results: List[SLOResult] = field(default_factory=list)
    
    # Extended metrics
    concurrent: Optional[ConcurrentStats] = None
    stability: Optional[StabilityStats] = None
    ttfb: Optional[TTFBStats] = None
    
    duration_seconds: float = 0.0
    requests_per_second: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "model": self.model,
            "endpoint": self.endpoint,
            "timestamp": self.timestamp,
            "test_type": self.test_type,
            "latency": self.latency.to_dict(),
            "errors": self.errors.to_dict(),
            "slo_results": [s.to_dict() for s in self.slo_results],
            "duration_seconds": round(self.duration_seconds, 2),
            "requests_per_second": round(self.requests_per_second, 4),
        }
        
        if self.concurrent:
            result["concurrent"] = self.concurrent.to_dict()
        if self.stability:
            result["stability"] = self.stability.to_dict()
        if self.ttfb:
            result["ttfb"] = self.ttfb.to_dict()
        
        return result
    
    def passed_all_slos(self) -> bool:
        return all(slo.passed for slo in self.slo_results)


@dataclass
class SLOConfig:
    """SLO threshold configuration."""
    latency_p50_ms: float = 5000
    latency_p99_ms: float = 30000
    error_rate_percent: float = 1.0
    availability_percent: float = 99.9
    ttfb_p99_ms: float = 5000  # TTFB P99 target
    throughput_min_rps: float = 0.1  # Minimum throughput
    stability_score_min: float = 80.0  # Minimum stability score


class PerfTester:
    """
    Performance tester for API infrastructure.
    
    Tests latency, error rates, and validates against SLOs.
    """
    
    # Standard test prompt - simple, consistent
    TEST_PROMPT = "Say 'ok' and nothing else."
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        slo_config: Optional[SLOConfig] = None,
    ):
        config = get_config()
        self.api_key = api_key or config.api_key
        self.slo_config = slo_config or SLOConfig()
        self.invoker = ModelInvoker(api_key=self.api_key)
        
    def _classify_error(self, result: InvokeResult) -> ErrorType:
        """Classify the type of error from an invoke result."""
        if result.success:
            return ErrorType.NONE
        
        error = result.error or ""
        error_lower = error.lower()
        
        if "timeout" in error_lower:
            return ErrorType.TIMEOUT
        elif "connection" in error_lower or "connect" in error_lower:
            return ErrorType.CONNECTION
        elif "http 4" in error_lower or "400" in error or "401" in error or "403" in error or "404" in error:
            return ErrorType.HTTP_4XX
        elif "http 5" in error_lower or "500" in error or "502" in error or "503" in error:
            return ErrorType.HTTP_5XX
        else:
            return ErrorType.UNKNOWN
    
    def _calculate_percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile from sorted data."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = (len(sorted_data) - 1) * percentile / 100
        lower = int(index)
        upper = lower + 1
        if upper >= len(sorted_data):
            return sorted_data[-1]
        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight
    
    def _compute_latency_stats(self, latencies_ms: List[float]) -> LatencyStats:
        """Compute latency statistics from samples."""
        if not latencies_ms:
            return LatencyStats()
        
        return LatencyStats(
            count=len(latencies_ms),
            min_ms=min(latencies_ms),
            max_ms=max(latencies_ms),
            mean_ms=statistics.mean(latencies_ms),
            median_ms=statistics.median(latencies_ms),
            p50_ms=self._calculate_percentile(latencies_ms, 50),
            p90_ms=self._calculate_percentile(latencies_ms, 90),
            p95_ms=self._calculate_percentile(latencies_ms, 95),
            p99_ms=self._calculate_percentile(latencies_ms, 99),
            std_dev_ms=statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0,
            samples=latencies_ms,
        )
    
    def _compute_error_stats(self, results: List[InvokeResult]) -> ErrorStats:
        """Compute error statistics from results."""
        if not results:
            return ErrorStats()
        
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        
        errors_by_type: Dict[str, int] = {}
        for r in results:
            error_type = self._classify_error(r)
            if error_type != ErrorType.NONE:
                errors_by_type[error_type.value] = errors_by_type.get(error_type.value, 0) + 1
        
        return ErrorStats(
            total_requests=total,
            successful_requests=successful,
            failed_requests=failed,
            error_rate=failed / total if total > 0 else 0.0,
            errors_by_type=errors_by_type,
        )
    
    def _validate_slos(self, latency: LatencyStats, errors: ErrorStats) -> List[SLOResult]:
        """Validate results against SLO thresholds."""
        slo = self.slo_config
        results = []
        
        # Latency P50
        results.append(SLOResult(
            name="Latency P50",
            target=slo.latency_p50_ms,
            actual=latency.p50_ms,
            passed=latency.p50_ms <= slo.latency_p50_ms,
            unit="ms",
        ))
        
        # Latency P99
        results.append(SLOResult(
            name="Latency P99",
            target=slo.latency_p99_ms,
            actual=latency.p99_ms,
            passed=latency.p99_ms <= slo.latency_p99_ms,
            unit="ms",
        ))
        
        # Error Rate
        error_rate_pct = errors.error_rate * 100
        results.append(SLOResult(
            name="Error Rate",
            target=slo.error_rate_percent,
            actual=error_rate_pct,
            passed=error_rate_pct <= slo.error_rate_percent,
            unit="%",
        ))
        
        # Availability
        availability = (1 - errors.error_rate) * 100
        results.append(SLOResult(
            name="Availability",
            target=slo.availability_percent,
            actual=availability,
            passed=availability >= slo.availability_percent,
            unit="%",
        ))
        
        return results
    
    def run_latency_test(
        self,
        model: str,
        warmup_requests: int = 3,
        sample_requests: int = 20,
        show_progress: bool = True,
    ) -> PerfTestResult:
        """
        Run latency test for a model.
        
        Args:
            model: Model path to test
            warmup_requests: Number of warmup requests (not included in stats)
            sample_requests: Number of sample requests for statistics
            show_progress: Whether to show progress
            
        Returns:
            PerfTestResult with latency stats and SLO validation
        """
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
        
        console = Console()
        endpoint = get_model_endpoint(model)
        start_time = time.time()
        
        all_results: List[InvokeResult] = []
        latencies_ms: List[float] = []
        
        total_requests = warmup_requests + sample_requests
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
            disable=not show_progress,
        ) as progress:
            task = progress.add_task(
                f"Testing {model.split('/')[-1]}",
                total=total_requests,
            )
            
            # Warmup phase
            for i in range(warmup_requests):
                progress.update(task, description=f"[yellow]Warmup {i+1}/{warmup_requests}")
                self.invoker.invoke(
                    prompt=self.TEST_PROMPT,
                    model=model,
                    max_tokens=10,
                    temperature=0,
                )
                progress.advance(task)
            
            # Sample phase
            for i in range(sample_requests):
                progress.update(task, description=f"[cyan]Sample {i+1}/{sample_requests}")
                result = self.invoker.invoke(
                    prompt=self.TEST_PROMPT,
                    model=model,
                    max_tokens=10,
                    temperature=0,
                )
                all_results.append(result)
                
                if result.success:
                    latencies_ms.append(result.latency * 1000)  # Convert to ms
                
                progress.advance(task)
        
        duration = time.time() - start_time
        
        # Compute statistics
        latency_stats = self._compute_latency_stats(latencies_ms)
        error_stats = self._compute_error_stats(all_results)
        slo_results = self._validate_slos(latency_stats, error_stats)
        
        return PerfTestResult(
            model=model,
            endpoint=endpoint,
            timestamp=datetime.now().isoformat(),
            latency=latency_stats,
            errors=error_stats,
            slo_results=slo_results,
            duration_seconds=duration,
            requests_per_second=sample_requests / duration if duration > 0 else 0,
        )
    
    def print_result(self, result: PerfTestResult) -> None:
        """Print performance test result to console."""
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        
        console = getattr(self, "console", Console())
        
        # Header
        console.print(f"\n[bold]═══ Performance Test: {result.model} ═══[/bold]\n")
        
        # Latency table
        latency_table = Table(title="Latency Statistics", show_header=True)
        latency_table.add_column("Metric", style="cyan")
        latency_table.add_column("Value", justify="right")
        
        lat = result.latency
        latency_table.add_row("Samples", str(lat.count))
        latency_table.add_row("Min", f"{lat.min_ms:.0f} ms")
        latency_table.add_row("Max", f"{lat.max_ms:.0f} ms")
        latency_table.add_row("Mean", f"{lat.mean_ms:.0f} ms")
        latency_table.add_row("P50", f"{lat.p50_ms:.0f} ms")
        latency_table.add_row("P90", f"{lat.p90_ms:.0f} ms")
        latency_table.add_row("P95", f"{lat.p95_ms:.0f} ms")
        latency_table.add_row("P99", f"{lat.p99_ms:.0f} ms")
        latency_table.add_row("Std Dev", f"{lat.std_dev_ms:.0f} ms")
        
        console.print(latency_table)
        
        # Error table
        error_table = Table(title="Error Statistics", show_header=True)
        error_table.add_column("Metric", style="cyan")
        error_table.add_column("Value", justify="right")
        
        err = result.errors
        error_table.add_row("Total Requests", str(err.total_requests))
        error_table.add_row("Successful", f"[green]{err.successful_requests}[/green]")
        error_table.add_row("Failed", f"[red]{err.failed_requests}[/red]" if err.failed_requests > 0 else "0")
        error_table.add_row("Error Rate", f"{err.error_rate * 100:.2f}%")
        
        if err.errors_by_type:
            for error_type, count in err.errors_by_type.items():
                error_table.add_row(f"  └ {error_type}", str(count))
        
        console.print(error_table)
        
        # SLO table
        slo_table = Table(title="SLO Validation", show_header=True)
        slo_table.add_column("SLO", style="cyan")
        slo_table.add_column("Target", justify="right")
        slo_table.add_column("Actual", justify="right")
        slo_table.add_column("Status", justify="center")
        
        for slo in result.slo_results:
            status = "[green]✓ PASS[/green]" if slo.passed else "[red]✗ FAIL[/red]"
            target_str = f"{slo.target:.0f} {slo.unit}" if slo.unit else f"{slo.target:.2f}"
            actual_str = f"{slo.actual:.0f} {slo.unit}" if slo.unit else f"{slo.actual:.2f}"
            slo_table.add_row(slo.name, target_str, actual_str, status)
        
        console.print(slo_table)
        
        # Summary
        all_passed = result.passed_all_slos()
        status_msg = "[green]All SLOs Passed ✓[/green]" if all_passed else "[red]Some SLOs Failed ✗[/red]"
        console.print(f"\n{status_msg}")
        console.print(f"Duration: {result.duration_seconds:.1f}s | Throughput: {result.requests_per_second:.2f} req/s")
    
    async def _async_invoke(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 10,
    ) -> InvokeResult:
        """Async wrapper for synchronous invoke (runs in executor)."""
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(
                executor,
                lambda: self.invoker.invoke(
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=0,
                )
            )
        return result
    
    def run_concurrent_test(
        self,
        model: str,
        concurrent_requests: int = 5,
        total_requests: int = 20,
        show_progress: bool = True,
    ) -> ConcurrentStats:
        """
        Run concurrent/throughput test.
        
        Simulates multiple users making requests simultaneously.
        
        Args:
            model: Model path to test
            concurrent_requests: Number of simultaneous requests
            total_requests: Total number of requests to make
            show_progress: Whether to show progress
            
        Returns:
            ConcurrentStats with throughput metrics
        """
        from rich.console import Console
        
        console = Console()
        
        if show_progress:
            console.print(f"[cyan]Running concurrent test ({concurrent_requests} concurrent, {total_requests} total)...[/cyan]")
        
        results: List[InvokeResult] = []
        latencies_ms: List[float] = []
        
        async def run_batch():
            nonlocal results, latencies_ms
            semaphore = asyncio.Semaphore(concurrent_requests)
            
            async def bounded_invoke():
                async with semaphore:
                    return await self._async_invoke(
                        prompt=self.TEST_PROMPT,
                        model=model,
                        max_tokens=10,
                    )
            
            tasks = [bounded_invoke() for _ in range(total_requests)]
            batch_results = await asyncio.gather(*tasks)
            results = list(batch_results)
            
            for r in results:
                if r.success:
                    latencies_ms.append(r.latency * 1000)
        
        start_time = time.time()
        asyncio.run(run_batch())
        duration = time.time() - start_time
        
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        
        return ConcurrentStats(
            concurrent_requests=concurrent_requests,
            total_requests=len(results),
            successful_requests=successful,
            failed_requests=failed,
            throughput_rps=len(results) / duration if duration > 0 else 0,
            avg_latency_ms=statistics.mean(latencies_ms) if latencies_ms else 0,
            max_latency_ms=max(latencies_ms) if latencies_ms else 0,
            duration_seconds=duration,
        )
    
    def run_stability_test(
        self,
        model: str,
        total_requests: int = 50,
        interval_seconds: float = 2.0,
        show_progress: bool = True,
    ) -> StabilityStats:
        """
        Run stability test - long-running performance trends.
        
        Makes requests at regular intervals and tracks latency trends
        to detect performance degradation.
        
        Args:
            model: Model path to test
            total_requests: Total number of requests
            interval_seconds: Seconds between requests
            show_progress: Whether to show progress
            
        Returns:
            StabilityStats with trend analysis
        """
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
        
        console = Console()
        
        latency_trend: List[float] = []
        error_count = 0
        
        start_time = time.time()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
            disable=not show_progress,
        ) as progress:
            task = progress.add_task(
                f"[magenta]Stability test",
                total=total_requests,
            )
            
            for i in range(total_requests):
                progress.update(task, description=f"[magenta]Stability {i+1}/{total_requests}")
                
                result = self.invoker.invoke(
                    prompt=self.TEST_PROMPT,
                    model=model,
                    max_tokens=10,
                    temperature=0,
                )
                
                if result.success:
                    latency_trend.append(result.latency * 1000)
                else:
                    error_count += 1
                    latency_trend.append(0)  # Mark error with 0
                
                progress.advance(task)
                
                # Wait before next request (skip on last)
                if i < total_requests - 1:
                    time.sleep(interval_seconds)
        
        duration = time.time() - start_time
        
        # Compute stability metrics
        valid_latencies = [l for l in latency_trend if l > 0]
        mid = len(valid_latencies) // 2
        
        first_half = valid_latencies[:mid] if mid > 0 else valid_latencies
        second_half = valid_latencies[mid:] if mid > 0 else valid_latencies
        
        avg_first = statistics.mean(first_half) if first_half else 0
        avg_second = statistics.mean(second_half) if second_half else 0
        
        # Calculate degradation percentage
        degradation = 0.0
        if avg_first > 0:
            degradation = ((avg_second - avg_first) / avg_first) * 100
        
        # Calculate stability score (100 = perfect, lower = degraded)
        # Penalize for: degradation, high variance, errors
        stability_score = 100.0
        
        if valid_latencies:
            cv = (statistics.stdev(valid_latencies) / statistics.mean(valid_latencies) * 100) if len(valid_latencies) > 1 else 0
            stability_score -= min(cv, 30)  # Penalize up to 30% for variance
        
        stability_score -= min(abs(degradation), 30)  # Penalize up to 30% for degradation
        stability_score -= (error_count / total_requests) * 40  # Penalize up to 40% for errors
        stability_score = max(0, stability_score)
        
        return StabilityStats(
            total_requests=total_requests,
            test_duration_seconds=duration,
            latency_trend=latency_trend,
            error_count_trend=[error_count],  # Simplified
            avg_latency_first_half_ms=avg_first,
            avg_latency_second_half_ms=avg_second,
            latency_degradation_percent=degradation,
            stability_score=stability_score,
        )
    
    def run_ttfb_test(
        self,
        model: str,
        sample_requests: int = 10,
        show_progress: bool = True,
    ) -> TTFBStats:
        """
        Run TTFB (Time To First Byte) test for streaming responses.
        
        Measures how quickly the first token arrives.
        
        Args:
            model: Model path to test
            sample_requests: Number of samples
            show_progress: Whether to show progress
            
        Returns:
            TTFBStats with TTFB metrics
        """
        import httpx
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
        
        console = Console()
        endpoint = get_model_endpoint(model)
        config = get_config()
        
        ttfb_samples: List[float] = []
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": self.TEST_PROMPT}],
            "max_tokens": 50,
            "temperature": 0,
            "stream": True,
        }
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
            disable=not show_progress,
        ) as progress:
            task = progress.add_task(
                f"[yellow]TTFB test",
                total=sample_requests,
            )
            
            for i in range(sample_requests):
                progress.update(task, description=f"[yellow]TTFB {i+1}/{sample_requests}")
                
                try:
                    start_time = time.perf_counter()
                    
                    with httpx.Client(timeout=config.timeout) as client:
                        with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                            # Time to first byte = when we receive first chunk
                            for chunk in response.iter_bytes():
                                ttfb = (time.perf_counter() - start_time) * 1000
                                ttfb_samples.append(ttfb)
                                break  # Only measure first byte
                                
                except Exception as e:
                    console.print(f"[red]TTFB error: {e}[/red]")
                
                progress.advance(task)
        
        if not ttfb_samples:
            return TTFBStats()
        
        return TTFBStats(
            count=len(ttfb_samples),
            min_ms=min(ttfb_samples),
            max_ms=max(ttfb_samples),
            mean_ms=statistics.mean(ttfb_samples),
            p50_ms=self._calculate_percentile(ttfb_samples, 50),
            p99_ms=self._calculate_percentile(ttfb_samples, 99),
            samples=ttfb_samples,
        )
    
    def run_full_test(
        self,
        model: str,
        warmup_requests: int = 3,
        sample_requests: int = 20,
        concurrent_requests: int = 5,
        stability_requests: int = 30,
        stability_interval: float = 1.0,
        ttfb_samples: int = 10,
        show_progress: bool = True,
    ) -> FullPerfResult:
        """
        Run comprehensive performance test with all metrics.
        
        Includes: latency, concurrent, stability, and TTFB tests.
        
        Args:
            model: Model path to test
            warmup_requests: Number of warmup requests
            sample_requests: Number of latency samples
            concurrent_requests: Concurrency level
            stability_requests: Number of stability test requests
            stability_interval: Seconds between stability requests
            ttfb_samples: Number of TTFB samples
            show_progress: Whether to show progress
            
        Returns:
            FullPerfResult with all metrics
        """
        from rich.console import Console
        
        console = Console()
        endpoint = get_model_endpoint(model)
        
        console.print(f"\n[bold]═══ Full Performance Test: {model} ═══[/bold]\n")
        
        start_time = time.time()
        all_results: List[InvokeResult] = []
        latencies_ms: List[float] = []
        
        # Phase 1: Basic latency test
        console.print("[bold cyan]Phase 1: Latency Test[/bold cyan]")
        basic_result = self.run_latency_test(
            model=model,
            warmup_requests=warmup_requests,
            sample_requests=sample_requests,
            show_progress=show_progress,
        )
        
        # Phase 2: Concurrent test
        console.print("\n[bold cyan]Phase 2: Concurrent Test[/bold cyan]")
        concurrent_stats = self.run_concurrent_test(
            model=model,
            concurrent_requests=concurrent_requests,
            total_requests=sample_requests,
            show_progress=show_progress,
        )
        
        # Phase 3: Stability test
        console.print("\n[bold cyan]Phase 3: Stability Test[/bold cyan]")
        stability_stats = self.run_stability_test(
            model=model,
            total_requests=stability_requests,
            interval_seconds=stability_interval,
            show_progress=show_progress,
        )
        
        # Phase 4: TTFB test
        console.print("\n[bold cyan]Phase 4: TTFB Test[/bold cyan]")
        ttfb_stats = self.run_ttfb_test(
            model=model,
            sample_requests=ttfb_samples,
            show_progress=show_progress,
        )
        
        duration = time.time() - start_time
        
        # Build extended SLO results
        slo_results = basic_result.slo_results.copy()
        
        # Add TTFB SLO
        if ttfb_stats.count > 0:
            slo_results.append(SLOResult(
                name="TTFB P99",
                target=self.slo_config.ttfb_p99_ms,
                actual=ttfb_stats.p99_ms,
                passed=ttfb_stats.p99_ms <= self.slo_config.ttfb_p99_ms,
                unit="ms",
            ))
        
        # Add Throughput SLO
        slo_results.append(SLOResult(
            name="Throughput",
            target=self.slo_config.throughput_min_rps,
            actual=concurrent_stats.throughput_rps,
            passed=concurrent_stats.throughput_rps >= self.slo_config.throughput_min_rps,
            unit="req/s",
        ))
        
        # Add Stability SLO
        slo_results.append(SLOResult(
            name="Stability Score",
            target=self.slo_config.stability_score_min,
            actual=stability_stats.stability_score,
            passed=stability_stats.stability_score >= self.slo_config.stability_score_min,
            unit="",
        ))
        
        return FullPerfResult(
            model=model,
            endpoint=endpoint,
            timestamp=datetime.now().isoformat(),
            test_type="full",
            latency=basic_result.latency,
            errors=basic_result.errors,
            slo_results=slo_results,
            concurrent=concurrent_stats,
            stability=stability_stats,
            ttfb=ttfb_stats,
            duration_seconds=duration,
            requests_per_second=basic_result.requests_per_second,
        )
    
    def print_full_result(self, result: FullPerfResult) -> None:
        """Print full performance test result to console."""
        from rich.console import Console
        from rich.table import Table
        
        console = getattr(self, "console", Console())
        
        # Header
        console.print(f"\n[bold]═══ Full Performance Report: {result.model} ═══[/bold]\n")
        
        # Latency table
        latency_table = Table(title="Latency Statistics", show_header=True)
        latency_table.add_column("Metric", style="cyan")
        latency_table.add_column("Value", justify="right")
        
        lat = result.latency
        latency_table.add_row("Samples", str(lat.count))
        latency_table.add_row("Min", f"{lat.min_ms:.0f} ms")
        latency_table.add_row("Max", f"{lat.max_ms:.0f} ms")
        latency_table.add_row("Mean", f"{lat.mean_ms:.0f} ms")
        latency_table.add_row("P50", f"{lat.p50_ms:.0f} ms")
        latency_table.add_row("P90", f"{lat.p90_ms:.0f} ms")
        latency_table.add_row("P95", f"{lat.p95_ms:.0f} ms")
        latency_table.add_row("P99", f"{lat.p99_ms:.0f} ms")
        
        console.print(latency_table)
        
        # Concurrent table
        if result.concurrent:
            conc_table = Table(title="Concurrent/Throughput", show_header=True)
            conc_table.add_column("Metric", style="cyan")
            conc_table.add_column("Value", justify="right")
            
            conc = result.concurrent
            conc_table.add_row("Concurrency", str(conc.concurrent_requests))
            conc_table.add_row("Total Requests", str(conc.total_requests))
            conc_table.add_row("Throughput", f"{conc.throughput_rps:.2f} req/s")
            conc_table.add_row("Avg Latency", f"{conc.avg_latency_ms:.0f} ms")
            conc_table.add_row("Max Latency", f"{conc.max_latency_ms:.0f} ms")
            
            console.print(conc_table)
        
        # Stability table
        if result.stability:
            stab_table = Table(title="Stability Analysis", show_header=True)
            stab_table.add_column("Metric", style="cyan")
            stab_table.add_column("Value", justify="right")
            
            stab = result.stability
            stab_table.add_row("Total Requests", str(stab.total_requests))
            stab_table.add_row("Duration", f"{stab.test_duration_seconds:.1f}s")
            stab_table.add_row("Avg Latency (1st half)", f"{stab.avg_latency_first_half_ms:.0f} ms")
            stab_table.add_row("Avg Latency (2nd half)", f"{stab.avg_latency_second_half_ms:.0f} ms")
            
            degradation_color = "green" if stab.latency_degradation_percent <= 10 else "red"
            stab_table.add_row("Degradation", f"[{degradation_color}]{stab.latency_degradation_percent:.1f}%[/{degradation_color}]")
            
            score_color = "green" if stab.stability_score >= 80 else "yellow" if stab.stability_score >= 60 else "red"
            stab_table.add_row("Stability Score", f"[{score_color}]{stab.stability_score:.1f}/100[/{score_color}]")
            
            console.print(stab_table)
        
        # TTFB table
        if result.ttfb and result.ttfb.count > 0:
            ttfb_table = Table(title="TTFB (Time To First Byte)", show_header=True)
            ttfb_table.add_column("Metric", style="cyan")
            ttfb_table.add_column("Value", justify="right")
            
            ttfb = result.ttfb
            ttfb_table.add_row("Samples", str(ttfb.count))
            ttfb_table.add_row("Min", f"{ttfb.min_ms:.0f} ms")
            ttfb_table.add_row("Max", f"{ttfb.max_ms:.0f} ms")
            ttfb_table.add_row("Mean", f"{ttfb.mean_ms:.0f} ms")
            ttfb_table.add_row("P50", f"{ttfb.p50_ms:.0f} ms")
            ttfb_table.add_row("P99", f"{ttfb.p99_ms:.0f} ms")
            
            console.print(ttfb_table)
        
        # Error table
        error_table = Table(title="Error Statistics", show_header=True)
        error_table.add_column("Metric", style="cyan")
        error_table.add_column("Value", justify="right")
        
        err = result.errors
        error_table.add_row("Total Requests", str(err.total_requests))
        error_table.add_row("Successful", f"[green]{err.successful_requests}[/green]")
        error_table.add_row("Failed", f"[red]{err.failed_requests}[/red]" if err.failed_requests > 0 else "0")
        error_table.add_row("Error Rate", f"{err.error_rate * 100:.2f}%")
        
        console.print(error_table)
        
        # SLO table
        slo_table = Table(title="SLO Validation", show_header=True)
        slo_table.add_column("SLO", style="cyan")
        slo_table.add_column("Target", justify="right")
        slo_table.add_column("Actual", justify="right")
        slo_table.add_column("Status", justify="center")
        
        for slo in result.slo_results:
            status = "[green]✓ PASS[/green]" if slo.passed else "[red]✗ FAIL[/red]"
            if slo.unit:
                target_str = f"{slo.target:.0f} {slo.unit}" if slo.target >= 1 else f"{slo.target:.2f} {slo.unit}"
                actual_str = f"{slo.actual:.0f} {slo.unit}" if slo.actual >= 1 else f"{slo.actual:.2f} {slo.unit}"
            else:
                target_str = f"{slo.target:.1f}"
                actual_str = f"{slo.actual:.1f}"
            slo_table.add_row(slo.name, target_str, actual_str, status)
        
        console.print(slo_table)
        
        # Summary
        all_passed = result.passed_all_slos()
        status_msg = "[green]All SLOs Passed ✓[/green]" if all_passed else "[red]Some SLOs Failed ✗[/red]"
        console.print(f"\n{status_msg}")
        console.print(f"Total Duration: {result.duration_seconds:.1f}s")
