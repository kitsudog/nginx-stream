# WebSocket Header 继承问题修复计划

## TL;DR

> **问题**: `feat: 新架构` 提交重构模板时，在 location 中重复定义了 `proxy_set_header Upgrade/Connection`，导致 Nginx 继承机制破坏，丢失了 http 块中定义的 `X-Real-IP`, `X-Forwarded-For` 等关键 headers
> 
> **解决方案**: 创建统一的 `templates/proxy_headers.conf`，将标准 headers 抽离，通过 jinja 模板自动 include 到所有 location，移除重复的 headers 定义
> 
> **Deliverables**:
> - 新增：`templates/proxy_headers.conf`
> - 修改：`templates/basic_location_header.jinja`
> - 修改：`templates/basic_ex_location_root.jinja`
> - 修改：`templates/http_default_forward.jinja`
> 
> **Estimated Effort**: Short (1-2 小时)
> **Parallel Execution**: NO - 必须按顺序修改
> **Critical Path**: 创建 proxy_headers.conf → 修改 basic_location_header.jinja → 修改 basic_ex_location_root.jinja → 测试验证

---

## Context

### 原始问题
用户发现 WebSocket 配置存在问题，经分析发现根本原因是 **Nginx header 继承机制被破坏**。

### 问题根源
**Commit**: `0275f6f` (feat: 新架构)

该提交重构了模板系统，但在以下文件中重复定义了 `proxy_set_header`：

1. **templates/basic_location_header.jinja:3-4**
   ```nginx
   proxy_set_header            Upgrade                             $http_upgrade;
   proxy_set_header            Connection                          $proxy_connection;
   ```

2. **templates/basic_ex_location_root.jinja:4-5**
   ```nginx
   proxy_set_header        Upgrade             $http_upgrade;
   proxy_set_header        Connection          $proxy_connection;
   ```

3. **templates/http_default_forward.jinja:22-23**
   ```nginx
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection $proxy_connection;
   ```

### Nginx 继承规则
> 如果在 location 块中定义了**任意一个** `proxy_set_header`，则 http/server 块中定义的**所有** `proxy_set_header` 都不会继承到该 location

### 受影响的 Headers（当前丢失）
- ❌ `X-Real-IP` - 真实客户端 IP
- ❌ `X-Forwarded-For` - 代理链信息
- ❌ `X-Forwarded-Proto` - 协议信息
- ❌ `X-Forwarded-Ssl` - SSL 状态
- ❌ `X-Forwarded-Port` - 端口信息
- ❌ `Proxy ""` - 防止代理头混淆

### 受影响的服务
根据生成的 `nginx.conf`：
- `www.test.com` (EX Gateway)
- `www.test2.com` (EX Gateway + TLS)
- `echo-image.com` (EX Gateway)
- `echo.com` / `echo2.com` / `echo3.com` / `echo4.com`
- `jwt.com`
- `qcloud.com`
- 等所有使用 LISTEN/FORWARD 配置的服务

---

## Metis Review 发现的关键问题

### 1. Host Header 不能全局化
`basic_location_header.jinja` 中：
```nginx
proxy_set_header            Host                                "{{ location.proxy_host }}";
```

使用 `{{ location.proxy_host }}` 是**动态的**（每个 location 不同），不能放入全局配置文件。

### 2. X-FROM Header 是 Location 特有
```nginx
proxy_set_header            X-FROM                              "{{ location.listen_host }}";
```

这也是每个 location 不同的，必须保留在模板中。

### 3. https 位置的 X-Forwarded-Proto 覆盖
`basic_location_https.jinja:1` 显式设置：
```nginx
proxy_set_header                X-Forwarded-Proto https;
```

这在 include 之后定义，会**正确覆盖** include 中的变量版本。

### 4. 变量依赖
`proxy_headers.conf` 依赖 `default_map.conf` 中定义的变量：
- `$proxy_connection`
- `$proxy_x_forwarded_proto`
- `$proxy_x_forwarded_ssl`
- `$proxy_x_forwarded_port`

