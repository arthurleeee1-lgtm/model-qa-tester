# CanopyWave Model Tester

🚀 **专业的 API 自动化测试平台**，用于测试 CanopyWave 模型 API 的质量和性能。

## ✨ 功能特性

### 质量测试 (QA)

- ✅ 多种评估指标（精确匹配、语义相似度、BLEU、ROUGE）
- ✅ 自动生成报告（JSON/Markdown/纯文本表格）
- ✅ 多模型对比测试
- ✅ 交互式 React Dashboard 可视化

### 性能测试 (Performance)

- ⚡ 延迟统计（P50/P90/P95/P99）
- 📊 并发吞吐量测试
- 🔄 稳定性长时间测试
- ⏱️ TTFB（首字节时间）测试
- 🎯 SLO 验证（遵循 Google SRE 标准）

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入你的 API Key
export CANOPYWAVE_API_KEY="your-api-key-here"
```

### 3. 运行测试

#### QA 质量测试

```bash
# 运行所有质量测试
python -m src.runner --config tests/qa_tests.yaml

# 指定模型测试
python -m src.runner -m deepseek/deepseek-chat-v3.2

# 查看报告
open reports/index.html      # 交互式 React Dashboard
cat reports/report.txt        # 纯文本表格
```

#### 性能测试

```bash
# 基础性能测试（延迟 + 错误率）
python -m src.perf_cli -c tests/perf_tests.yaml

# 完整性能测试（全部指标）
python -m src.perf_cli --full -c tests/perf_tests.yaml

# 测试单个模型
python -m src.perf_cli --full -m deepseek/deepseek-chat-v3.2

# 测试所有模型
python -m src.perf_cli --full --all
```

### 4. Web Dashboard

```bash
# 启动服务
python -m uvicorn src.server:app --host 0.0.0.0 --port 8080

# 访问 http://localhost:8080
# - 查看历史报告
# - 在线运行测试
# - 导出数据（JSON/CSV）
```

---

## 📊 测试参数配置

### 统一配置文件

所有标准参数定义在 `config/test_config.yaml`:

```yaml
test_params:
  # 通用设置
  timeout_seconds: 120
  max_retries: 3

  # QA测试
  qa:
    default_model: "deepseek/deepseek-chat-v3.2"
    max_tokens: 1000
    temperature: 0.7

  # 性能测试
  perf:
    warmup_requests: 3 # 预热请求
    sample_requests: 20 # 延迟采样
    concurrent_requests: 5 # 并发数
    stability_requests: 30 # 稳定性测试
    ttfb_samples: 10 # TTFB采样

# SLO阈值（Google SRE标准）
slo:
  latency_p50_ms: 5000 # P50 < 5秒
  latency_p99_ms: 30000 # P99 < 30秒
  error_rate_percent: 1.0 # 错误率 < 1%
  availability_percent: 99.9 # 可用性 > 99.9%
  ttfb_p99_ms: 5000 # TTFB P99 < 5秒
  throughput_min_rps: 0.1 # 吞吐量 > 0.1/s
  stability_score_min: 80.0 # 稳定性 > 80分
```

### 自定义参数

#### 方法1：命令行覆盖

```bash
python -m src.perf_cli --full -m model-name \
  --samples 50 \
  --concurrent 10 \
  --stability-requests 100
```

#### 方法2：修改配置文件

编辑 `tests/perf_tests.yaml`:

```yaml
test_settings:
  sample_requests: 50 # 覆盖默认的20
```

---

## 📁 项目结构

```text
canopywave-model-tester/
├── config/
│   └── test_config.yaml      # 统一配置（标准参数）
├── src/
│   ├── config.py             # 配置管理
│   ├── invoker.py            # API调用
│   ├── metrics.py            # 评估指标
│   ├── runner.py             # QA测试运行器
│   ├── perf.py               # 性能测试核心
│   ├── perf_cli.py           # 性能测试CLI
│   ├── report.py             # 报告生成
│   └── server.py             # Web Dashboard
├── tests/
│   ├── qa_tests.yaml         # QA测试用例
│   └── perf_tests.yaml       # 性能测试配置
├── reports/                  # 生成的报告
│   ├── report.txt            # 纯文本表格
│   ├── index.html            # 交互式 React Dashboard (支持动态加载JSON)
│   ├── report.json           # JSON结构化
│   └── report.md             # Markdown
└── docs/
    └── CONFIGURATION.md      # 详细配置说明
