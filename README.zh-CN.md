# chsql

[English](README.md) · 简体中文

面向 **Agent / LLM** 的轻量 ClickHouse 查询 CLI —— **JSON 优先、默认只读、语义化退出码**。
底层是 `clickhouse-driver` 的一层薄封装，**零第三方 CLI 依赖**（只用标准库 `argparse`），
装好约 3.5 MB（前提是环境已有 Python）。设计目的：让 Agent 通过命令行直接查 ClickHouse，
而不必启动一个笨重的 MCP 服务。

## 安装

```bash
# 方式一:uv tool(推荐,装进全局 PATH)
uv tool install "chsql[http,keyring]"          # 发到 PyPI 后
uv tool install --editable /path/to/chsql \
  --with clickhouse-connect --with keyring     # 从本地源码(可编辑,改完即生效)

# 方式二:pipx
pipx install "chsql[http,keyring]"

chsql skill install     # 把配套的 Agent skill 装到 ~/.agents/skills
```

可选依赖：`[http]` 加 HTTP(S) 接口支持（反代部署），`[keyring]` 加系统钥匙串存密码。

## 快速开始

```bash
chsql config init       # 交互式配置一次连接信息(见下),之后零参数直接用
chsql databases         # 列库
chsql tables system --like '%part%'
chsql describe system.parts
chsql query "SELECT count() FROM system.tables"
```

默认输出 **JSONEachRow**（每行一个 JSON 对象）。可切 `--format json|table|csv|tsv`。

## 命令

| 命令 | 说明 |
| --- | --- |
| `chsql query "<sql>"` | 执行 SQL（无参数则读 stdin）。默认只读，写操作需 `--write`，建表/删表需 `--allow-ddl` |
| `chsql databases` | 列出所有数据库 |
| `chsql tables [库] --like ... --not-like ...` | 列表，含引擎和行数/字节数 |
| `chsql describe <表 \| 库.表>` | 查看表结构（列名、类型、默认值、注释） |
| `chsql config init / show` | 配置 / 查看连接 profile |
| `chsql skill install [--path 目录]` | 安装配套 Agent skill |

## 连接与凭据

跑一次 `chsql config init` 保存连接 profile，之后 `chsql databases` 零参数即可用。
沿用 `gh` / AWS CLI 的"配置与密钥分离"模型：**非机密设置**写入
`~/.config/chsql/config.ini`；**密码绝不写进该文件**——存进系统钥匙串
（`pip install 'chsql[keyring]'`，同 `gh`），或用 `password_command` 在查询时动态取
（同 AWS `credential_process`）。

```bash
chsql config init                 # 交互式:写默认 profile
chsql config show                 # 查看 profile(不显示密钥)
chsql --profile prod databases    # 使用具名 profile
```

也可用环境变量 / 命令行 flag（flag 优先）：

```
CLICKHOUSE_HOST  CLICKHOUSE_PORT  CLICKHOUSE_USER  CLICKHOUSE_PASSWORD
CLICKHOUSE_SECURE  CLICKHOUSE_DATABASE  CLICKHOUSE_PROTOCOL  CLICKHOUSE_PROFILE
```

**密码解析优先级**：`--password` > `$CLICKHOUSE_PASSWORD` > 系统钥匙串 > `password_command`。
其余设置：flag > 环境变量 > profile > 内置默认。

```bash
# 公共只读 playground(native 协议)
chsql --secure --host play.clickhouse.com --user explorer databases

# 反代后只开 HTTP 接口的服务器(443 上的 HTTP 接口)
chsql --host ch.example.com --port 443 --secure databases   # auto -> http
```

### 传输协议

| 协议 | 端口 | 驱动 | 适用 |
| --- | --- | --- | --- |
| `native`（默认） | 9000 / 9440 | clickhouse-driver | 直连 TCP |
| `http` | 8123 / 8443 / 443 | clickhouse-connect（`chsql[http]`） | HTTPS 反代后的服务器 |

`--protocol auto`（默认）对 443/8123/8443 端口选 **http**，否则选 **native**。

## Agent 契约

| 方面 | 行为 |
| --- | --- |
| 输出 | 数据 → stdout（默认 JSONEachRow）；错误 → stderr，格式 `{"error","code"}` |
| 退出码 | `0` 成功 · `1` 查询错 · `2` 连接错 · `3` 写/DDL 被只读拦截 |
| 安全 | 默认只读；`--write` 放行 DML，`--allow-ddl` 放行 DDL |
| 参数化 | `--param k=v` 绑定到 SQL 里的 `%(k)s`（数字值不加引号） |

## 开发

```bash
pip install -e '.[dev]'
pytest
```

## 许可

MIT
