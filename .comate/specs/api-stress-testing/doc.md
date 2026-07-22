# API 压力测试功能设计文档

## 1. 需求概述

为现有的 AI Agent 测试平台增加接口压力测试功能，支持并发请求、性能指标采集、结果分析和可视化报告。

## 2. 功能场景

### 2.1 核心场景
- 用户在测试用例界面选择一个或多个测试用例
- 配置压力测试参数（并发数、总请求数、持续时间、压测模式等）
- 启动压力测试，系统并发执行 API 调用
- 实时显示压力测试进度和关键指标
- 测试完成后生成详细的性能分析报告

### 2.2 压测模式
- **固定并发模式**：保持固定数量的并发请求
- **递增并发模式**：并发数从低到高逐步增加
- **突发模式**：瞬间产生大量并发请求

## 3. 技术架构

### 3.1 架构设计
```
UI 层 (Streamlit)
    ↓
Service 层 (StressTestService)
    ↓
Engine 层 (StressTestEngine)
    ↓
API Client 层 (chat_client.py)
```

### 3.2 核心组件

#### 3.2.1 StressTestEngine (新增)
- 路径: `app/stress_test_engine.py`
- 职责：
  - 管理并发请求执行
  - 收集性能指标（延迟、吞吐量、成功率等）
  - 实时统计和聚合数据
  - 支持不同压测模式

#### 3.2.2 StressTestService (新增)
- 路径: `app/services/stress_test_service.py`
- 职责：
  - 压力测试历史记录的 CRUD 操作
  - 与数据库交互，保存和查询压测结果

#### 3.2.3 StressTestHistory Model (新增)
- 路径: `app/models/stress_test_history.py`
- 字段设计：
  ```python
  - id: str (主键, timestamp格式)
  - api_name: str (被测 API)
  - test_mode: str (压测模式: fixed/incremental/burst)
  - concurrency: int (并发数)
  - total_requests: int (总请求数)
  - duration: int (持续时间, 秒)
  - test_cases: List[str] (测试用例ID列表, JSONB)
  - status: str (running/completed/failed)
  - start_time: datetime
  - end_time: datetime
  - metrics: dict (性能指标, JSONB)
  - created_at: datetime
  ```

#### 3.2.4 StressTestResult Model (新增)
- 路径: 同 `app/models/stress_test_history.py`
- 字段设计：
  ```python
  - id: int (自增主键)
  - history_id: str (外键 -> StressTestHistory.id)
  - request_index: int (请求序号)
  - case_id: str (测试用例ID)
  - input: str (请求内容)
  - status: str (success/error/timeout)
  - latency: float (响应时间, 秒)
  - ttft: float (首字延迟, 秒)
  - timestamp: datetime (请求时间)
  - error_message: str (错误信息, 可选)
  - created_at: datetime
  ```

#### 3.2.5 UI 组件 (新增页面)
- 路径: `app/ui/stress_test.py`
- 界面设计：
  - 参数配置面板（API选择、并发数、请求数、压测模式等）
  - 测试用例选择器（复用现有组件）
  - 实时监控面板（显示 QPS、平均延迟、成功率等）
  - 结果报告（图表展示：延迟分布、时间序列、百分位数等）

#### 3.2.6 API Router (新增)
- 路径: `app/routers/stress_test.py`
- 端点：
  - `POST /api/stress-test/start` - 启动压力测试
  - `GET /api/stress-test/status/{test_id}` - 查询测试状态
  - `POST /api/stress-test/stop/{test_id}` - 停止测试
  - `GET /api/stress-test/history` - 获取历史记录列表
  - `GET /api/stress-test/report/{test_id}` - 获取详细报告

## 4. 实现细节

### 4.1 并发执行策略

使用 `concurrent.futures.ThreadPoolExecutor` 实现并发请求：