```

---

## 🎯 评估指标

### QA 质量指标

| 指标           | 说明           | 适用场景           |
| -------------- | -------------- | ------------------ |
| `exact_match`  | 精确匹配       | 数学计算、固定答案 |
| `contains`     | 包含关键词     | 内容验证           |
| `contains_any` | 包含任一关键词 | 灵活匹配           |
| `regex_match`  | 正则匹配       | 格式验证           |
| `ss_score`     | 语义相似度     | 开放性回答         |
| `bleu`         | BLEU评分       | 翻译质量           |
| `rouge`        | ROUGE评分      | 摘要质量           |
| `composite`    | 综合评分       | 多维度评估         |

### 性能指标

| 指标       | 说明                               |
| ---------- | ---------------------------------- |
| **延迟**   | P50, P90, P95, P99, Min, Max, Mean |
| **错误率** | HTTP错误、超时、连接失败           |
| **可用性** | 成功请求比例                       |
| **吞吐量** | 并发请求数/秒                      |
| **稳定性** | 长时间运行的性能衰减               |
| **TTFB**   | 流式响应首字节时间                 |

---

## 📝 测试用例格式

### QA 测试示例

```yaml
tests:
  # 数学测试
  - id: math_simple
    prompt: "计算 1234 + 5678"
    metric: exact_match
    expected: "6912"

  # 创意生成
  - id: story_generation
    prompt: "写一个短故事"
    metric: contains_any
    expected: ["故事", "情节", "角色"]

  # 语义相似度
  - id: summary_article
    prompt: "总结这篇文章..."
    metric: ss_score
    reference: "文章主要讨论..."
    threshold: 0.7
```

### 性能测试配置

```yaml
# tests/perf_tests.yaml
test_settings:
  warmup_requests: 3
  sample_requests: 20
  timeout_seconds: 120

slo:
  latency_p50_ms: 5000
  latency_p99_ms: 30000
  error_rate_percent: 1.0

models:
  - zai/glm-5
  - deepseek/deepseek-chat-v3.2
```

---

## 📈 性能测试说明

### 基础测试 vs 完整测试

| 模式     | 参数     | 测试内容                             | 耗时           |
| -------- | -------- | ------------------------------------ | -------------- |
| **基础** | 默认     | 延迟 + 错误率 + 4项SLO               | ~1分钟/模型    |
| **完整** | `--full` | 基础 + 并发 + 稳定性 + TTFB + 7项SLO | ~5-10分钟/模型 |

### 使用建议

- **日常监控**: 基础测试即可
- **上线前评估**: 使用完整测试
- **性能调优**: 使用完整测试 + 自定义参数

```bash
# 快速验证（10个样本）
python -m src.perf_cli -m model-name --samples 10

# 标准测试（默认参数）
python -m src.perf_cli -c tests/perf_tests.yaml

# 深度测试（大样本 + 长稳定性）
python -m src.perf_cli --full --all \
  --samples 50 \
  --stability-requests 100
```

---

## 🔄 CI/CD 集成

项目包含 GitHub Actions 工作流，自动运行测试：

```yaml
# .github/workflows/test.yml
- name: Run QA Tests
  run: python -m src.runner --config tests/qa_tests.yaml

- name: Run Performance Tests
  run: python -m src.perf_cli -c tests/perf_tests.yaml
```

---

## 🛠️ 开发指南

### 添加新的评估指标

编辑 `src/metrics.py`:

```python
def evaluate_custom(response: str, expected: str) -> float:
    # 自定义评估逻辑
    return score
```

### 添加新模型

编辑 `src/config.py`:

```python
MODEL_ENDPOINTS = {
    "your/model-name": "https://api.example.com/v1/chat/completions",
}
```

---

## 📄 License

MIT License

---

## 🙋 常见问题

**Q: 虚拟环境中运行失败？**

```bash
# 确保激活虚拟环境
source venv/bin/activate
# 重新安装依赖
pip install -r requirements.txt
```

**Q: macOS 权限问题？**

```bash
# 在系统终端运行，不要在IDE内置终端
# 允许网络访问和文件写入
```

**Q: 如何修改 SLO 阈值？**

```bash
# 编辑 config/test_config.yaml
slo:
  latency_p50_ms: 3000  # 改为3秒
```

**Q: 报告在哪里？**

```bash
reports/
├── report.txt       # 纯文本表格（推荐）
├── index.html       # 交互式 React Dashboard (可加载不同的JSON结果)
└── report.json      # JSON数据
```
