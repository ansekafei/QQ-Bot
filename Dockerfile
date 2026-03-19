FROM python:3.11-slim

WORKDIR /app

# 🌟 核心修复：一键将 Debian 官方源替换为清华源，彻底解决构建卡死问题
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources || true \
    && sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list || true \
    && apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 使用清华源加速下载依赖
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY . .

# 防止 Python 缓冲输出导致你看不到实时日志
ENV PYTHONUNBUFFERED=1

# 声明项目目录为安全目录，防止 Docker 挂载时触发 git 权限保护警告
RUN git config --global --add safe.directory /app

CMD ["python", "main.py"]