**Include 顺序很重要！**

---

## Work Objectives

### Core Objective
修复 Nginx header 继承机制，确保所有 location 都能正确传递 `X-Real-IP`, `X-Forwarded-For` 等 headers，同时保持 WebSocket 支持。

### Concrete Deliverables
1. `templates/proxy_headers.conf` - 包含所有标准 headers（除了 Host 和 X-FROM）
2. 修改 `templates/basic_location_header.jinja` - include proxy_headers.conf，移除重复定义
3. 修改 `templates/basic_ex_location_root.jinja` - include proxy_headers.conf，移除重复定义
4. 修改 `templates/http_default_forward.jinja` - include proxy_headers.conf，移除重复定义

### Definition of Done
- [ ] 所有 location 都能正确传递 X-Real-IP, X-Forwarded-For 等 headers
- [ ] WebSocket 连接正常工作（Upgrade/Connection headers 正确）
- [ ] Host header 仍使用 location.proxy_host（不是 $http_host）
- [ ] X-FROM header 仍包含 location.listen_host
- [ ] nginx -t 通过，无警告
- [ ] 测试脚本全部通过

### Must Have
- 保持向后兼容，不破坏现有配置
- Host header 使用 proxy_host 变量（不是 http_host）
- X-FROM header 继续传递
- WebSocket 正常工作

### Must NOT Have (Guardrails)
- 不要修改 headers 的语义（只改组织方式）
- 不要删除任何现有功能
- 不要改变 Host header 的值（必须用 proxy_host）
- 不要在 include 文件中包含 Host 或 X-FROM

---

## Verification Strategy

### Test Infrastructure
- 现有测试：`./test.sh`
- 可以运行 nginx -t 进行配置语法检查
- 可以访问 http://echo.com/headers 查看 headers

### Agent-Executed QA Scenarios (MANDATORY)

#### Scenario 1: 验证标准 Headers 存在
```
Scenario: Verify X-Forwarded headers present
  Tool: Bash (curl)
  Preconditions: nginx 已启动，echo.com 配置存在
  Steps:
    1. curl -s http://echo.com/headers
    2. 解析响应 JSON，检查 headers 字段
    3. Assert: X-Real-IP 存在且不为空
    4. Assert: X-Forwarded-For 存在
    5. Assert: X-Forwarded-Proto 存在
    6. Assert: X-Forwarded-Port 存在
  Expected Result: 所有 X-Forwarded-* headers 都存在于响应中
  Failure Indicators: 任意 header 缺失
  Evidence: 保存 curl 输出到 .sisyphus/evidence/task-1-headers.json
```

#### Scenario 2: 验证 WebSocket Headers
```
Scenario: WebSocket upgrade headers work
  Tool: Bash (curl)
  Preconditions: nginx 已启动
  Steps:
    1. curl -s -H "Upgrade: websocket" -H "Connection: Upgrade" http://echo.com/headers
    2. 解析响应，检查 headers.Upgrade 字段
    3. Assert: Upgrade = "websocket"
    4. Assert: Connection = "upgrade"
  Expected Result: WebSocket headers 正确传递到后端
  Failure Indicators: Upgrade/Connection headers 不正确
  Evidence: 保存输出到 .sisyphus/evidence/task-2-websocket.json
```

#### Scenario 3: 验证 Host Header 使用 proxy_host
```
Scenario: Host header uses proxy_host not original host
  Tool: Bash (curl)
  Preconditions: echo.com 转发到 httpbin.org
  Steps:
    1. curl -s http://echo.com/headers
    2. 检查 headers.Host 字段
    3. Assert: Host 包含 "httpbin.org"（不是 "echo.com"）
  Expected Result: Host header 是上游服务器地址
  Failure Indicators: Host 是原始请求域名
  Evidence: 保存输出到 .sisyphus/evidence/task-3-host.json
```

