# Mac 环境配置指南

---

## 一、安装 Miniconda

### 1. 下载安装包

前往官网下载：https://docs.conda.io/en/latest/miniconda.html

- Apple Silicon（M1/M2/M3/M4）选：**Miniconda3 macOS Apple M1 64-bit pkg**
- Intel Mac 选：**Miniconda3 macOS Intel x86 64-bit pkg**

> 选 `.pkg` 格式，双击安装更方便。

### 2. 安装

双击下载的 `.pkg` 文件，按提示一路「继续」→「同意」→「安装」。

安装完成后，**重新打开一个终端窗口**（Terminal / iTerm2）。

`.pkg` 安装包会自动运行 `conda init zsh`，修改 `~/.zshrc`，**无需手动配置环境变量**。

### 3. 验证安装

```bash
conda --version
```

应输出 `conda 24.x.x` 类似版本号。若提示 `command not found`，手动执行：

```bash
~/miniconda3/bin/conda init zsh
```

然后关闭并重新打开终端。

### 4. 创建项目环境

```bash
conda create -n ticket python=3.11 -y
conda activate ticket
pip install -r requirements.txt
```

---

## 二、安装 VSCode

### 1. 下载

前往官网：https://code.visualstudio.com/

点击 **Download Mac Universal**（同时支持 Intel 和 Apple Silicon）。

### 2. 安装

1. 解压下载的 `.zip` 文件，得到 `Visual Studio Code.app`
2. 将其拖入 `/Applications` 文件夹

### 3. 安装 `code` 命令行工具

打开 VSCode → 按 `⌘ + Shift + P` → 输入 `Shell Command` → 选择 **Install 'code' command in PATH**

之后可在终端直接用 `code .` 打开当前目录。

### 4. 安装推荐插件

| 插件 | 用途 |
|------|------|
| Python（Microsoft） | Python 语言支持 |
| Pylance | 类型检查和自动补全 |