```python
import concurrent.futures
import time
from collections import defaultdict
from threading import Lock

class StressTestEngine:
    def __init__(self):
        self.metrics = {
            'total_requests': 0,
            'success_count': 0,
            'error_count': 0,
            'latencies': [],
            'ttfts': [],
            'timestamps': [],
            'errors': defaultdict(int)
        }
        self.lock = Lock()
    
    def execute_fixed_concurrency(self, cases, api_name, concurrency, total_requests):
        """固定并发数压测"""
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = []
            for i in range(total_requests):
                case = cases[i % len(cases)]  # 轮询选择测试用例
                future = executor.submit(self._execute_request, i, case, api_name)
                futures.append(future)
            
            # 等待所有请求完成
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                self._update_metrics(result)
    
    def _execute_request(self, index, case, api_name):
        """执行单个请求"""
        start_time = time.time()
        try:
            from chat_client import get_chat_response
            response = get_chat_response(case['input'], api_name=api_name)
            end_time = time.time()
            
            # 解析响应
            latency = end_time - start_time
            ttft = 0.0
            if isinstance(response, str):
                try:
                    import json
                    resp_data = json.loads(response)
                    ttft = resp_data.get('ttft', 0.0)
                except:
                    pass
            
            return {
                'index': index,
                'case_id': case['id'],
                'input': case['input'],
                'status': 'success',
                'latency': latency,
                'ttft': ttft,
                'timestamp': start_time
            }
        except Exception as e:
            return {
                'index': index,
                'case_id': case['id'],
                'input': case['input'],
                'status': 'error',
                'latency': time.time() - start_time,
                'ttft': 0.0,
                'timestamp': start_time,
                'error': str(e)
            }
```

### 4.2 性能指标计算

```python
import numpy as np

def calculate_metrics(results):
    """计算性能指标"""
    latencies = [r['latency'] for r in results if r['status'] == 'success']
    
    if not latencies:
        return {
            'success_rate': 0,
            'error_rate': 100,
            'avg_latency': 0,
            'p50_latency': 0,
            'p95_latency': 0,
            'p99_latency': 0,
            'max_latency': 0,
            'min_latency': 0,
            'qps': 0
        }
    
    success_count = len([r for r in results if r['status'] == 'success'])
    total_count = len(results)
    
    # 计算时间范围
    timestamps = [r['timestamp'] for r in results]
    duration = max(timestamps) - min(timestamps)
    qps = total_count / duration if duration > 0 else 0
    
    return {
        'success_rate': (success_count / total_count) * 100,
        'error_rate': ((total_count - success_count) / total_count) * 100,
        'avg_latency': np.mean(latencies),
        'p50_latency': np.percentile(latencies, 50),
        'p95_latency': np.percentile(latencies, 95),
        'p99_latency': np.percentile(latencies, 99),
        'max_latency': np.max(latencies),
        'min_latency': np.min(latencies),
        'qps': qps,
        'total_requests': total_count,
        'success_count': success_count,
        'error_count': total_count - success_count
    }
```

### 4.3 数据库集成

创建数据表：

```sql
-- 压力测试历史记录表
CREATE TABLE stress_test_history (
    id VARCHAR(20) PRIMARY KEY,
    api_name VARCHAR(100) NOT NULL,
    test_mode VARCHAR(20) NOT NULL,
    concurrency INTEGER NOT NULL,
    total_requests INTEGER NOT NULL,
    duration INTEGER,
    test_cases JSONB,
    status VARCHAR(20) NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    metrics JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 压力测试结果详情表
CREATE TABLE stress_test_result (
    id SERIAL PRIMARY KEY,
    history_id VARCHAR(20) REFERENCES stress_test_history(id) ON DELETE CASCADE,
    request_index INTEGER NOT NULL,
    case_id VARCHAR(50),
    input TEXT,
    status VARCHAR(20) NOT NULL,
    latency FLOAT NOT NULL,
    ttft FLOAT,
    timestamp TIMESTAMP NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_stress_test_result_history_id ON stress_test_result(history_id);
CREATE INDEX idx_stress_test_result_timestamp ON stress_test_result(timestamp);
```

### 4.4 UI 设计

Streamlit 页面布局：