#### Scenario 4: 验证 X-FROM Header 存在
```
Scenario: X-FROM header contains listen_host
  Tool: Bash (curl)
  Preconditions: nginx 已启动
  Steps:
    1. curl -s http://echo.com/headers
    2. 检查 headers.X-FROM 字段
    3. Assert: X-FROM = "echo.com"
  Expected Result: X-FROM header 显示监听域名
  Failure Indicators: X-FROM 缺失或不正确
  Evidence: 保存输出到 .sisyphus/evidence/task-4-xfrom.json
```

#### Scenario 5: Nginx 配置测试
```
Scenario: Nginx configuration is valid
  Tool: Bash
  Preconditions: nginx 已安装
  Steps:
    1. nginx -t 2>&1
    2. Assert: 输出包含 "syntax is ok"
    3. Assert: 输出包含 "test is successful"
    4. Assert: 输出不包含 "duplicate" 或 "redefine"
  Expected Result: 配置语法正确，无重复定义警告
  Failure Indicators: 语法错误或重复定义警告
  Evidence: 保存输出到 .sisyphus/evidence/task-5-nginx-test.txt
```

#### Scenario 6: 完整测试套件
```
Scenario: Full test suite passes
  Tool: Bash
  Preconditions: 所有服务已启动
  Steps:
    1. cd /Users/luozhangming/Documents/workspace/_daveluo/nginx-stream
    2. ./test.sh
    3. Assert: 退出码为 0
  Expected Result: 所有测试通过
  Failure Indicators: 任意测试失败
  Evidence: 保存完整输出到 .sisyphus/evidence/task-6-test-suite.txt
```

---

## Execution Strategy

### 执行顺序（必须串行）

```
Wave 1:
└── Task 1: 创建 proxy_headers.conf 模板
    └── 依赖: 无
    └── 阻塞: Task 2, 3, 4

Wave 2:
├── Task 2: 修改 basic_location_header.jinja
│   └── 依赖: Task 1
│   └── 阻塞: 无
├── Task 3: 修改 basic_ex_location_root.jinja
│   └── 依赖: Task 1
│   └── 阻塞: 无
└── Task 4: 修改 http_default_forward.jinja
    └── 依赖: Task 1
    └── 阻塞: 无

Wave 3:
└── Task 5: 测试验证
    └── 依赖: Task 2, 3, 4
    └── 阻塞: 无 (Final)
```

### 回滚策略

如果出现问题，回滚命令：
```bash
# 恢复原始模板
git checkout HEAD -- templates/basic_location_header.jinja \
    templates/basic_ex_location_root.jinja \
    templates/http_default_forward.jinja

# 删除新增文件
rm -f templates/proxy_headers.conf

# 重新生成配置并测试
./start.py
nginx -t
```

---

## TODOs

- [ ] **1. 创建 proxy_headers.conf 模板**

  **What to do**:
  - 在 `templates/` 目录下创建 `proxy_headers.conf`
  - 包含所有标准 headers（不包括 Host 和 X-FROM）
  - 对齐格式与现有模板一致

  **File content**:
  ```nginx
  # Standard proxy headers (included in all locations)
  # Note: Host and X-FROM are location-specific and defined separately
  proxy_set_header            Upgrade                             $http_upgrade;
  proxy_set_header            Connection                          $proxy_connection;
  proxy_set_header            X-Real-IP                           $remote_addr;
  proxy_set_header            X-Forwarded-For                     $proxy_add_x_forwarded_for;
  proxy_set_header            X-Forwarded-Proto                   $proxy_x_forwarded_proto;
  proxy_set_header            X-Forwarded-Ssl                     $proxy_x_forwarded_ssl;
  proxy_set_header            X-Forwarded-Port                    $proxy_x_forwarded_port;
  proxy_set_header            Proxy                               "";
  ```

  **Must NOT do**:
  - 不要包含 Host header（它使用 location.proxy_host 变量）
  - 不要包含 X-FROM header（它是 location 特有的）
  - 不要修改 headers 的顺序或值（只调整格式）

  **Recommended Agent Profile**:
  - **Category**: `quick` - 这是一个简单的文件创建任务
  - **Skills**: 无特殊技能要求
  - **Reason**: 只需要按照格式要求创建静态配置文件

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 2, 3, 4
  - **Blocked By**: None

  **References**:
  - `templates/default_proxy.conf:10-18` - 当前 http 块中的 headers 定义（参考内容）
  - `templates/basic_location_header.jinja` - 当前 location headers（参考格式对齐）
  - `templates/default_map.conf` - 确认变量名正确性

  **Acceptance Criteria**:
  - [ ] 文件创建于 `templates/proxy_headers.conf`
  - [ ] 包含 8 个标准 headers（见上方内容）
  - [ ] 不包含 Host 和 X-FROM
  - [ ] 格式对齐（参考 basic_location_header.jinja 的缩进）
  - [ ] nginx -t 通过（需等 Task 2-4 完成后测试）

  **Commit**: YES
  - Message: `refactor(templates): add proxy_headers.conf for centralized header management`
  - Files: `templates/proxy_headers.conf`
  - Pre-commit: 无

