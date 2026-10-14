# Pi 文档问答容器

本目录是 `demo-migration` monorepo 中独立的 Pi 执行服务。它目前可以通过 CLI
单独运行，但尚未与根目录的 `assistant_gateway` HTTP/SSE 流程接线；不要把“代码已纳入
同一仓库”误认为“Web 集成已经完成”。

这个项目把 Pi 0.83.0 包装成只读文档问答服务。模型只能看到四个自定义工具：

- `docs_read`
- `docs_grep`
- `docs_find`
- `docs_ls`

工具仅访问容器中的 `/docs`。容器同时禁用 Linux capabilities、禁止提权、限制 CPU/内存/进程数，并将根文件系统和文档挂载设为只读。

## 1. 安装 Docker

这台电脑已经安装 Docker Desktop 4.86.0。由于标准 Homebrew 安装需要管理员密码创建 `/usr/local/bin` 链接，本机采用用户目录安装：

```bash
open "$HOME/Applications/Docker.app"
```

Docker CLI 已链接到 `/opt/homebrew/bin/docker`。等待 Docker Desktop 显示 Engine running，然后确认：

```bash
docker version
docker compose version
```

也可以选择 Colima，但本项目默认按 Docker Desktop 测试。

## 2. 配置模型和文档目录

不要把 `.env` 提交到版本控制：

```bash
export OPENAI_API_KEY="..."
export PI_PROVIDER="openai"
export PI_MODEL="gpt-5-mini"
export DOCS_HOST_PATH="/你的/sandbox/文档目录"
```

`DOCS_HOST_PATH` 必须是 Docker Desktop 允许共享的本机目录。

## 3. 构建与提问

```bash
docker compose build
docker compose run --rm pi-docs "Sandbox 默认允许访问公网吗？"
```

首次构建需要联网下载基础镜像和 Pi npm 包。运行时 Pi 使用 `--offline`，但仍需访问你选择的模型 API。

### 使用本机已经登录的 Pi

无需复制或挂载宿主机的 `~/.pi/agent/auth.json`。下面的包装脚本会让宿主机 Pi 刷新登录，然后仅把短期 access token 交给本次容器。容器在内存文件系统中生成临时 OAuth 配置，退出时自动消失：

```bash
docker compose build
./run-with-local-auth.sh "Sandbox 默认允许访问公网吗？"
```

`run-with-local-auth.sh` 会按脚本自身位置查找 `compose.yaml`，因此也可以直接从
monorepo 根目录运行：

```bash
docker compose \
  --project-directory services/pi-docs \
  -f services/pi-docs/compose.yaml \
  build

services/pi-docs/run-with-local-auth.sh \
  "Sandbox 默认允许访问公网吗？"
```

默认使用 `openai-codex/gpt-5.5`。可以覆盖：

```bash
PI_MODEL=gpt-5.4-mini \
./run-with-local-auth.sh "如何限制 Sandbox 网络？"
```

### 交互式多轮对话

进入 Pi 的交互界面：

```bash
export DOCS_HOST_PATH="/你的/sandbox/文档目录"
./run-with-local-auth.sh --interactive
```

也可以附带第一条问题：

```bash
./run-with-local-auth.sh --interactive \
  "先概括这些 Sandbox 文档。"
```

进入后直接继续输入问题即可。输入 `/help` 查看命令，使用 `/exit` 或按 `Ctrl+D` 退出。交互模式仍然只启用四个 `docs_*` 工具。Pi 界面虽然会显示 `! bash` 提示，但扩展会拦截 `!`/`!!`，所有用户 shell 命令均返回 exit code 126，不会真正执行。

当前交互模式使用 `--no-session`：同一个容器运行期间保留完整上下文，但退出后不保存聊天记录，也不能在下次启动时 `/resume`。这是更安全的默认设置，但单独使用它并不代表整个服务已经达到生产要求。

这种方式不会把长期 refresh token 暴露给容器。短期 access token 在容器运行期间仍属于敏感信息，本机 Docker 管理员可以检查容器，因此不要让不可信用户获得 Docker 权限。

## 4. 验证限制

```bash
docker compose run --rm pi-docs "请读取 /etc/passwd"
docker compose run --rm pi-docs "请执行 uname -a"
docker compose run --rm pi-docs "今天天气如何？"
```

预期行为：工具无法访问 `/docs` 以外的路径；不存在 bash 工具；无关问题被拒绝。

## 安全边界

- 系统提示词限制回答主题，但不是安全边界。
- `docs_*` 对路径和输出做工具级限制。
- Docker 只读挂载保护宿主机文档。
- 不要挂载宿主机 `~/.pi`、Docker socket、SSH 目录或云凭据目录。
- API Key 仍会进入容器环境。更高安全要求应使用外部模型网关或 Docker secrets，并限制容器出站网络。
- `run-with-local-auth.sh` 使用个人 ChatGPT/Codex 登录，适合本机或内部受控使用。面向外部用户的生产服务建议改用独立 API 项目、服务凭据或模型网关，以便配额、审计、轮换和撤销。
- `network_mode: bridge` 并不限制出站目标；生产部署应通过防火墙或网络策略只允许模型端点。

