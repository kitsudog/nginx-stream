# 安全隐患：默认 HTTPS 证书缺失导致 SNI 隐私泄露

## 1. 问题描述
当服务器配置了 HTTPS (Port 443) 监听，但 Nginx 配置中没有显式指定 `default_server` 时，Nginx 会默认使用加载的第一个 SSL 配置作为默认服务器。
如果攻击者将恶意域名（如 `random.com`）解析到本服务器 IP 并发起 HTTPS 请求，Nginx 会返回第一个站点的证书（例如 `your-domain.com`）。
这将导致：
1.  **源站 IP 暴露**：扫描器可以通过扫描全网 IP 的 443 端口获取证书中的域名，从而发现隐藏在高防 IP 后的真实源站 IP。
2.  **隐私泄露**：泄露了服务器上托管的业务域名。

## 2. 影响范围
所有使用 `start.py` 动态生成配置且未配置全局默认 SSL 证书的实例。

## 3. 修复方案
### 3.1 自动生成默认证书
在容器启动时 (`start.sh`)，检查 `/etc/nginx/certs/default.crt` 是否存在。如果不存在，使用 `openssl` 自动生成一个自签名的 "Snake Oil" 证书。
证书信息应尽量模糊，例如 `CN=localhost`, `O=Nginx Stream`.

### 3.2 配置 Nginx Default Server
修改模板 (`templates/http_default_server.jinja` 或直接修改 `http.jinja`)，添加一个监听 443 的 `default_server` 块：
```nginx
server {
    listen 80 default_server;
    listen 443 ssl default_server;
    server_name _;
    ssl_certificate /etc/nginx/certs/default.crt;
    ssl_certificate_key /etc/nginx/certs/default.key;
    return 444; # 或者 403
}
```

## 4. 验证方法
1.  启动容器，不挂载任何证书。
2.  使用 `openssl s_client -connect localhost:443 -servername random.com` 连接。
3.  验证返回的证书 Subject 是否为默认自签名证书（而非业务证书）。
4.  验证连接是否被拒绝 (444/403)。