- [ ] **2. 修改 basic_location_header.jinja**

  **What to do**:
  - 在第 1 行后添加 `{% include 'proxy_headers.conf' %}`
  - 删除第 3-4 行（重复的 Upgrade/Connection）
  - 保留其他 headers（Host, X-FROM 等）

  **Original file** (前 8 行):
  ```nginx
  proxy_ssl_server_name       on;
  proxy_ssl_name              {{ location.proxy_host }};
  proxy_set_header            Upgrade                             $http_upgrade;
  proxy_set_header            Connection                          $proxy_connection;
  add_header                  FROM                                nginx-stream always;
  proxy_set_header            X-FROM                              "{{ location.listen_host }}";
  proxy_set_header            Host                                "{{ location.proxy_host }}";
  set                         $dest_host                          "{{ location.host }}";
  ```

  **New file** (修改后):
  ```nginx
  {% include 'proxy_headers.conf' %}
  proxy_ssl_server_name       on;
  proxy_ssl_name              {{ location.proxy_host }};
  add_header                  FROM                                nginx-stream always;
  proxy_set_header            X-FROM                              "{{ location.listen_host }}";
  proxy_set_header            Host                                "{{ location.proxy_host }}";
  set                         $dest_host                          "{{ location.host }}";
  ```

  **Must NOT do**:
  - 不要删除 Host header
  - 不要删除 X-FROM header
  - 不要删除 add_header FROM
  - 不要修改 proxy_ssl_server_name

  **Recommended Agent Profile**:
  - **Category**: `quick` - 简单的模板编辑
  - **Skills**: 无
  - **Reason**: 只需要 include 和删除两行

  **Parallelization**:
  - **Can Run In Parallel**: YES (after Task 1)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 5
  - **Blocked By**: Task 1

  **References**:
  - `templates/proxy_headers.conf` - 刚创建的文件
  - `templates/basic_location_header.jinja` - 当前文件

  **Acceptance Criteria**:
  - [ ] 包含 `{% include 'proxy_headers.conf' %}`
  - [ ] 已删除 Upgrade 和 Connection 的定义
  - [ ] Host header 仍然存在
  - [ ] X-FROM header 仍然存在
  - [ ] 格式对齐正确

  **Agent-Executed QA**:
  ```bash
  # 生成配置后验证
  ./start.py
  grep -A 20 "CONFIG LISTEN_1" nginx.conf | head -25
  # 应该看到 include 语句，不应该看到重复的 Upgrade/Connection
  ```

  **Commit**: YES (groups with Task 3, 4)
  - Message: `refactor(templates): include proxy_headers.conf in location templates`
  - Files: `templates/basic_location_header.jinja`