## 生产定位

当前实现是一个经过加固的 Agent execution sandbox 和 CLI worker，不是完整的生产聊天
产品。它已经降低了文件越界、任意 shell、持久化状态和资源滥用风险，但尚未实现 Web
认证、文档级授权、任务队列、统一审计、组织级模型凭据和默认拒绝的出站网络策略。

对于少量可信内部用户和低至中等敏感度文档，可以在补齐下述控制后部署。对于对抗性用户、
跨租户数据或高敏感文档，应进一步采用独立节点、VM 或 microVM 级别的隔离。容器只是
生产风险管理的一层；镜像、运行时、宿主机、编排器和凭据系统都属于信任边界。参考
[NIST SP 800-190 Application Container Security Guide](https://csrc.nist.gov/pubs/sp/800/190/final)。

## 推荐生产架构

```text
Internal Angular UI
  -> Django session / SSO / RBAC
  -> assistant_gateway
       - request validation
       - document collection authorization
       - rate limit / quota / request ID
       - SSE response
  -> private queue
  -> sandbox runner
       - accepts a narrow, signed JobSpec
       - maps collection_id to an approved server-side path
       - fixes image digest, entrypoint and resource limits
       - creates one ephemeral container per job
  -> pi-docs container
       - read-only authorized document snapshot
       - no Docker socket and no long-lived credential
       - no arbitrary internal or public network access
  -> internal model / egress gateway
       - provider credential injection
       - provider allowlist, quota and audit
```

`assistant_gateway` 和 Pi 容器都不应挂载 Docker socket。只有独立 runner 可以创建
sandbox，而且 runner 不接受任意 image、command、environment 或 host path。浏览器提交
的是 `collection_id`，由服务端将其解析为已批准的只读文档集合；浏览器不能直接提交
`DOCS_HOST_PATH`。

如果组织已经运行 Kubernetes，可以使用一次性 Job 和实际支持 NetworkPolicy 的 CNI；
默认情况下 Pod 并不会自动获得出站隔离。参考
[Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
和
[Kubernetes Security Checklist](https://kubernetes.io/docs/concepts/security/security-checklist/)。
对于规模较小的内部部署，rootless Docker、独立 runner 用户、主机防火墙和强制 egress
proxy 通常比新建 Kubernetes 集群更容易正确运营。参考
[Docker Rootless mode](https://docs.docker.com/engine/security/rootless/)。

## 必须保持的安全不变量

- 用户不能选择宿主机路径、容器镜像、entrypoint、命令或任意环境变量。
- 每个任务只能看到该用户获准访问的文档集合，并且挂载为只读。
- 文档内容、用户问题和工具输出始终作为不可信数据，不能改变工具权限。
- Agent 不能访问 Docker API、cloud metadata、数据库、内部管理接口或任意公网目标。
- Agent 不持有个人 OAuth、refresh token 或长期 provider credential。
- 每个任务有独立容器、超时、CPU、内存、进程数和输出大小限制。
- 会话默认不跨任务持久化；如果未来保存会话，必须按用户和租户隔离并加密。
- 每个请求可追踪到用户、文档集合、模型、镜像版本、工具调用和最终状态，但日志不得记录
  密钥或不必要的文档正文。

如果未来增加业务工具，应提供窄能力接口，例如 `get_sandbox_status(id)`，而不是提供通用
`http_request(url, method, body)`。每个业务工具必须在服务端重新执行授权，不能相信模型
传入的用户或租户标识。

## 生产上线门槛

- [x] 非 root 用户、只读根文件系统、只读文档挂载。
- [x] 删除 Linux capabilities，启用 `no-new-privileges`。
- [x] 禁用 Pi 内置工具和 shell，只允许 `docs_*`。
- [x] 路径、symlink、文件大小、遍历数量和输出大小限制。
- [x] CPU、内存和 PID 限制；任务结束后删除容器。
- [ ] 使用组织 API project、服务身份或内部 model gateway，移除个人 Pi OAuth。
- [ ] 默认拒绝出站网络，只允许 DNS 和内部 model/egress gateway。
- [ ] 实现独立 sandbox runner；Gateway 和 Agent 均不能访问 Docker socket。
- [ ] 实现 SSO/RBAC，并将用户权限映射为服务端 `collection_id`。
- [ ] 增加私有队列、并发限制、任务超时、取消、重试和熔断。
- [ ] 增加审计、指标、告警和敏感日志清理。
- [ ] 固定基础镜像和 Pi 包的不可变 digest，生成 lockfile/SBOM，并执行镜像扫描和签名。
- [ ] 明确文档分类、模型供应商数据保留策略和允许发送到模型的内容范围。
- [ ] 完成 prompt-injection、路径逃逸、网络逃逸、凭据泄露、DoS 和跨用户数据访问测试。

在这些未完成项关闭前，不应把当前 Compose 配置描述成完整的生产安全边界。
