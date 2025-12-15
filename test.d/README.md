# 测试脚本规范说明

本目录下的脚本用于 `nginx-stream` 容器的集成测试。
每个脚本都具有双重用途：既负责准备环境（Host 主机侧），也负责验证行为（Container 容器侧）。

## 脚本结构
脚本在逻辑上由 `cat << EOF` 块分隔为两个部分。

### 第一部分：主机环境准备 (Host Preparation)
脚本顶部直到第一个 `cat` 命令的 `EOF` 分隔符之前的所有内容，均由 `test.sh` 在 **Host (主机)** 机器上执行。
**主要目的**：生成 `.env-test` 文件，该文件定义了启动 Docker 容器时所需的环境变量（如 `LISTEN`, `PROXY` 等配置）。

**示例**：
```bash
cat << EOF > .env-test
LISTEN_1=example.com:backend:80
EOF
```

### 第二部分：容器内验证 (Container Verification)
`EOF` 块之后的所有内容，均由 `start.sh` 在 **Container (容器)** 内部（作为 `/test.sh`）执行。
**主要目的**：执行验证命令（如 `curl`, `openssl`, `grep`），确保 Nginx 按照预期工作。
**运行环境**：
- 工作目录：`/app`
- 状态：Nginx 已启动并加载了配置
- 可用工具：`curl`, `openssl`, `grep`, `jq` 等

**示例**：
```bash
set -xe
# 验证域名是否可正常访问
curl -sSf -H "Host: example.com" http://127.0.0.1 | grep "Welcome"
```

## 如何运行测试
请使用根目录下的 `test.sh` 脚本执行测试。支持通过关键字过滤运行特定的测试脚本。

```bash
# 运行所有测试
./test.sh

# 运行特定测试 (例如只运行 simple.sh)
./test.sh simple
```