- [ ] **3. 修改 basic_ex_location_root.jinja**

  **What to do**:
  - 在第 1 行前添加 `{% include 'proxy_headers.conf' %}`
  - 删除第 4-5 行（重复的 Upgrade/Connection）
  - 保留 Host header

  **Original file**:
  ```nginx
  set                     $dest_host          "#internal-server#";
  set                     $full_url           "http://127.0.0.1:8000/";
  proxy_set_header        Host ${http_host};
  proxy_set_header        Upgrade             $http_upgrade;
  proxy_set_header        Connection          $proxy_connection;
  proxy_ssl_server_name   on;
  proxy_pass              http://127.0.0.1:8000/;
  proxy_redirect          default;
  ```

  **New file**:
  ```nginx
  {% include 'proxy_headers.conf' %}
  set                     $dest_host          "#internal-server#";
  set                     $full_url           "http://127.0.0.1:8000/";
  proxy_set_header        Host ${http_host};
  proxy_ssl_server_name   on;
  proxy_pass              http://127.0.0.1:8000/;
  proxy_redirect          default;
  ```

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: 无

  **Parallelization**:
  - **Can Run In Parallel**: YES (after Task 1)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 5
  - **Blocked By**: Task 1

  **Acceptance Criteria**:
  - [ ] 包含 include 语句
  - [ ] 已删除 Upgrade 和 Connection 的定义
  - [ ] Host header 仍然存在（注意这里用的是 `${http_host}` 不是模板变量）

  **Commit**: YES (groups with Task 2, 4)
  - Message: `refactor(templates): include proxy_headers.conf in ex_location_root`
  - Files: `templates/basic_ex_location_root.jinja`

- [ ] **4. 修改 http_default_forward.jinja**

  **What to do**:
  - 找到 location 块中的 Upgrade/Connection 定义
  - 替换为 include 语句

  **需要查看的内容**:
  当前 `templates/http_default_forward.jinja` 第 22-23 行：
  ```nginx
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection $proxy_connection;
  ```

  **修改后**:
  ```nginx
  {% include 'proxy_headers.conf' %}
  ```

  **注意**: 需要确认这个文件是否还有其他 headers 需要保留

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: 无

  **Parallelization**:
  - **Can Run In Parallel**: YES (after Task 1)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 5
  - **Blocked By**: Task 1

  **Acceptance Criteria**:
  - [ ] 使用 include 替代直接的 Upgrade/Connection 定义
  - [ ] 确保其他 headers 不会丢失

  **Commit**: YES (groups with Task 2, 3)
  - Message: `refactor(templates): include proxy_headers.conf in default_forward`
  - Files: `templates/http_default_forward.jinja`

- [ ] **5. 测试验证**

  **What to do**:
  1. 运行 `./start.py` 重新生成 nginx.conf
  2. 运行 `nginx -t` 验证配置语法
  3. 运行测试脚本验证 headers
  4. 检查生成的 nginx.conf 中没有重复定义

  **测试步骤**:
  ```bash
  # 1. 重新生成配置
  ./start.py
  
  # 2. 语法检查
  nginx -t
  
  # 3. 检查生成的配置文件
  grep -B 2 -A 10 "proxy_set_header.*Upgrade" nginx.conf
  # 应该只看到 include 文件中的定义，不应该在 location 中重复
  
  # 4. 启动服务测试
  # ... 启动 nginx ...
  
  # 5. 验证 headers
  curl -s http://echo.com/headers | jq '.headers | keys'
  # 应该包含: X-Real-IP, X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Port
  
  # 6. 运行完整测试
  ./test.sh
  ```

  **Must NOT do**:
  - 不要跳过 nginx -t 检查
  - 不要忽略任何警告

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: 无（基本 bash 操作）

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (Final)
  - **Blocks**: None
  - **Blocked By**: Task 2, 3, 4

  **References**:
  - `nginx.conf` - 生成的配置文件
  - `./test.sh` - 测试脚本

  **Acceptance Criteria**:
  - [ ] `./start.py` 成功运行，无错误
  - [ ] `nginx -t` 通过，无 "duplicate" 警告
  - [ ] 生成的 `nginx.conf` 中，location 使用 include 而非重复定义
  - [ ] curl 测试显示 X-Real-IP, X-Forwarded-For 等 headers 存在
  - [ ] WebSocket headers 正常工作
  - [ ] `./test.sh` 全部通过

  **Agent-Executed QA Scenarios**:
  执行 Verification Strategy 中定义的 6 个场景。

  **Commit**: YES (Final)
  - Message: `test: verify proxy headers fix`
  - Files: 无文件修改，只有测试

