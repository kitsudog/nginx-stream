[![Github Action](https://github.com/kitsudog/nginx-stream/actions/workflows/main.yml/badge.svg)](https://github.com/kitsudog/nginx-stream/actions/workflows/main.yml)
[![Docker Image Size](https://img.shields.io/docker/image-size/kitsudo/nginx-stream?sort=semver)](https://hub.docker.com/r/kitsudo/nginx-stream "Click to view the image on Docker Hub")
[![Docker stars](https://img.shields.io/docker/stars/kitsudo/nginx-stream.svg)](https://hub.docker.com/r/kitsudo/nginx-stream 'DockerHub')
[![Docker pulls](https://img.shields.io/docker/pulls/kitsudo/nginx-stream.svg)](https://hub.docker.com/r/kitsudo/nginx-stream 'DockerHub')

# nginx-stream

这是一个基于 **Nginx + Python (Flask/Gevent)** 构建的高级网络代理与流处理网关。它的核心设计理念是**通过环境变量动态生成配置**，并结合 Python 应用作为"边车"（Sidecar）来处理 Nginx 无法单独完成的高级流量操作。

核心架构分为三个层次：**流量入口 (Nginx)** -> **控制逻辑 (Python Scripts)** -> **数据/扩展 (SSH/Storage)**。

## 核心功能

### 1. 多协议代理与转发 (L4/L7 Proxy)
*   **HTTP/HTTPS 反向代理**：支持通过 `LISTEN`、`FORWARD`、`PROXY` 等环境变量快速定义反向代理规则，自带 SSL 卸载能力。
*   **TCP/UDP 流代理**：通过 `BIND` 变量支持 L4 层的端口转发 (基于 Nginx Stream 模块)。
*   **重定向服务**：通过 `REDIRECT` 变量快速搭建域名或路径重定向服务。

### 2. 高级内容处理 (Content Modification)
当 Nginx 需要进行复杂的流量清洗时，会将请求转发给内部的 Python Flask 服务（默认端口 8000）。
*   **图片处理**：自动支持图片缩放与格式转换（JPEG/PNG 互转、Resize）。
*   **文本/Header 替换**：支持对响应内容、Header（如 `Set-Cookie`, `Location`）进行正则匹配和字符串替换，有效解决反向代理场景下的域名/路径不匹配问题。

### 3. 混合网络隧道 (Hybrid Tunneling)
内置完整的 SSH 隧道管理能力，通过 `tunnel.py` 和 `tunneld.py` 实现：
*   **Client 模式**：作为 SSH 客户端连接远程服务器，建立端口转发（Local/Remote Forwarding）。
*   **Server 模式**：动态启动 SSHD 进程接收隧道连接，作为跳板机使用。
*   **无缝集成**：隧道建立的端口可以直接被 Nginx 代理配置引用，实现跨网段的复杂流量转发。

### 4. 流量录制与分析 (Observability)
*   **全量录制**：支持通过 `tcpdump` 将流量录制为 `.pcap` 文件。
*   **深度解析**：内置 `pcaper.py` 解析器（基于 `dpkt`），可从 PCAP 文件中还原 HTTP 请求/响应。
*   **高级过滤**：支持通过正则匹配 Body、Header、URL 对录制流量进行筛选。
*   **数据导出**：解析结果支持导入 Elasticsearch 或 MongoDB，便于长期存储和分析。

## 设计思路

1.  **配置即代码 (Configuration as Environment Variables)**
    *   项目极度依赖环境变量。`start.py` 作为一个复杂的配置生成器，将简单的环境变量声明（如 `LISTEN="domain.com:80"`）自动翻译为复杂的 `nginx.conf` 和辅助脚本配置。
    *   这种设计非常适合容器化部署（Docker/K8s），无需挂载复杂的配置文件。

2.  **Sidecar 模式 (Nginx + Python)**
    *   **Nginx** 负责抗高并发及基础的路由、SSL 终结。
    *   **Python** 负责业务灵活性，处理 Nginx 配置难以实现的逻辑（如基于内容的修改、复杂的正则替换）。
    *   二者通过本地回环网络高效通信。

3.  **自包含工具链**
    *   集成了证书管理、SSH Key 生成、隧道维护、日志分析等工具，作为一个"网络瑞士军刀"式的 Docker 镜像，解决了部署复杂应用时的"网络胶水"需求。

## 简单使用示例

```bash
# 基本反向代理 + 百度转发
LISTEN=www.abc.com:www.baidu.com:80 FORWARD=www.baidu.com ./start.py

# 端口转发 (L4)
BIND=80:192.168.1.1:80 ./start.py

# 代理 OpenAI
PROXY=openai.com ./start.py
```
