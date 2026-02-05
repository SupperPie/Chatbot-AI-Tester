# DeepEval Test Management System

A Streamlit-based application for managing and running automated tests against AI Agents (Bundle API, Airport Assistant, Skills API) using DeepEval.

## Features

*   **Test Case Management**: View, import, and manage test cases (Single-turn & Multi-turn).
*   **Automated Execution**: Run tests in the background (Async) without blocking the UI.
*   **Real-time Reporting**: View running job progress, success rates, and detailed logs.
*   **Thinking Process Tracking**: Capture and display the "Reasoning" process from supported APIs.
*   **Latency Monitoring**: Track response times for each API call.
*   **PDF Export**: Generate PDF reports for test runs.

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
```bash
nano .env
# Paste your keys -> Ctrl+O -> Enter -> Ctrl+X
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
