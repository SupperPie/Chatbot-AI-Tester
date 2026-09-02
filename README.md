# DeepEval Test Management System

A Streamlit-based application for managing and running automated tests against AI Agents (Bundle API, Airport Assistant, Skills API) using DeepEval.

## Features

*   **Test Case Management**: View, import, and manage test cases (Single-turn & Multi-turn).
*   **Automated Execution**: Run tests in the background (Async) without blocking the UI.
*   **Real-time Reporting**: View running job progress, success rates, and detailed logs.
*   **Thinking Process Tracking**: Capture and display the "Reasoning" process from supported APIs.
*   **Latency Monitoring**: Track response times for each API call.
*   **PDF Export**: Generate PDF reports for test runs.

## Changelog

### v3.7

*   **Description 列**: 测试用例表新增 Description 列，用于描述用例目的（对应产品需求中的验收标准 AC）。支持在表格中直接编辑、CSV/JSON 导入、AI 自动生成。
*   **目录树子节点用例为空修复**: 修复 `sac.tree(return_index=True)` 扁平索引解析逻辑错误，点击展开/折叠箭头后选中节点不再跳错。
*   **DB priority 列缺失修复**: 修复 `test_cases` 表缺失 `priority` 列导致 ORM 查询失败、回退到 JSON 文件（category_id 全为 root）的严重 bug。
*   **关键词搜索修复**: `str.contains` 加 `regex=False` 避免特殊字符（`?`、`(` 等）报错；搜索范围增加 `id` 列；筛选条件变化时自动重置到第一页。
*   **Management 布局优化**: Move / Priority / Assert / Delete 按钮移到 API Endpoint 下方独立一行。

### v3.6

*   **Report 复选框/重跑修复**: 报告页选择与重跑逻辑修正。
*   **Stop Job 评分中断**: 停止任务时正确中断评分流程。
*   **Thinking/Result 拆分**: 将 `is_thinking` 拆分为 `thinking` 和 `result` 两列独立展示。

## 1. Preparation for Git Upload

Before uploading your code to Git, ensure you have configured the `.gitignore` file to exclude sensitive information and unnecessary files.

A `.gitignore` file has been created for you, which excludes:
*   `.env` (Environment variables/Keys)
*   `__pycache__/`
*   `.deepeval/`
*   Virtual environment folders (`venv/`, `env/`)

**Steps to Upload:**

```bash
# 1. Initialize Git (if not already done)
git init

# 2. Add files
git add .

# 3. Commit
git commit -m "Initial commit of DeepEval Test System"

# 4. Add Remote (Update URL to your repo)
git remote add origin <your-git-repo-url>

# 5. Push
git push -u origin master
```

## 2. Server Deployment Guide

You asked whether to use **Docker** or deploy directly. 

**Recommendation: Use Docker.**
*   **Why?** Docker ensures the environment (Python version, dependencies, system libraries) is exactly the same on your server as it is on your local machine. It avoids "it works on my machine" issues.

### Option A: Docker Deployment (Recommended)

1.  **Build the Image**:
    ```bash
    docker build -t deepeval-app .
    ```

2.  **Run the Container**:
    ```bash
    docker run -d -p 8501:8501 --name deepeval-container deepeval-app
    ```
    *   `-d`: Run in background (detached mode).
    *   `-p 8501:8501`: Map port 8501 of the container to port 8501 on the server.

3.  **Access**:
    Open `http://<your-server-ip>:8501` in your browser.

### Option B: Direct Deployment (Manual)

If you cannot use Docker, follow these steps on your server:

1.  **Install Python 3.9+**.
2.  **Clone the Repo**:
    ```bash
    git clone <your-git-repo-url>
    cd <repo-folder>
    ```
3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Run Application**:
    ```bash
    streamlit run streamlit_app.py --server.port 8501
    ```
    *   Use `nohup` or `systemd` to keep it running in the background.

## Configuration

*   **API Configuration**: Edit `data/api_config.json` to manage API endpoints.
*   **Environment Variables**: Create a `.env` file for API keys if needed (e.g., `OPENAI_API_KEY`).

## 3. Security: Deploying Secrets (API Keys) Safely

If you follow security best practices and **exclude** `.env` from Git, here is how you deploy it to the server:

### Method A: Manual File Copy (SCP)
After cloning the code on the server, copy your local `.env` file directly to the server using a secure command:

```bash
# Run this on your LOCAL machine
scp .env user@<your-server-ip>:/path/to/your/repo/.env
```
Or simply creating it on server:
# Paste your keys -> Ctrl+O -> Enter -> Ctrl+X
```

### 6. Managing the Process (Start/Stop)

**Start in Background:**
```bash
nohup streamlit run streamlit_app.py --server.port 8501 > app.log 2>&1 &
```

**View Logs:**
```bash
tail -f app.log
```

**Stop the Application:**
1. Find the Process ID (PID):
   ```bash
   ps -ef | grep streamlit
   ```
2. Kill the process (replace `12345` with the actual PID):
   ```bash
   kill 12345
   ```

### Method B: Docker Volume Mount (Recommended)
If running with Docker, you don't need to rebuild the image to add keys. You can "mount" the file when running the container.

1.  Create `.env` file on the server (as per Method A).
2.  Run Docker with `-v` flag:
    ```bash
    docker run -d -p 8501:8501 \
      -v $(pwd)/.env:/app/.env \
      --name deepeval-app deepeval-app
    ```
    This maps the server's `.env` to `/app/.env` inside the container.
