# chsql

[English](README.md) · 简体中文

面向 **Agent / LLM** 的轻量 ClickHouse 查询 CLI —— **JSON 优先、默认只读、语义化退出码**。
底层封装 `clickhouse-driver` / `clickhouse-connect`，**不依赖任何第三方 CLI 框架**（只用标准库
`argparse`）。开箱即用：native + HTTP 双传输、系统钥匙串存密码全都内置（装好约 8 MB，仍远小于
138 MB 的官方二进制）。设计目的：让 Agent 通过命令行直接查 ClickHouse，而不必启动笨重的 MCP 服务。

## 安装

```bash
uv tool install chsql     # 推荐(把 chsql 装进全局 PATH)
# 或
pipx install chsql
```

然后安装配套 Agent skill（通用路径 `~/.agents/skills`）：

```bash
chsql skill install
```

## 使用

```bash
chsql databases
chsql tables system --like '%part%'
chsql describe system.parts
chsql query "SELECT count() FROM system.tables"
```

默认输出 **JSONEachRow**（每行一个 JSON）。可切 `--format json|table|csv|tsv`。
结果默认上限 10 万行（`--max-rows N`，`--max-rows 0` 关闭）。

## 命令

| 命令 | 说明 |
| --- | --- |
| `chsql query "<sql>"` | 执行 SQL（无参数则读 stdin）。默认只读，写需 `--write`，DDL 需 `--allow-ddl` |
| `chsql databases` | 列出数据库 |
| `chsql tables [库] --like ... --not-like ...` | 列表，含引擎和行数/字节数 |
| `chsql describe <表 \| 库.表>` | 查看表结构（列名、类型、默认值、注释） |
| `chsql login [URL] \| logout \| login --show` | 管理已保存的连接 |
| `chsql skill install [--path 目录]` | 安装配套 Agent skill |
| `chsql --version` | 版本号 |

## 连接 —— 一个 URL

一个连接就是一个 URL：

```
clickhouse://user:password@host:port/database?secure=1&protocol=http
```

| 部分 | 含义 |
| --- | --- |
| scheme | `clickhouse://`，或 `clickhouses://`（带 s 表示走 TLS） |
| `user:password@` | 凭据（可选；密码里的 `@ : / ?` 等特殊字符需 percent 编码） |
| `host:port` | 服务器；端口可省（按协议默认：native 9000/9440，http 8123/8443） |
| `/database` | 默认库（可选；缺省为 `default`） |
| `?secure=1` | 走 TLS。接受 `1/true/yes/on`。`clickhouses://` 或安全端口也会自动开启 |
| `?protocol=` | `auto`（默认）/ `native` / `http`。`auto` 对 443/8123/8443 端口选 http，否则 native |

`chsql login` 把它存进**系统钥匙串**（密码绝不落到任何配置文件），之后零参数即可用：

```bash
chsql login 'clickhouse://me:pw@ch.example.com:443?secure=1'   # 粘一次
chsql databases                                                # 零参数
chsql login --show     # 打印已存 URL(密码打码)
chsql logout           # 删除
```

解析优先级：`--url` > `$CHSQL_URL` 环境变量 > 已 login 的 URL。
单个 `--host/--port/--user/--password/--secure/--protocol/--database` flag 可临时覆盖字段：

```bash
# 公共只读 playground —— 无需 login
chsql --host play.clickhouse.com --user explorer --secure databases
```

**无桌面的服务器 / VPS**：没有系统钥匙串，别用 `chsql login`，改用环境变量（12-factor 标准做法）：

```bash
export CHSQL_URL='clickhouse://user:pass@host:443?secure=1'   # 写进 ~/.bashrc
chsql databases
```

### 传输协议

| 协议 | 端口 | 驱动 | 适用 |
| --- | --- | --- | --- |
| `native`（默认） | 9000 / 9440 | clickhouse-driver | 直连 TCP |
| `http` | 8123 / 8443 / 443 | clickhouse-connect | HTTPS 反代后的服务器 |

`--protocol auto`（默认）对 443/8123/8443 端口选 **http**，否则选 **native**。

## Agent 契约

| 方面 | 行为 |
| --- | --- |
| 输出 | 数据 → stdout（默认 JSONEachRow）；错误 → stderr，格式 `{"error","code"}` |
| 退出码 | `0` 成功 · `1` 查询错 · `2` 连接错 · `3` 写/DDL 被只读拦截 |
| 安全 | 默认只读；`--write` 放行 DML，`--allow-ddl` 放行 DDL；多语句感知 |
| 限制 | 结果按 `--max-rows`（默认 10 万）截断，截断时 stderr 给提示 |
| 参数化 | `--param k=v` 绑定到 SQL 的 `%(k)s`（数字值不加引号） |

## 开发

```bash
pip install -e '.[dev]'
pytest
```

## 许可

MIT
