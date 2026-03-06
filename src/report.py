"""
Report Generator - Generate HTML, JSON, and Markdown reports.

Creates beautiful, informative reports with charts and detailed test results.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Template


class ReportGenerator:
    """
    Generates reports in various formats from test results.
    """
    
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_html(self, suite_result: Any) -> str:
        """Generate an HTML report with embedded Chart.js visualizations."""
        template = Template(HTML_TEMPLATE)
        
        # Prepare data for charts
        chart_data = self._prepare_chart_data(suite_result)
        
        html = template.render(
            suite=suite_result,
            results=suite_result.results,
            chart_data=json.dumps(chart_data),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        
        output_path = os.path.join(self.output_dir, "index.html")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return output_path
    
    def generate_json(self, suite_result: Any) -> str:
        """Generate a JSON report."""
        output_path = os.path.join(self.output_dir, "report.json")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(suite_result.to_dict(), f, indent=2, ensure_ascii=False)
        
        return output_path
    
    def generate_markdown(self, suite_result: Any) -> str:
        """Generate a Markdown report."""
        template = Template(MARKDOWN_TEMPLATE)
        
        md = template.render(
            suite=suite_result,
            results=suite_result.results,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        
        output_path = os.path.join(self.output_dir, "report.md")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md)
        
        return output_path
    
    def generate_text_table(self, suite_result: Any) -> str:
        """Generate a plain text table report (like terminal output)."""
        from io import StringIO
        from rich.console import Console
        from rich.table import Table
        
        # Create a console that writes to string
        string_buffer = StringIO()
        text_console = Console(file=string_buffer, width=120, legacy_windows=False)
        
        # Header
        text_console.print()
        text_console.print(f"[bold blue]═══ {suite_result.suite_name} ═══[/bold blue]")
        text_console.print()
        
        # Summary stats table
        summary_table = Table(title="Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", justify="right")
        
        summary_table.add_row("Total Tests", str(suite_result.total_tests))
        summary_table.add_row("Passed", f"[green]{suite_result.passed_tests}[/green]")
        summary_table.add_row("Failed", f"[red]{suite_result.failed_tests}[/red]")
        summary_table.add_row("Errors", f"[yellow]{suite_result.error_tests}[/yellow]")
        summary_table.add_row("Pass Rate", f"{suite_result.pass_rate:.1%}")
        summary_table.add_row("Avg Latency", f"{suite_result.avg_latency:.2f}s")
        summary_table.add_row("P50 Latency", f"{suite_result.latency_stats['p50']:.2f}s")
        summary_table.add_row("P99 Latency", f"{suite_result.latency_stats['p99']:.2f}s")
        summary_table.add_row("Duration", f"{suite_result.duration_seconds:.1f}s")
        
        text_console.print(summary_table)
        
        # Results table
        text_console.print()
        results_table = Table(title="Test Results")
        results_table.add_column("ID", style="cyan", max_width=20)
        results_table.add_column("Model", max_width=25)
        results_table.add_column("Latency", justify="right")
        results_table.add_column("Score", justify="right")
        results_table.add_column("Verdict")
        
        for r in suite_result.results:
            verdict_style = "green" if r.passed else ("yellow" if r.verdict == "ERROR" else "red")
            model_short = r.model.split("/")[-1][:20]
            
            results_table.add_row(
                r.test_id[:20],
                model_short,
                f"{r.latency:.2f}s",
                f"{r.score:.2f}",
                f"[{verdict_style}]{r.verdict}[/{verdict_style}]"
            )
        
        text_console.print(results_table)
        text_console.print()
        
        # Get the string content
        output_text = string_buffer.getvalue()
        
        # Write to file
        output_path = os.path.join(self.output_dir, "report.txt")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(output_text)
        
        return output_path
    
    def generate_junit_xml(self, suite_result: Any) -> str:
        """Generate JUnit XML for CI/CD integration."""
        test_cases = []
        
        for r in suite_result.results:
            if r.passed:
                test_case = f'    <testcase name="{r.test_id}" classname="{r.model}" time="{r.latency:.3f}"/>'
            elif r.verdict == "ERROR":
                test_case = f'''    <testcase name="{r.test_id}" classname="{r.model}" time="{r.latency:.3f}">
      <error message="{self._escape_xml(r.error or 'Unknown error')}"/>
    </testcase>'''
            else:
                test_case = f'''    <testcase name="{r.test_id}" classname="{r.model}" time="{r.latency:.3f}">
      <failure message="Score: {r.score:.2f}, Expected to pass"/>
    </testcase>'''
            test_cases.append(test_case)
        
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="{suite_result.suite_name}" tests="{suite_result.total_tests}" failures="{suite_result.failed_tests}" errors="{suite_result.error_tests}" time="{suite_result.duration_seconds:.3f}">
{chr(10).join(test_cases)}
</testsuite>'''
        
        output_path = os.path.join(self.output_dir, "junit.xml")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(xml)
        
        return output_path
    
    def _prepare_chart_data(self, suite_result: Any) -> Dict[str, Any]:
        """Prepare data for Chart.js visualizations."""
        # Pass/Fail pie chart
        pass_fail = {
            "labels": ["Passed", "Failed", "Errors"],
            "data": [
                suite_result.passed_tests,
                suite_result.failed_tests,
                suite_result.error_tests,
            ],
            "colors": ["#22c55e", "#ef4444", "#f59e0b"]
        }
        
        # Latency distribution
        latencies = [r.latency for r in suite_result.results]
        latency_dist = {
            "labels": [r.test_id[:15] for r in suite_result.results],
            "data": latencies,
        }
        
        # Score distribution by metric
        metric_scores: Dict[str, List[float]] = {}
        for r in suite_result.results:
            if r.metric_type not in metric_scores:
                metric_scores[r.metric_type] = []
            metric_scores[r.metric_type].append(r.score)
        
        avg_by_metric = {
            "labels": list(metric_scores.keys()),
            "data": [sum(v)/len(v) if v else 0 for v in metric_scores.values()],
        }
        
        # Model comparison
        model_stats: Dict[str, Dict[str, Any]] = {}
        for r in suite_result.results:
            if r.model not in model_stats:
                model_stats[r.model] = {"passed": 0, "total": 0, "latencies": []}
            model_stats[r.model]["total"] += 1
            if r.passed:
                model_stats[r.model]["passed"] += 1
            model_stats[r.model]["latencies"].append(r.latency)
        
        model_comparison = {
            "labels": [m.split("/")[-1][:20] for m in model_stats.keys()],
            "pass_rates": [s["passed"]/s["total"]*100 if s["total"] else 0 for s in model_stats.values()],
            "avg_latencies": [sum(s["latencies"])/len(s["latencies"]) if s["latencies"] else 0 for s in model_stats.values()],
        }
        
        return {
            "passFail": pass_fail,
            "latencyDist": latency_dist,
            "avgByMetric": avg_by_metric,
            "modelComparison": model_comparison,
        }
    
    def _escape_xml(self, text: str) -> str:
        """Escape special characters for XML."""
        return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


# HTML Template with embedded React & Tailwind
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CanopyWave Model Tester Dashboard</title>
    <!-- React & ReactDOM -->
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <!-- Babel for in-browser JSX -->
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Recharts -->
    <script src="https://unpkg.com/recharts/umd/Recharts.min.js"></script>
    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest"></script>
    
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        background: '#0f172a',
                        surface: '#1e293b',
                        card: '#334155',
                        primary: '#3b82f6',
                        success: '#22c55e',
                        danger: '#ef4444',
                        warning: '#f59e0b',
                    }
                }
            }
        }
    </script>
    <style>
        body { background-color: #0f172a; color: #f8fafc; }
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
    </style>
</head>
<body class="antialiased selection:bg-primary/30">
    <div id="root"></div>

    <script type="text/babel">
        const { useState, useEffect, useMemo } = React;
        const { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } = window.Recharts;
        
        // Initial static data from python generator
        const STATIC_SUITE_DATA = {{ chart_data|safe }};
        const REPORT_GENERATED_AT = "{{ generated_at }}";
        const SUITE_NAME = "{{ suite.suite_name }}";

        const COLORS = ['#3b82f6', '#8b5cf6', '#22c55e', '#ef4444', '#f59e0b', '#06b6d4', '#ec4899'];

        function Dashboard() {
            const [reportType, setReportType] = useState('static'); // 'static' or 'dynamic'
            const [dynamicData, setDynamicData] = useState(null);
            const [loading, setLoading] = useState(false);
            const [error, setError] = useState(null);
            const [availableFiles, setAvailableFiles] = useState([]);
            const [selectedFile, setSelectedFile] = useState("");

            useEffect(() => {
                // Try to load any JSON files from the current directory context if served via HTTP
                fetch('.')
                    .then(res => res.text())
                    .then(html => {
                        // Very basic scraping if directory listing is enabled
                        const matches = html.match(/href="([^"]+\\.json)"/g);
                        if (matches) {
                            const files = matches.map(m => m.replace(/href="|"/g, '')).filter(f => f.includes('report'));
                            setAvailableFiles(files);
                        }
                    }).catch(err => console.log("Local directory listing not available."));
            }, []);

            const loadJsonReport = async (filename) => {
                setLoading(true);
                setError(null);
                try {
                    // For local file:// protocol this will usually fail due to CORS
                    // User needs to serve with `python -m http.server`
                    const response = await fetch(filename);
                    if (!response.ok) throw new Error("Failed to fetch");
                    const data = await response.json();
                    setDynamicData(data);
                    setReportType('dynamic');
                    setSelectedFile(filename);
                } catch (err) {
                    setError(`Cannot load ${filename}. If opening locally, you need a web server (e.g. python -m http.server) due to CORS restrictions.`);
                    console.error(err);
                } finally {
                    setLoading(false);
                }
            };

            const handleFileUpload = (event) => {
                const file = event.target.files[0];
                if (!file) return;
                
                const reader = new FileReader();
                reader.onload = (e) => {
                    try {
                        const json = JSON.parse(e.target.result);
                        setDynamicData(json);
                        setReportType('dynamic');
                        setSelectedFile(file.name);
                        setError(null);
                    } catch (err) {
                        setError("Invalid JSON file");
                    }
                };
                reader.readAsText(file);
            };

            // Calculate metrics based on currently viewed data
            const viewData = useMemo(() => {
                if (reportType === 'static') {
                    // Using QA static template data
                    return {
                        title: SUITE_NAME || "QA Test Results",
                        timestamp: REPORT_GENERATED_AT,
                        isPerf: false,
                        passRate: (STATIC_SUITE_DATA.passFail.data[0] / STATIC_SUITE_DATA.passFail.data.reduce((a,b)=>a+b, 0) * 100).toFixed(1) || 0,
                        totalCount: STATIC_SUITE_DATA.passFail.data.reduce((a,b)=>a+b, 0),
                        charts: {
                            modelCompare: STATIC_SUITE_DATA.modelComparison.labels.map((l, i) => ({
                                name: l,
                                passRate: STATIC_SUITE_DATA.modelComparison.pass_rates[i],
                                latency: STATIC_SUITE_DATA.modelComparison.avg_latencies[i]
                            })),
                            latency: STATIC_SUITE_DATA.latencyDist.labels.map((l, i) => ({
                                name: l,
                                latency: STATIC_SUITE_DATA.latencyDist.data[i]
                            }))
                        }
                    };
                } else if (dynamicData) {
                    // Dynamic JSON Data (either QA or Perf structure)
                    const isPerf = !!dynamicData.total_models || !!dynamicData.latency;
                    
                    if (isPerf) {
                        // Handle Perf JSON structure (single or full_perf array)
                        const results = dynamicData.results || [dynamicData];
                        const passes = results.filter(r => r.slo_results?.every(s => s.passed)).length;
                        
                        return {
                            title: dynamicData.total_models ? "Performance Test Overview" : "Single Performance Result",
                            timestamp: dynamicData.timestamp || new Date().toISOString(),
                            isPerf: true,
                            passRate: ((passes / results.length) * 100).toFixed(1),
                            totalCount: results.length,
                            rawData: results,
                            charts: {
                                modelCompare: results.map(r => ({
                                    name: r.model.split('/').pop(),
                                    latencyP50: r.latency?.p50_ms || 0,
                                    latencyP99: r.latency?.p99_ms || 0,
                                    throughput: r.concurrent?.throughput_rps || 0,
                                    errorRate: r.errors?.error_rate_percent || 0
                                }))
                            }
                        };
                    } else {
                        // Dynamic QA structure
                        const total = dynamicData.total_tests || 0;
                        const passed = dynamicData.passed_tests || 0;
                        return {
                            title: dynamicData.suite_name || "QA Test Results",
                            timestamp: new Date().toISOString(),
                            isPerf: false,
                            passRate: ((passed / Math.max(total, 1)) * 100).toFixed(1),
                            totalCount: total,
                            rawData: dynamicData.results,
                            charts: {
                                latency: dynamicData.results?.map(r => ({
                                    name: r.test_id,
                                    latency: r.latency
                                }))
                            }
                        };
                    }
                }
                return null;
            }, [reportType, dynamicData]);

            const [expandedRows, setExpandedRows] = useState({});

            const toggleRow = (idx) => {
                setExpandedRows(prev => ({
                    ...prev,
                    [idx]: !prev[idx]
                }));
            };

            return (
                <div className="min-h-screen bg-background text-slate-200">
                    <nav className="border-b border-surface bg-surface/50 backdrop-blur sticky top-0 z-50">
                        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                            <div className="flex justify-between h-16 items-center">
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-500 flex items-center justify-center font-bold text-white">CW</div>
                                    <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-purple-400">
                                        Model Tester
                                    </h1>
                                </div>
                                <div className="flex items-center gap-4">
                                    <button 
                                        onClick={() => setReportType('static')}
                                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${reportType === 'static' ? 'bg-primary text-white' : 'hover:bg-card text-slate-300'}`}
                                    >
                                        QA Static View
                                    </button>
                                    
                                    <label className="cursor-pointer px-4 py-2 rounded-lg text-sm font-medium bg-card hover:bg-slate-600 transition-colors border border-slate-600 flex items-center gap-2">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                                        Load JSON Report
                                        <input type="file" className="hidden" accept=".json" onChange={handleFileUpload} />
                                    </label>
                                </div>
                            </div>
                        </div>
                    </nav>

                    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                        {error && (
                            <div className="p-4 mb-8 bg-danger/20 border border-danger/50 text-danger-300 rounded-xl flex items-start gap-3">
                                <svg className="w-5 h-5 mt-0.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                                <div>{error}</div>
                            </div>
                        )}

                        {viewData && (
                            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                                <header>
                                    <h2 className="text-3xl font-bold text-white mb-2">{viewData.title}</h2>
                                    <p className="text-slate-400">Generated: {viewData.timestamp} {selectedFile && `• Source: ${selectedFile}`}</p>
                                </header>

                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                    <div className="bg-surface border border-slate-700/50 rounded-2xl p-6 shadow-xl">
                                        <div className="text-slate-400 text-sm font-medium mb-1 uppercase tracking-wider">Pass Rate</div>
                                        <div className={`text-4xl font-bold ${viewData.passRate >= 90 ? 'text-success' : viewData.passRate >= 70 ? 'text-warning' : 'text-danger'}`}>
                                            {viewData.passRate}%
                                        </div>
                                    </div>
                                    <div className="bg-surface border border-slate-700/50 rounded-2xl p-6 shadow-xl">
                                        <div className="text-slate-400 text-sm font-medium mb-1 uppercase tracking-wider">Total Tests/Models</div>
                                        <div className="text-4xl font-bold text-primary">{viewData.totalCount}</div>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                                    {viewData.isPerf && viewData.charts.modelCompare && (
                                        <>
                                            <div className="bg-surface border border-slate-700/50 rounded-2xl p-6 shadow-xl h-96 flex flex-col">
                                                <h3 className="text-lg font-bold mb-4">Latency Comparison (ms)</h3>
                                                <div className="flex-1">
                                                    <ResponsiveContainer width="100%" height="100%">
                                                        <BarChart data={viewData.charts.modelCompare}>
                                                            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                                            <XAxis dataKey="name" stroke="#94a3b8" tick={ { fill: '#94a3b8' } } />
                                                            <YAxis stroke="#94a3b8" tick={ { fill: '#94a3b8' } } />
                                                            <Tooltip contentStyle={ { backgroundColor: '#1e293b', borderColor: '#334155' } } />
                                                            <Legend />
                                                            <Bar dataKey="latencyP50" name="P50 Latency" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                                                            <Bar dataKey="latencyP99" name="P99 Latency" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                                                        </BarChart>
                                                    </ResponsiveContainer>
                                                </div>
                                            </div>
                                            <div className="bg-surface border border-slate-700/50 rounded-2xl p-6 shadow-xl h-96 flex flex-col">
                                                <h3 className="text-lg font-bold mb-4">Throughput (RPS)</h3>
                                                <div className="flex-1">
                                                    <ResponsiveContainer width="100%" height="100%">
                                                        <BarChart data={viewData.charts.modelCompare}>
                                                            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                                            <XAxis dataKey="name" stroke="#94a3b8" tick={ { fill: '#94a3b8' } } />
                                                            <YAxis stroke="#94a3b8" tick={ { fill: '#94a3b8' } } />
                                                            <Tooltip contentStyle={ { backgroundColor: '#1e293b', borderColor: '#334155' } } />
                                                            <Legend />
                                                            <Bar dataKey="throughput" name="Req/Sec" fill="#22c55e" radius={[4, 4, 0, 0]} />
                                                        </BarChart>
                                                    </ResponsiveContainer>
                                                </div>
                                            </div>
                                        </>
                                    )}

                                    {!viewData.isPerf && viewData.charts.modelCompare && (
                                        <div className="bg-surface border border-slate-700/50 rounded-2xl p-6 shadow-xl h-96 flex flex-col lg:col-span-2">
                                            <h3 className="text-lg font-bold mb-4">Model QA Comparison</h3>
                                            <div className="flex-1">
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <BarChart data={viewData.charts.modelCompare}>
                                                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                                                        <XAxis dataKey="name" stroke="#94a3b8" />
                                                        <YAxis yAxisId="left" stroke="#94a3b8" />
                                                        <YAxis yAxisId="right" orientation="right" stroke="#94a3b8" />
                                                        <Tooltip contentStyle={ { backgroundColor: '#1e293b', borderColor: '#334155' } } />
                                                        <Legend />
                                                        <Bar yAxisId="left" dataKey="passRate" name="Pass Rate %" fill="#22c55e" radius={[4, 4, 0, 0]} />
                                                        <Bar yAxisId="right" dataKey="latency" name="Avg Latency (s)" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                                                    </BarChart>
                                                </ResponsiveContainer>
                                            </div>
                                        </div>
                                    )}
                                </div>
                                
                                {viewData.isPerf && viewData.rawData && (
                                    <div className="bg-surface border border-slate-700/50 rounded-2xl p-6 shadow-xl overflow-hidden mt-8">
                                        <h3 className="text-lg font-bold mb-4">Performance Details</h3>
                                        <div className="overflow-x-auto">
                                            <table className="w-full text-left border-collapse min-w-max">
                                                <thead>
                                                    <tr className="border-b border-card text-slate-400 text-sm uppercase tracking-wider">
                                                        <th className="p-4 font-medium w-8"></th>
                                                        <th className="p-4 font-medium">Model</th>
                                                        <th className="p-4 font-medium">P50 (ms)</th>
                                                        <th className="p-4 font-medium">P99 (ms)</th>
                                                        <th className="p-4 font-medium">Throughput</th>
                                                        <th className="p-4 font-medium">TTFB P99</th>
                                                        <th className="p-4 font-medium">Error Rate</th>
                                                        <th className="p-4 font-medium text-center">Status</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-card/50">
                                                    {viewData.rawData.map((row, idx) => {
                                                        const allSlosPassed = row.slo_results?.every(s => s.passed);
                                                        const isExpanded = !!expandedRows[idx];
                                                        return (
                                                            <React.Fragment key={idx}>
                                                                <tr 
                                                                    onClick={() => toggleRow(idx)}
                                                                    className="hover:bg-slate-700/20 transition-colors cursor-pointer group"
                                                                >
                                                                    <td className="p-4 text-slate-500 group-hover:text-primary transition-colors">
                                                                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`transform transition-transform ${isExpanded ? 'rotate-90' : ''}`}><polyline points="9 18 15 12 9 6"></polyline></svg>
                                                                    </td>
                                                                    <td className="p-4 font-mono text-sm text-primary">{row.model}</td>
                                                                    <td className="p-4">{row.latency?.p50_ms?.toFixed(0) || '-'}</td>
                                                                    <td className="p-4">{row.latency?.p99_ms?.toFixed(0) || '-'}</td>
                                                                    <td className="p-4">{row.concurrent?.throughput_rps?.toFixed(2) || '-'} RPS</td>
                                                                    <td className="p-4">{row.ttfb?.p99_ms?.toFixed(0) || '-'} ms</td>
                                                                    <td className="p-4">{row.errors?.error_rate_percent?.toFixed(2) || '0'}%</td>
                                                                    <td className="p-4 text-center">
                                                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${allSlosPassed ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'}`}>
                                                                            {allSlosPassed ? 'PASS' : 'FAIL'}
                                                                        </span>
                                                                    </td>
                                                                </tr>
                                                                {isExpanded && (
                                                                    <tr className="bg-card/30">
                                                                        <td colSpan="8" className="p-6 border-b border-card">
                                                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                                                                {/* Latency Details */}
                                                                                <div className="space-y-3">
                                                                                    <h4 className="text-sm font-bold text-slate-300 uppercase tracking-wide border-b border-slate-700 pb-2">Latency Details</h4>
                                                                                    <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                                                                                        <span className="text-slate-400">Min:</span><span className="text-right font-mono">{row.latency?.min_ms?.toFixed(1) || '-'} ms</span>
                                                                                        <span className="text-slate-400">P50:</span><span className="text-right font-mono">{row.latency?.p50_ms?.toFixed(1) || '-'} ms</span>
                                                                                        <span className="text-slate-400">P90:</span><span className="text-right font-mono">{row.latency?.p90_ms?.toFixed(1) || '-'} ms</span>
                                                                                        <span className="text-slate-400">P95:</span><span className="text-right font-mono">{row.latency?.p95_ms?.toFixed(1) || '-'} ms</span>
                                                                                        <span className="text-slate-400">P99:</span><span className="text-right font-mono text-warning font-semibold">{row.latency?.p99_ms?.toFixed(1) || '-'} ms</span>
                                                                                        <span className="text-slate-400">Max:</span><span className="text-right font-mono text-danger font-semibold">{row.latency?.max_ms?.toFixed(1) || '-'} ms</span>
                                                                                        <span className="text-slate-400">Mean:</span><span className="text-right font-mono">{row.latency?.mean_ms?.toFixed(1) || '-'} ms</span>
                                                                                    </div>
                                                                                </div>
                                                                                {/* Stability & TTFB */}
                                                                                <div className="space-y-3">
                                                                                    <h4 className="text-sm font-bold text-slate-300 uppercase tracking-wide border-b border-slate-700 pb-2">Extended Metrics</h4>
                                                                                    {row.stability && (
                                                                                        <div className="text-sm space-y-2">
                                                                                            <div className="flex justify-between"><span className="text-slate-400">Stability Score:</span><span className="font-bold text-primary">{row.stability.stability_score?.toFixed(1)}/100</span></div>
                                                                                            <div className="flex justify-between"><span className="text-slate-400">Degradation:</span><span>{row.stability.degradation_percent?.toFixed(1)}%</span></div>
                                                                                            <div className="flex justify-between"><span className="text-slate-400">Error Spikes:</span><span>{row.stability.error_spikes}</span></div>
                                                                                        </div>
                                                                                    )}
                                                                                    {row.ttfb && (
                                                                                        <div className="text-sm space-y-2 mt-4 pt-4 border-t border-slate-700/50">
                                                                                            <div className="flex justify-between"><span className="text-slate-400">TTFB Mean:</span><span className="font-mono">{row.ttfb.mean_ms?.toFixed(1)} ms</span></div>
                                                                                            <div className="flex justify-between"><span className="text-slate-400">TTFB P99:</span><span className="font-mono text-warning">{row.ttfb.p99_ms?.toFixed(1)} ms</span></div>
                                                                                        </div>
                                                                                    )}
                                                                                </div>
                                                                                {/* SLO Check Results */}
                                                                                <div className="space-y-3">
                                                                                    <h4 className="text-sm font-bold text-slate-300 uppercase tracking-wide border-b border-slate-700 pb-2">SLO Checks</h4>
                                                                                    <div className="space-y-2 text-sm">
                                                                                        {row.slo_results?.map((slo, i) => (
                                                                                            <div key={i} className="flex items-start gap-2">
                                                                                                {slo.passed 
                                                                                                    ? <svg className="w-4 h-4 text-success shrink-0 mt-0.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                                                                                    : <svg className="w-4 h-4 text-danger shrink-0 mt-0.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                                                                                                }
                                                                                                <span className={slo.passed ? "text-slate-300" : "text-danger"}>
                                                                                                    <span className="font-medium mr-1">{slo.metric}:</span>
                                                                                                    {slo.detail}
                                                                                                </span>
                                                                                            </div>
                                                                                        ))}
                                                                                    </div>
                                                                                </div>
                                                                            </div>
                                                                        </td>
                                                                    </tr>
                                                                )}
                                                            </React.Fragment>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}
                                
                                {!viewData.isPerf && viewData.rawData && (
                                    <div className="bg-surface border border-slate-700/50 rounded-2xl p-6 shadow-xl mt-8">
                                        <h3 className="text-lg font-bold mb-6">QA Detailed Results</h3>
                                        <div className="space-y-4">
                                            {viewData.rawData.map((test, idx) => (
                                                <div key={idx} className={`border rounded-xl p-5 ${test.passed ? 'border-success/20 bg-success/5' : 'border-danger/20 bg-danger/5'}`}>
                                                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
                                                        <div>
                                                            <div className="flex items-center gap-3">
                                                                <h4 className="font-bold text-lg text-white">{test.test_id}</h4>
                                                                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-surface border border-slate-700 font-mono text-primary">
                                                                    {test.model.split('/').pop()}
                                                                </span>
                                                            </div>
                                                            <div className="text-sm text-slate-400 mt-1 flex gap-4">
                                                                <span>Metric: <span className="text-slate-300">{test.metric_type}</span></span>
                                                                <span>Latency: <span className="text-slate-300">{test.latency?.toFixed(2)}s</span></span>
                                                                <span>Score: <span className="text-slate-300">{test.score?.toFixed(2)}</span></span>
                                                            </div>
                                                        </div>
                                                        
                                                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-bold ${test.passed ? 'bg-success/20 text-success' : 'bg-danger/20 text-danger'}`}>
                                                            {test.verdict}
                                                        </span>
                                                    </div>
                                                    
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm mt-4">
                                                        <div className="bg-background/80 p-4 rounded-lg border border-slate-800">
                                                            <div className="text-xs uppercase tracking-wider text-slate-500 font-bold mb-2">Prompt</div>
                                                            <div className="text-slate-300 whitespace-pre-wrap font-serif italic">{test.prompt}</div>
                                                        </div>
                                                        <div className="bg-background/80 p-4 rounded-lg border border-slate-800 flex flex-col gap-4">
                                                            <div>
                                                                <div className="text-xs uppercase tracking-wider text-slate-500 font-bold mb-2">Model Response</div>
                                                                <div className="text-slate-200 whitespace-pre-wrap max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                                                    {test.response_content || <span className="text-slate-600 italic">No response</span>}
                                                                </div>
                                                            </div>
                                                            {test.error && (
                                                                <div className="mt-auto pt-2">
                                                                    <div className="text-xs uppercase tracking-wider text-danger-400 font-bold mb-1">Error</div>
                                                                    <div className="text-danger-300 font-mono text-xs">{test.error}</div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </main>
                </div>
            );
        }

        const root = ReactDOM.createRoot(document.getElementById('root'));
        root.render(<Dashboard />);
    </script>
</body>
</html>
'''

MARKDOWN_TEMPLATE = '''# {{ suite.suite_name }}

> Generated at {{ generated_at }}

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | {{ suite.total_tests }} |
| Passed | {{ suite.passed_tests }} |
| Failed | {{ suite.failed_tests }} |
| Errors | {{ suite.error_tests }} |
| Pass Rate | {{ "%.1f"|format(suite.pass_rate * 100) }}% |
| Avg Latency | {{ "%.2f"|format(suite.avg_latency) }}s |
| P50 Latency | {{ "%.2f"|format(suite.latency_stats.p50) }}s |
| P90 Latency | {{ "%.2f"|format(suite.latency_stats.p90) }}s |
| P99 Latency | {{ "%.2f"|format(suite.latency_stats.p99) }}s |
| Duration | {{ "%.1f"|format(suite.duration_seconds) }}s |

## Models Tested

{% for model in suite.models_tested %}
- `{{ model }}`
{% endfor %}

## Detailed Results

| Test ID | Model | Metric | Latency | Score | Verdict |
|---------|-------|--------|---------|-------|---------|
{% for r in results %}
| {{ r.test_id }} | {{ r.model.split('/')[-1] }} | {{ r.metric_type }} | {{ "%.2f"|format(r.latency) }}s | {{ "%.2f"|format(r.score) }} | {% if r.passed %}✅ PASS{% elif r.verdict == 'ERROR' %}⚠️ ERROR{% else %}❌ FAIL{% endif %} |
{% endfor %}

## Detailed Test Output

{% for r in results %}
### {{ r.test_id }}

- **Model**: `{{ r.model }}`
- **Verdict**: {{ r.verdict }}
- **Score**: {{ "%.2f"|format(r.score) }}
- **Latency**: {{ "%.2f"|format(r.latency) }}s
- **Prompt**:
  > {{ r.prompt | replace('\n', '\n> ') }}

- **Response Content**:
  ```text
  {{ r.response_content }}
  ```

{% if r.error %}
- **Error**: {{ r.error }}
{% endif %}

---
{% endfor %}
'''
