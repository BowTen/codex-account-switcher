## Context

`codex-auth usage` 已经具备多账号查询、自动 refresh 和批量并发能力，但当前查询链路仍然默认直接发起真实 usage 请求，没有一个更早、更明确的网络判定阶段。结果是代理异常、DNS 失败、出口受阻或远端无响应时，操作者往往只能看到一个“卡住很久然后失败”的命令，而不是一个可区分的网络问题。

这个 change 只收敛 usage 查询的网络语义，不改变账号存储、switch 行为或 refresh 协议。关键约束是：继续使用现有 usage 端点，不引入新依赖，不把网络细节泄露到终端之外的其它能力。

## Goals / Non-Goals

**Goals:**
- 在任何 named 或 batch usage 查询开始前，先判断 usage 端点是否可达。
- 给 usage 请求补上明确超时，而不是依赖无限期阻塞。
- 区分三类失败语义：
  - preflight 不可达 -> 命令级失败
  - usage 请求超时 -> named 直接失败，batch 整批中止
  - 其它 usage/refresh 失败 -> 继续沿用按账号隔离
- 让 CLI 可以输出稳定、简洁的网络错误文案，而不是靠字符串猜测底层异常。

**Non-Goals:**
- 不探测 refresh endpoint。
- 不新增 CLI 参数来配置 timeout 或 preflight。
- 不修改账号快照格式。
- 不改变非 usage 命令的网络行为。

## Decisions

### 1. 只对 usage endpoint 做 preflight，并把“收到任何 HTTP 响应”视为可达

preflight 目标固定为 `https://chatgpt.com/backend-api/wham/usage`。由于 preflight 发生在真正的账号鉴权请求之前，它不依赖有效 token，只需要确认网络路径已经打到目标站点。因此只要收到了服务端 HTTP 响应，不论是 `401`、`403`、`405` 还是 `200`，都视为“usage endpoint reachable”。

备选方案：
- 同时探测 refresh endpoint。
- 用完整鉴权请求做真实 usage 探针。

拒绝原因：
- refresh endpoint 不在本次需求范围内，会引入不必要的额外网络面。
- 用真实鉴权请求做 preflight 会把“网络是否可达”和“账号是否可用”耦合在一起，失去 preflight 的价值。

### 2. 引入专门的 usage 网络异常类型，而不是继续依赖通用 `ValueError`

服务层需要对 timeout 做特殊处理，但普通 HTTP/JSON 失败仍应保持 per-account 语义。如果继续只抛通用 `ValueError`，上层只能靠错误字符串判断是不是 timeout，语义脆弱且不利于测试。因此需要新增如 `UsageNetworkError` 和 `UsageTimeoutError` 这类 typed errors，让 service 和 CLI 都能稳定识别。

备选方案：
- 继续沿用 `ValueError`，在 service 中通过字符串匹配区分 timeout。

拒绝原因：
- 字符串匹配容易被文案改动破坏。
- 测试只能验证文本，无法验证行为边界。

### 3. batch 查询只在 timeout 上整批中止，其它账号失败继续隔离

用户明确要求 timeout 代表“不要继续等下去”，所以 batch 中只要有一个账号请求 timeout，就应当尽快中止剩余批次并返回非零退出码。相对地，HTTP 4xx/5xx、payload 错误、refresh 失败仍然是单账号问题，不应破坏整个批次。

备选方案：
- 沿用所有错误都按账号隔离。
- 任何异常都整批失败。

拒绝原因：
- 前者不能满足“卡住就立刻终止”的要求。
- 后者会把普通业务错误也提升成命令级错误，损失现有批量容错能力。

### 4. 把 preflight 和 timeout 语义放在 usage API + service 边界，而不是 CLI 层

CLI 应只负责把最终失败显示给用户。真正的网络探测、超时映射和 batch 中止策略应该由 usage API 和 service 组合实现，这样 named/batch 两条路径共享同一套行为，测试也能在非 CLI 层直接覆盖。

备选方案：
- 在 CLI 里先行做 preflight，再调用已有 service。

拒绝原因：
- 会把同一条网络语义拆散在多个层次。
- 后续 live view 或其它展示模式复用时仍要重复实现。

## Risks / Trade-offs

- [额外增加一次 preflight 网络往返] → 只探测一个固定端点，并把任何 HTTP 响应都视为可达，尽量降低成本和误判。
- [timeout 中止后已有部分结果可能未输出] → 明确定义 timeout 是命令级失败，把快速终止优先级放在“尽量保留局部结果”之前。
- [新增异常类型会影响现有错误处理路径] → 让新异常继承现有 CLI 已捕获的错误基类，并补上 CLI/service 回归测试。
