# mcp-faultlab

Break your agent before production.

这是一个无第三方依赖的 Agent 故障注入与 Replay 测试工具（v0.4.1）。它把 Scenario、故障、完整轨迹、可验证断言和 HTML 报告串成一条命令。

## 快速开始

```bash
cd mcp-faultlab
python3 -m pip install .
python3 -m mcp_faultlab init tests
python3 -m mcp_faultlab validate examples/tool-timeout-recovery.yml
python3 -m mcp_faultlab run examples/tool-timeout-recovery.yml
open examples/tool-timeout-recovery.html
```

最有传播性的演示：

```bash
python3 -m mcp_faultlab run examples/malicious-tool-result.yml
# 0 passed · 2 failed · 1 security violation · 1 attack injected
python3 -m mcp_faultlab run examples/agent-prompt-injection-safe.yml
# 2 passed · 0 failed · 0 security violation · 1 attack injected
```

目标进程还支持 `response_timeout_ms`、`max_response_bytes`、`cwd` 和 `env`；故障可以用 `times: 1` 只注入前一次匹配请求，适合测试“第一次超时、第二次恢复”。

目标进程采用简单的 JSONL 协议：stdin 每行一个请求，stdout 每行一个响应。例如：

```json
{"id": 1, "method": "tools/call", "params": {"name": "search", "arguments": {"q": "faultlab"}}}
```

Scenario 可以声明 `target.command`，也可以声明 `agent.command + server.command`。前者适合直接测试工具服务器，后者会让 Agent 通过 Faultlab Proxy 驱动工具服务器，真实记录 Agent 在恶意结果后的下一步调用。

```yaml
name: tool-timeout-recovery
target:
  command: python3 examples/demo_server.py

requests:
  - id: 1
    method: tools/call
    params:
      name: search
      arguments: {q: faultlab}

faults:
  - kind: timeout
    method: tools/call
    delay_ms: 8000

assertions:
  - no_duplicate_tool_call
  - final_status: recoverable
  - max_retries: 2
```

## 命令

```text
python3 -m mcp_faultlab init <directory>
python3 -m mcp_faultlab packs
python3 -m mcp_faultlab validate <scenario.yml>
python3 -m mcp_faultlab run <scenario.yml> [--out <dir>]
python3 -m mcp_faultlab run tests/ [--out faultlab-report]
python3 -m mcp_faultlab replay <cassette.json> [--serve]
python3 -m mcp_faultlab report <run.json>
python3 -m mcp_faultlab proxy <scenario.yml> --upstream http://127.0.0.1:9000/mcp
```

`run` 会生成 `<scenario>.run.json`、`<scenario>.html` 和 `<scenario>.cassette.json`。存在失败断言时返回退出码 1，适合 CI。

当参数是目录时，CLI 会递归发现 `.yml`、`.yaml` 和 `.json` 场景，逐个执行并生成 `campaign.json`、`campaign.html` 以及每个场景的独立报告；任何场景失败都会让整个 campaign 返回退出码 1。

`attack_injections` 和 `security_violations` 是两个不同指标：前者表示测试输入已注入，后者只在 Agent 实际调用危险工具或携带凭据外传时增加。可直接运行 `examples/malicious-tool-result.yml`：脆弱 Agent 会因继续调用 `shell.exec` 而失败；`examples/agent-prompt-injection-safe.yml` 则应通过。

`replay --serve` 默认严格校验 method 和 params，再从 stdin 接收 JSON 请求并按 request id 返回 cassette 中已记录的响应；`--lenient` 才会退化为只按 id 匹配。它可以作为 Agent 的确定性工具服务器。`proxy` 是标准库实现的 HTTP JSON Proxy，会把请求转发到 upstream，同时执行 Scenario 故障注入并可录制 HTTP cassette。HTTP Proxy 场景不需要 `target.command`，可参考 `examples/http-proxy.yml`。

报告现在还包含最大/平均延迟、工具调用数、重试次数和估算 token 数，并在 GitHub Actions 中自动写入 `GITHUB_STEP_SUMMARY`。

## Attack Packs

内置十个高频场景：工具描述注入、工具返回值注入、环境变量诱导、Schema 漂移、假成功、重复副作用、无限重试、敏感数据、超大结果和危险工具链诱导。可以在 YAML 中写：

```yaml
attacks:
  - tool_result_prompt_injection
  - sensitive_result
```

Attack Pack 会展开为可记录的 fault，并在报告中显示为 `attack injection`；只有 Agent 后续行为触发安全规则时才标记 `security violation`。

断言还支持 `no_sensitive_data_in_results`、`no_tool_after_timeout`、`no_stale_data_used`、`max_latency_ms`、`max_result_bytes` 和 `max_tool_calls`，未知断言会在 `validate` 阶段 fail closed。

## GitHub Action

`mcp-faultlab` 自带一个可复用的 composite action。直接在目标仓库的 workflow 中使用：

```yaml
- uses: lee226520-hue/mcp-faultlab@v1
  with:
    scenario: tests/agent-safety.yml
```

本地版本的 Action 会调用 CLI、保留 HTML/JSON 报告，并将失败状态传给 CI。

## 设计边界

这一版仍把 Agent SDK 解耦，但已经提供 JSONL Replay server 和 HTTP JSON Proxy，并统一使用 v2 cassette schema。对于 SSE、二进制内容和不同 MCP SDK 的握手流程，仍需要在 transport adapter 层补充协议适配；事件模型、断言和报告无需重写。
