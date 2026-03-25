# 微信小程序抢票工具 使用说明

---

## 一、用 Fiddler 抓包获取 Token

**下载 Fiddler Classic**（免费）：https://www.telerik.com/fiddler/fiddler-classic

### 配置步骤

1. 打开 Fiddler → 菜单 `Tools` → `Options` → `HTTPS` 选项卡
2. 勾选 `Capture HTTPS CONNECTs` 和 `Decrypt HTTPS traffic`，点击 `OK`（会提示安装证书，全部同意）
3. 打开微信 PC 端，进入「跃动乒羽馆」小程序，随便点一个场地

### 找到 Token

4. 在 Fiddler 左侧请求列表中找到域名包含 `zwcdata.com` 的请求（点一下）
5. 右侧切换到 `Inspectors` → `Headers`，找到：
   ```
   Authorization: Bearer eyJhbGci...（一长串字符）
   ```
6. 复制 `Bearer ` **后面那一段**（不含 Bearer 和空格），粘贴到 `config/config.yaml` 的 `auth.token` 字段

### 确认抓包成功

右侧 `Inspectors` → `JSON` 能看到返回的场地列表数据（含 id、name、status 字段）即为成功。

---

## 二、用 Conda 配置 Python 环境

**前提：已安装 Anaconda 或 Miniconda**（[下载 Miniconda](https://docs.conda.io/en/latest/miniconda.html)，更轻量）

在 **Anaconda Prompt** 中执行：

```bash
conda create -n ticket python=3.11 -y
conda activate ticket
pip install -r requirements.txt
```

**为什么用 Conda？** 系统可能存在多个 Python 版本，直接运行 `python` 可能指向错误版本导致包导入失败。Conda 环境隔离可确保依赖正确加载。

### 运行（每次运行前先激活环境）

```bash
conda activate ticket

# 真实抢票
python src/main.py

# 测试（不发真实请求）
python src/main.py --dry-run
```

> **注意**：必须在 Anaconda Prompt 或已初始化 conda 的终端中运行，普通 CMD/PowerShell 默认不识别 `conda activate`。

---

## 三、关键参数说明

核心参数全部在 `config/config.yaml` 的 `engine` 部分：

| 参数 | 说明 | 激进模式 | 保守模式 |
|------|------|----------|----------|
| `concurrency` | 同时发出的并发请求数 | `5` | `1` |
| `attempt_rounds` | 触发后重复抢几轮 | `5` | `2` |
| `round_delay_ms` | 每轮之间的间隔（毫秒） | `100` | `500` |
| `request_timeout_s` | 单次请求超时（秒） | `3` | `8` |
| `retry.max_retries` | 遇到 502/503 最多重试次数 | `3` | `1` |

### 激进配置（抢热门场地，不怕被限频）

```yaml
engine:
  concurrency: 5
  attempt_rounds: 5
  round_delay_ms: 100
  request_timeout_s: 3
  retry:
    max_retries: 3
```

### 保守配置（避免被服务器限速或封 token）

```yaml
engine:
  concurrency: 1
  attempt_rounds: 2
  round_delay_ms: 500
  request_timeout_s: 8
  retry:
    max_retries: 1
```

> **注意**：token 有有效期，每次使用前建议重新抓包确认 token 未过期。