---

## Commit Strategy

| After Task | Message | Files |
|------------|---------|-------|
| 1 | `refactor(templates): add proxy_headers.conf for centralized header management` | templates/proxy_headers.conf |
| 2-4 | `refactor(templates): include proxy_headers.conf in location templates` | templates/basic_location_header.jinja, templates/basic_ex_location_root.jinja, templates/http_default_forward.jinja |
| 5 | `test: verify proxy headers fix` | (no files) |

**Squash 建议**: 可以将 Task 1-4 合并为一个 commit，Task 5 单独提交。

---

## Success Criteria

### Verification Commands

```bash
# 配置生成
./start.py

# 语法检查
nginx -t

# Headers 验证
curl -s http://echo.com/headers | jq '.headers | with_entries(select(.key | startswith("X-")))'

# WebSocket 验证
curl -s -H "Upgrade: websocket" http://echo.com/headers | jq '.headers.Upgrade'

# 完整测试
./test.sh
```

### Expected Outputs

1. `nginx -t` 输出：
   ```
   nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
   nginx: configuration file /etc/nginx/nginx.conf test is successful
   ```

2. Headers 检查输出（示例）：
   ```json
   {
     "X-FORWARDED-FOR": "192.168.1.100",
     "X-FORWARDED-PORT": "80",
     "X-FORWARDED-PROTO": "http",
     "X-FORWARDED-SSL": "off",
     "X-FROM": "echo.com",
     "X-REAL-IP": "192.168.1.100"
   }
   ```

3. `test.sh` 输出：
   ```
   All tests passed!
   ```

### Final Checklist
- [ ] 所有 "Must Have" 满足
- [ ] 所有 "Must NOT Have" 未违反
- [ ] nginx -t 通过
- [ ] 所有测试通过
- [ ] 无重复定义警告
- [ ] 文档已更新（如需要）

---

## Rollback Plan

如果部署后发现问题，执行：

```bash
# 1. 恢复原始模板
git checkout HEAD -- templates/basic_location_header.jinja \
    templates/basic_ex_location_root.jinja \
    templates/http_default_forward.jinja

# 2. 删除新增文件
rm -f templates/proxy_headers.conf

# 3. 重新生成配置
./start.py

# 4. 测试
nginx -t
./test.sh
```

---

## Notes

### 为什么 Host 不能放入 proxy_headers.conf

`basic_location_header.jinja` 使用模板变量：
```nginx
proxy_set_header            Host                                "{{ location.proxy_host }}";
```

`basic_ex_location_root.jinja` 使用 Nginx 变量：
```nginx
proxy_set_header        Host ${http_host};
```

两者不同，且都是 location 特定的，所以必须保留在各自的模板中。

### 为什么 X-FROM 不能放入 proxy_headers.conf

X-FROM 包含 `{{ location.listen_host }}`，每个 location 不同，是动态生成的。

### 包含顺序的重要性

`proxy_headers.conf` 使用变量如 `$proxy_connection`，这些变量在 `default_map.conf` 中定义。确保 include 顺序：

```nginx
http {
    include templates/default_map.conf;    # 变量定义
    # ...
    server {
        location / {
            include templates/proxy_headers.conf;  # 使用变量
            # ...
        }
    }
}
```

### 对齐格式说明

参考 `basic_location_header.jinja` 的格式：
```nginx
proxy_set_header            Upgrade                             $http_upgrade;
#           ^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^
#           指令名            参数名（对齐到此处）                   参数值
```

使用空格对齐，使配置文件更易读。
