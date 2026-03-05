# CanopyWave Model Tester - Configuration Guide

## 📁 Configuration Files

### 1. Unified Configuration

**Location**: `config/test_config.yaml`

包含所有标准测试参数和 SLO 阈值：

```yaml
test_params:
  timeout_seconds: 120
  qa:
    default_model: "deepseek/deepseek-chat-v3.2"
  perf:
    warmup_requests: 3
    sample_requests: 20
    concurrent_requests: 5

slo:
  latency_p50_ms: 5000
  latency_p99_ms: 30000
  error_rate_percent: 1.0
  availability_percent: 99.9
```

### 2. Test-Specific Configurations

#### QA Tests

**Location**: `tests/qa_tests.yaml`

定义质量测试用例，使用统一配置中的默认参数。

#### Performance Tests

**Location**: `tests/perf_tests.yaml`

定义性能测试参数，可覆盖统一配置中的默认值。

---

## 🎯 Standard Test Parameters

| 参数类别     | 参数名                | 默认值             | 说明             |
| ------------ | --------------------- | ------------------ | ---------------- |
| **基础设置** | `timeout_seconds`     | 120                | 请求超时时间     |
|              | `max_retries`         | 3                  | 失败重试次数     |
| **QA测试**   | `default_model`       | deepseek-chat-v3.2 | 默认测试模型     |
|              | `max_tokens`          | 1000               | 最大生成token数  |
|              | `temperature`         | 0.7                | 生成温度         |
| **性能测试** | `warmup_requests`     | 3                  | 预热请求数       |
|              | `sample_requests`     | 20                 | 采样请求数       |
|              | `concurrent_requests` | 5                  | 并发请求数       |
|              | `stability_requests`  | 30                 | 稳定性测试请求数 |
|              | `ttfb_samples`        | 10                 | TTFB采样数       |

---

## 📊 SLO (Service Level Objectives)

| SLO 指标       | 目标值      | 说明             |
| -------------- | ----------- | ---------------- |
| **延迟 P50**   | < 5000 ms   | 50%请求响应时间  |
| **延迟 P99**   | < 30000 ms  | 99%请求响应时间  |
| **错误率**     | < 1.0%      | 失败请求比例     |
| **可用性**     | > 99.9%     | 服务可用时间     |
| **TTFB P99**   | < 5000 ms   | 首字节响应时间   |
| **吞吐量**     | > 0.1 req/s | 最小请求速率     |
| **稳定性分数** | > 80/100    | 长时间运行稳定性 |

---

## 🚀 Usage

### 使用默认参数

```bash
# QA测试 - 自动使用默认配置
python -m src.runner --config tests/qa_tests.yaml

# 性能测试 - 自动使用默认配置
python -m src.perf_cli -c tests/perf_tests.yaml
```

### 覆盖默认参数

```bash
# 性能测试 - 自定义参数
python -m src.perf_cli -m deepseek/deepseek-chat-v3.2 \
  --samples 50 \
  --concurrent 10 \
  --stability-requests 100
```

---

## 🔧 Customization

### 修改默认参数

编辑 `config/test_config.yaml`:

```yaml
test_params:
  perf:
    sample_requests: 50 # 从 20 增加到 50
```

### 测试特定覆盖

编辑 `tests/perf_tests.yaml`:

```yaml
test_settings:
  sample_requests: 30 # 仅此测试使用 30
```

---

## 📦 Files Overview

```
config/
└── test_config.yaml      # 统一配置（标准参数）

tests/
├── qa_tests.yaml         # QA测试定义
└── perf_tests.yaml       # 性能测试配置

reports/
├── report.txt            # 纯文本表格报告
├── index.html            # 交互式 React Dashboard
├── report.json           # JSON结构化报告
└── report.md             # Markdown报告
```
