FROM python:3.11-slim

WORKDIR /app

# 先复制依赖文件，利用 Docker 缓存层
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制应用代码
COPY . .

# 将 .env.example 重命名为 .env 作为默认配置
RUN cp .env.example .env

# 端口通过环境变量配置
ENV STREAMLIT_PORT=54321

EXPOSE ${STREAMLIT_PORT}

# 使用 shell 形式以支持环境变量替换
CMD streamlit run streamlit_app.py --server.port=${STREAMLIT_PORT} --server.address=0.0.0.0