```python
import streamlit as st
import plotly.graph_objects as go

def render_stress_test_page():
    st.title("🚀 接口压力测试")
    
    # 配置面板
    with st.expander("📋 测试配置", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            api_name = st.selectbox("选择 API", get_api_list())
        with col2:
            test_mode = st.selectbox("压测模式", ["固定并发", "递增并发", "突发模式"])
        with col3:
            concurrency = st.number_input("并发数", min_value=1, max_value=500, value=10)
        
        col4, col5 = st.columns(2)
        with col4:
            total_requests = st.number_input("总请求数", min_value=1, value=100)
        with col5:
            duration = st.number_input("持续时间(秒)", min_value=0, value=0, 
                                      help="0 表示不限制时间，以总请求数为准")
    
    # 测试用例选择
    with st.expander("📝 选择测试用例", expanded=True):
        selected_cases = render_case_selector()
    
    # 启动按钮
    if st.button("🚀 启动压力测试", type="primary", disabled=len(selected_cases) == 0):
        test_id = start_stress_test(api_name, test_mode, concurrency, 
                                     total_requests, duration, selected_cases)
        st.session_state.current_stress_test = test_id
        st.rerun()
    
    # 实时监控面板
    if 'current_stress_test' in st.session_state:
        render_real_time_monitor(st.session_state.current_stress_test)
    
    # 历史记录
    st.subheader("📊 历史记录")
    render_history_list()
```

### 4.5 实时监控实现

```python
import streamlit as st
import time

def render_real_time_monitor(test_id):
    """实时监控面板"""
    st.subheader("📈 实时监控")
    
    # 创建占位符
    metrics_placeholder = st.empty()
    progress_placeholder = st.empty()
    chart_placeholder = st.empty()
    
    while True:
        # 获取最新状态
        status = get_stress_test_status(test_id)
        
        if status['status'] != 'running':
            break
        
        # 更新指标
        with metrics_placeholder.container():
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("QPS", f"{status['qps']:.2f}")
            col2.metric("平均延迟", f"{status['avg_latency']:.2f}s")
            col3.metric("成功率", f"{status['success_rate']:.1f}%")
            col4.metric("进度", f"{status['completed']}/{status['total']}")
        
        # 更新进度条
        progress = status['completed'] / status['total']
        progress_placeholder.progress(progress)
        
        # 更新图表
        with chart_placeholder.container():
            render_latency_chart(status['latencies'])
        
        time.sleep(1)  # 每秒刷新
    
    st.success("✅ 压力测试完成！")
    render_final_report(test_id)
```

## 5. 数据流路径

### 5.1 启动压力测试
```
UI (stress_test.py) 
  → API Router (/api/stress-test/start)
    → StressTestService.create_test()
      → JobManager.run_stress_test_job()
        → StressTestEngine.execute()
          → chat_client.get_chat_response() (并发调用)
          → 收集结果并保存到 DB
```

### 5.2 实时监控
```
UI (定时刷新)
  → API Router (/api/stress-test/status/{test_id})
    → StressTestService.get_test_status()
      → 查询 DB 获取最新指标
      → 返回聚合数据
```

## 6. 异常处理

### 6.1 请求超时
- 设置单个请求超时时间（默认 60 秒）
- 超时请求计入失败统计
- 记录超时错误信息

### 6.2 API 限流
- 检测连续失败率
- 如果失败率超过阈值（如 50%），自动暂停测试并提示用户

### 6.3 资源限制
- 限制最大并发数（建议 ≤ 500）
- 限制单次测试最大请求数（建议 ≤ 10000）

## 7. 预期结果

### 7.1 功能完整性
- ✅ 支持三种压测模式
- ✅ 实时显示 QPS、延迟、成功率等关键指标
- ✅ 生成详细的性能分析报告
- ✅ 支持历史记录查询和对比

### 7.2 性能指标
- ✅ P50、P95、P99 延迟统计
- ✅ 延迟分布直方图
- ✅ 时间序列图（QPS、延迟趋势）
- ✅ 错误类型统计

### 7.3 用户体验
- ✅ 配置简单直观
- ✅ 实时监控不阻塞 UI
- ✅ 可中途停止测试
- ✅ 报告可导出为 PDF

## 8. 技术亮点

1. **并发控制**：使用线程池精确控制并发数
2. **实时计算**：边执行边统计，无需等待全部完成
3. **数据库优化**：使用 JSONB 存储复杂指标，提高查询效率
4. **可视化**：使用 Plotly 生成交互式图表
5. **模块化设计**：复用现有的 JobManager 和 chat_client，减少重复代码

## 9. 扩展性考虑

- **分布式压测**：未来可扩展为多节点分布式压测
- **自定义指标**：支持用户自定义性能指标
- **智能压测**：根据系统响应自动调整并发数
- **压测对比**：支持多次压测结果对比分析
