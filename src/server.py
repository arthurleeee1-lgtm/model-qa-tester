"""
Web Dashboard Server for CanopyWave Model Tester.

Provides a web interface to:
- View test reports with interactive charts
- Run tests on demand
- Export reports in various formats (HTML, JSON, CSV, PDF)
- View historical test results
"""

import json
import os
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from .config import get_config
from .runner import TestRunner, TestSuiteResult
from .report import ReportGenerator


app = FastAPI(
    title="CanopyWave Model Tester",
    description="QA Testing Platform Dashboard",
    version="1.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store for recent results
_recent_results: List[Dict[str, Any]] = []
_current_run: Optional[TestSuiteResult] = None


class TestRunRequest(BaseModel):
    """Request to run tests."""
    config_path: str = "tests/qa_tests.yaml"
    models: Optional[List[str]] = None


class TestStatus(BaseModel):
    """Status of a test run."""
    running: bool
    progress: float
    current_test: Optional[str] = None


# API Routes

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard page."""
    return DASHBOARD_HTML


@app.get("/api/config")
async def get_api_config():
    """Get current configuration."""
    config = get_config()
    return {
        "default_model": config.default_model,
        "available_models": [m.name for m in config.available_models],
        "base_url": config.base_url,
        "timeout": config.timeout,
    }


@app.get("/api/reports")
async def list_reports():
    """List available reports."""
    reports_dir = Path("reports")
    reports = []
    
    if reports_dir.exists():
        for f in reports_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    reports.append({
                        "filename": f.name,
                        "suite_name": data.get("suite_name", "Unknown"),
                        "timestamp": data.get("timestamp", ""),
                        "pass_rate": data.get("summary", {}).get("pass_rate", 0),
                        "total_tests": data.get("summary", {}).get("total_tests", 0),
                    })
            except:
                pass
    
    # Sort by timestamp descending
    reports.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"reports": reports}


@app.get("/api/reports/{filename}")
async def get_report(filename: str):
    """Get a specific report."""
    report_path = Path("reports") / filename
    
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    
    with open(report_path) as f:
        return json.load(f)


@app.get("/api/reports/{filename}/export")
async def export_report(
    filename: str,
    format: str = Query("json", enum=["json", "csv", "html"])
):
    """Export a report in various formats."""
    report_path = Path("reports") / filename
    
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    
    with open(report_path) as f:
        data = json.load(f)
    
    if format == "json":
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    elif format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["Test ID", "Model", "Prompt", "Metric", "Latency", "Score", "Verdict"])
        
        # Data
        for r in data.get("results", []):
            writer.writerow([
                r.get("test_id"),
                r.get("model"),
                r.get("prompt", "")[:100],
                r.get("metric_type"),
                f"{r.get('latency', 0):.2f}",
                f"{r.get('score', 0):.2f}",
                r.get("verdict"),
            ])
        
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename.replace('.json', '.csv')}"}
        )
    
    elif format == "html":
        html_path = Path("reports") / "index.html"
        if html_path.exists():
            return FileResponse(
                html_path,
                media_type="text/html",
                filename="report.html"
            )
        raise HTTPException(status_code=404, detail="HTML report not found")


@app.post("/api/run")
async def run_tests(request: TestRunRequest, background_tasks: BackgroundTasks):
    """Start a new test run."""
    global _current_run
    
    config_path = request.config_path
    if not Path(config_path).exists():
        raise HTTPException(status_code=400, detail=f"Config file not found: {config_path}")
    
    # Run in background
    background_tasks.add_task(execute_tests, config_path, request.models)
    
    return {"status": "started", "message": "Test run started in background"}


async def execute_tests(config_path: str, models: Optional[List[str]] = None):
    """Execute tests in background."""
    global _current_run, _recent_results
    
    runner = TestRunner(models=models)
    tests = runner.load_tests(config_path)
    
    result = runner.run_suite(tests, show_progress=False)
    _current_run = result
    
    # Save to reports
    generator = ReportGenerator(output_dir="reports")
    generator.generate_json(result)
    generator.generate_html(result)
    
    # Add to recent results
    _recent_results.insert(0, result.to_dict())
    if len(_recent_results) > 10:
        _recent_results = _recent_results[:10]


@app.get("/api/latest")
async def get_latest_result():
    """Get the latest test result."""
    if _current_run:
        return _current_run.to_dict()
    
    # Try to load from reports
    reports_dir = Path("reports")
    json_files = sorted(reports_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
    
    if json_files:
        with open(json_files[0]) as f:
            return json.load(f)
    
    return {"message": "No test results yet"}


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """Run the dashboard server."""
    uvicorn.run(app, host=host, port=port)


# Dashboard HTML Template
DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CanopyWave Model Tester - Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a24;
            --bg-hover: #22222e;
            --text-primary: #ffffff;
            --text-secondary: #8b8b9e;
            --accent-blue: #4f8cff;
            --accent-purple: #a855f7;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --border-color: #2a2a3e;
            --gradient-1: linear-gradient(135deg, #4f8cff 0%, #a855f7 100%);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        /* Header */
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(10px);
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        
        .logo-icon {
            width: 40px;
            height: 40px;
            background: var(--gradient-1);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
        }
        
        .logo-text {
            font-size: 1.25rem;
            font-weight: 600;
            background: var(--gradient-1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .header-actions {
            display: flex;
            gap: 1rem;
        }
        
        .btn {
            padding: 0.625rem 1.25rem;
            border: none;
            border-radius: 8px;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .btn-primary {
            background: var(--gradient-1);
            color: white;
        }
        
        .btn-primary:hover {
            opacity: 0.9;
            transform: translateY(-1px);
        }
        
        .btn-secondary {
            background: var(--bg-card);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }
        
        .btn-secondary:hover {
            background: var(--bg-hover);
        }
        
        /* Main Content */
        .container {
            max-width: 1600px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }
        
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.3);
        }
        
        .stat-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.5rem;
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: 700;
        }
        
        .stat-value.green { color: var(--accent-green); }
        .stat-value.red { color: var(--accent-red); }
        .stat-value.yellow { color: var(--accent-yellow); }
        .stat-value.blue { color: var(--accent-blue); }
        
        /* Charts Section */
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .chart-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
        }
        
        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        
        .chart-title {
            font-size: 1rem;
            font-weight: 600;
        }
        
        .chart-container {
            height: 280px;
            position: relative;
        }
        
        /* Results Table */
        .table-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
        }
        
        .table-header {
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .table-title {
            font-size: 1.125rem;
            font-weight: 600;
        }
        
        .export-dropdown {
            position: relative;
        }
        
        .export-menu {
            position: absolute;
            top: 100%;
            right: 0;
            margin-top: 0.5rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            min-width: 150px;
            display: none;
            z-index: 50;
        }
        
        .export-menu.show {
            display: block;
        }
        
        .export-menu a {
            display: block;
            padding: 0.75rem 1rem;
            color: var(--text-primary);
            text-decoration: none;
            transition: background 0.2s;
        }
        
        .export-menu a:hover {
            background: var(--bg-hover);
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            text-align: left;
            padding: 1rem 1.5rem;
            background: var(--bg-secondary);
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-secondary);
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border-color);
        }
        
        td {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }
        
        tr:hover {
            background: var(--bg-hover);
        }
        
        .badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 100px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        
        .badge.pass {
            background: rgba(34, 197, 94, 0.15);
            color: var(--accent-green);
        }
        
        .badge.fail {
            background: rgba(239, 68, 68, 0.15);
            color: var(--accent-red);
        }
        
        .badge.error {
            background: rgba(245, 158, 11, 0.15);
            color: var(--accent-yellow);
        }
        
        /* Loading State */
        .loading {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 4rem;
            color: var(--text-secondary);
        }
        
        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid var(--border-color);
            border-top-color: var(--accent-blue);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 1rem;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-secondary);
        }
        
        .empty-state-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        
        /* Score Bar */
        .score-bar {
            width: 80px;
            height: 6px;
            background: var(--bg-hover);
            border-radius: 3px;
            overflow: hidden;
            display: inline-block;
            margin-right: 0.5rem;
            vertical-align: middle;
        }
        
        .score-bar-fill {
            height: 100%;
            background: var(--gradient-1);
            border-radius: 3px;
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                gap: 1rem;
            }
            
            .charts-grid {
                grid-template-columns: 1fr;
            }
            
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="logo">
            <div class="logo-icon">🧪</div>
            <span class="logo-text">CanopyWave Model Tester</span>
        </div>
        <div class="header-actions">
            <button class="btn btn-secondary" onclick="refreshData()">
                🔄 Refresh
            </button>
            <button class="btn btn-primary" onclick="runTests()">
                ▶️ Run Tests
            </button>
        </div>
    </header>
    
    <div class="container">
        <div id="loading" class="loading">
            <div class="spinner"></div>
            <span>Loading data...</span>
        </div>
        
        <div id="dashboard" style="display: none;">
            <!-- Stats -->
            <div class="stats-grid" id="stats-grid">
                <!-- Populated by JS -->
            </div>
            
            <!-- Charts -->
            <div class="charts-grid">
                <div class="chart-card">
                    <div class="chart-header">
                        <h3 class="chart-title">📊 Test Results</h3>
                    </div>
                    <div class="chart-container">
                        <canvas id="resultsChart"></canvas>
                    </div>
                </div>
                
                <div class="chart-card">
                    <div class="chart-header">
                        <h3 class="chart-title">⏱️ Latency Distribution</h3>
                    </div>
                    <div class="chart-container">
                        <canvas id="latencyChart"></canvas>
                    </div>
                </div>
                
                <div class="chart-card">
                    <div class="chart-header">
                        <h3 class="chart-title">📈 Score by Metric</h3>
                    </div>
                    <div class="chart-container">
                        <canvas id="metricChart"></canvas>
                    </div>
                </div>
                
                <div class="chart-card">
                    <div class="chart-header">
                        <h3 class="chart-title">🤖 Model Comparison</h3>
                    </div>
                    <div class="chart-container">
                        <canvas id="modelChart"></canvas>
                    </div>
                </div>
            </div>
            
            <!-- Results Table -->
            <div class="table-card">
                <div class="table-header">
                    <h3 class="table-title">📋 Test Results</h3>
                    <div class="export-dropdown">
                        <button class="btn btn-secondary" onclick="toggleExportMenu()">
                            📥 Export
                        </button>
                        <div class="export-menu" id="exportMenu">
                            <a href="#" onclick="exportAs('json')">📄 Export as JSON</a>
                            <a href="#" onclick="exportAs('csv')">📊 Export as CSV</a>
                            <a href="#" onclick="exportAs('html')">🌐 Export as HTML</a>
                        </div>
                    </div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Test ID</th>
                            <th>Model</th>
                            <th>Metric</th>
                            <th>Latency</th>
                            <th>Score</th>
                            <th>Verdict</th>
                        </tr>
                    </thead>
                    <tbody id="results-table">
                        <!-- Populated by JS -->
                    </tbody>
                </table>
            </div>
        </div>
        
        <div id="empty" class="empty-state" style="display: none;">
            <div class="empty-state-icon">🧪</div>
            <h3>No test results yet</h3>
            <p>Run your first test to see results here</p>
            <button class="btn btn-primary" style="margin-top: 1rem;" onclick="runTests()">
                ▶️ Run Tests
            </button>
        </div>
    </div>
    
    <script>
        let currentData = null;
        let charts = {};
        
        async function loadData() {
            try {
                const response = await fetch('/api/latest');
                const data = await response.json();
                
                document.getElementById('loading').style.display = 'none';
                
                if (data.message || !data.results) {
                    document.getElementById('empty').style.display = 'block';
                    return;
                }
                
                currentData = data;
                document.getElementById('dashboard').style.display = 'block';
                renderDashboard(data);
            } catch (error) {
                console.error('Error loading data:', error);
                document.getElementById('loading').innerHTML = '<p>Error loading data</p>';
            }
        }
        
        function renderDashboard(data) {
            renderStats(data);
            renderCharts(data);
            renderTable(data.results);
        }
        
        function renderStats(data) {
            const summary = data.summary || data;
            const passRate = (summary.pass_rate * 100).toFixed(1);
            const passRateColor = passRate >= 80 ? 'green' : passRate >= 50 ? 'yellow' : 'red';
            
            document.getElementById('stats-grid').innerHTML = `
                <div class="stat-card">
                    <div class="stat-label">Total Tests</div>
                    <div class="stat-value blue">${summary.total_tests}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Passed</div>
                    <div class="stat-value green">${summary.passed_tests}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Failed</div>
                    <div class="stat-value red">${summary.failed_tests}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Errors</div>
                    <div class="stat-value yellow">${summary.error_tests}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Pass Rate</div>
                    <div class="stat-value ${passRateColor}">${passRate}%</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avg Latency</div>
                    <div class="stat-value blue">${summary.avg_latency?.toFixed(2) || '0.00'}s</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">P90 Latency</div>
                    <div class="stat-value blue">${data.latency_stats?.p90?.toFixed(2) || '0.00'}s</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Duration</div>
                    <div class="stat-value blue">${summary.duration_seconds?.toFixed(1) || '0.0'}s</div>
                </div>
            `;
        }
        
        function renderCharts(data) {
            const summary = data.summary || data;
            const results = data.results || [];
            
            // Destroy existing charts
            Object.values(charts).forEach(c => c.destroy());
            
            // Results pie chart
            charts.results = new Chart(document.getElementById('resultsChart'), {
                type: 'doughnut',
                data: {
                    labels: ['Passed', 'Failed', 'Errors'],
                    datasets: [{
                        data: [summary.passed_tests, summary.failed_tests, summary.error_tests],
                        backgroundColor: ['#22c55e', '#ef4444', '#f59e0b'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom', labels: { color: '#fff' } }
                    }
                }
            });
            
            // Latency chart
            const latencies = results.map(r => r.latency);
            const labels = results.map(r => r.test_id.substring(0, 12));
            
            charts.latency = new Chart(document.getElementById('latencyChart'), {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Latency (s)',
                        data: latencies,
                        backgroundColor: '#4f8cff',
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#8b8b9e', maxRotation: 45 }, grid: { display: false } },
                        y: { ticks: { color: '#8b8b9e' }, grid: { color: 'rgba(139,139,158,0.1)' } }
                    }
                }
            });
            
            // Metric scores
            const metricScores = {};
            results.forEach(r => {
                if (!metricScores[r.metric_type]) metricScores[r.metric_type] = [];
                metricScores[r.metric_type].push(r.score);
            });
            
            charts.metric = new Chart(document.getElementById('metricChart'), {
                type: 'bar',
                data: {
                    labels: Object.keys(metricScores),
                    datasets: [{
                        label: 'Avg Score',
                        data: Object.values(metricScores).map(arr => arr.reduce((a,b) => a+b, 0) / arr.length),
                        backgroundColor: '#a855f7',
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#8b8b9e' }, grid: { display: false } },
                        y: { ticks: { color: '#8b8b9e' }, grid: { color: 'rgba(139,139,158,0.1)' }, max: 1 }
                    }
                }
            });
            
            // Model comparison
            const modelStats = {};
            results.forEach(r => {
                const model = r.model.split('/').pop();
                if (!modelStats[model]) modelStats[model] = { passed: 0, total: 0 };
                modelStats[model].total++;
                if (r.passed) modelStats[model].passed++;
            });
            
            charts.model = new Chart(document.getElementById('modelChart'), {
                type: 'bar',
                data: {
                    labels: Object.keys(modelStats),
                    datasets: [{
                        label: 'Pass Rate (%)',
                        data: Object.values(modelStats).map(s => (s.passed / s.total) * 100),
                        backgroundColor: '#22c55e',
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom', labels: { color: '#fff' } } },
                    scales: {
                        x: { ticks: { color: '#8b8b9e' }, grid: { display: false } },
                        y: { ticks: { color: '#8b8b9e' }, grid: { color: 'rgba(139,139,158,0.1)' }, max: 100 }
                    }
                }
            });
        }
        
        function renderTable(results) {
            const tbody = document.getElementById('results-table');
            tbody.innerHTML = results.map(r => `
                <tr>
                    <td><strong>${r.test_id}</strong></td>
                    <td style="font-family: monospace; color: var(--text-secondary);">${r.model.split('/').pop()}</td>
                    <td>${r.metric_type}</td>
                    <td>${r.latency.toFixed(2)}s</td>
                    <td>
                        <div class="score-bar"><div class="score-bar-fill" style="width: ${r.score * 100}%"></div></div>
                        ${r.score.toFixed(2)}
                    </td>
                    <td><span class="badge ${r.passed ? 'pass' : r.verdict === 'ERROR' ? 'error' : 'fail'}">${r.verdict}</span></td>
                </tr>
            `).join('');
        }
        
        function toggleExportMenu() {
            document.getElementById('exportMenu').classList.toggle('show');
        }
        
        function exportAs(format) {
            const filename = 'report.json';
            window.open(`/api/reports/${filename}/export?format=${format}`, '_blank');
            toggleExportMenu();
        }
        
        async function runTests() {
            try {
                const response = await fetch('/api/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                
                const result = await response.json();
                alert('Tests started! Refresh in a few moments to see results.');
            } catch (error) {
                alert('Error starting tests: ' + error.message);
            }
        }
        
        function refreshData() {
            document.getElementById('loading').style.display = 'flex';
            document.getElementById('dashboard').style.display = 'none';
            document.getElementById('empty').style.display = 'none';
            loadData();
        }
        
        // Close export menu on click outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.export-dropdown')) {
                document.getElementById('exportMenu').classList.remove('show');
            }
        });
        
        // Initial load
        loadData();
    </script>
</body>
</html>
'''


if __name__ == "__main__":
    run_server()
