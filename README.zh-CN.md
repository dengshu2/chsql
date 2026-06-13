# chsql

[English](README.md) · 简体中文

面向 **Agent / LLM** 的轻量 ClickHouse 查询 CLI —— **JSON 优先、默认只读、语义化退出码**。
底层封装 `clickhouse-driver` / `clickhouse-connect`，**不依赖任何第三方 CLI 框架**（只用标准库
`argparse`）。开箱即用：native + HTTP 双传输、系统钥匙串存密码全都内置（装好约 8 MB，仍远小于
138 MB 的官方二进制）。设计目的：让 Agent 通过命令行直接查 ClickHouse，而不必启动笨重的 MCP 服务。

## 安装

推荐 **uv**（把 `chsql` 装进全局 PATH）：

```bash
uv tool install chsql                  # 从 PyPI(即将发布)
uv tool install -e /path/to/chsql      # 从本地源码(可编辑,改完即生效)
```

或用 **pipx**：

```bash
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
| `chsql config init\|show\|path\|edit` | 管理连接 profile |
| `chsql skill install [--path 目录]` | 安装配套 Agent skill |
| `chsql --version` | 版本号 |

## 连接与凭据

跑一次 `chsql config init` 保存 profile，之后 `chsql databases` 零参数即可用。
沿用 `gh` / AWS CLI 的"配置与密钥分离"：**非机密设置**写入 `~/.config/chsql/config.ini`；
**密码绝不写进该文件**——存进系统钥匙串（同 `gh`），或用 `password_command` 查询时动态取
（同 AWS `credential_process`）。

```bash
# 交互式(只问 host/port/user/database + 密码后端)
chsql config init

# 一行配好(不交互):连接走 flag,密码从 stdin 进钥匙串
echo "$PASSWORD" | chsql config init --host ch.example.com --port 443 --secure \
  --user me --password-stdin

# 或用 URL 一次性填充
chsql config init --url 'clickhouse://me@ch.example.com:443?secure=1'

chsql config show     # 查看 profile(不显示密钥)
chsql config path     # 打印配置文件路径
chsql config edit     # 用 $EDITOR 打开
chsql --profile prod databases   # 使用具名 profile
```

也可用环境变量 / 命令行 flag（flag 优先）：

```
CLICKHOUSE_HOST  CLICKHOUSE_PORT  CLICKHOUSE_USER  CLICKHOUSE_PASSWORD
CLICKHOUSE_SECURE  CLICKHOUSE_DATABASE  CLICKHOUSE_PROTOCOL  CLICKHOUSE_PROFILE
```

**密码解析优先级**：`--password` > `$CLICKHOUSE_PASSWORD` > 系统钥匙串 > `password_command`。
其余设置：flag > 环境变量 > profile > 内置默认。

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
