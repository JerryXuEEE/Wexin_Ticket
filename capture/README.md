# 抓包指南 — 微信小程序 API 捕获

## 准备工具

1. 安装 mitmproxy: `pip install mitmproxy`
2. 手机和电脑在同一局域网

## 步骤

### 1. 启动 mitmproxy

```bash
# 使用自定义插件（自动过滤+记录）
mitmproxy -s capture/mitmproxy_addon.py

# 或使用 mitmdump（无 UI，纯命令行）
mitmdump -s capture/mitmproxy_addon.py
```

默认监听 `0.0.0.0:8080`。

### 2. 手机配置代理

1. 打开手机 WiFi 设置
2. 选择当前网络 → 代理 → 手动
3. 服务器: 电脑 IP 地址（如 `192.168.1.100`）
4. 端口: `8080`

### 3. 安装 CA 证书（HTTPS 解密必需）

1. 手机浏览器打开 `http://mitm.it`
2. 下载对应平台的证书
3. **Android**: 设置 → 安全 → 加密与凭据 → 安装证书
4. **iOS**: 设置 → 已下载描述文件 → 安装，然后 设置 → 通用 → 关于本机 → 证书信任设置 → 启用

> 注意: Android 7+ 用户可能需要使用 root 或 Magisk 模块来信任用户证书。

### 4. 操作小程序

1. 打开微信
2. 进入"跃动预约"小程序
3. 执行以下操作并观察 mitmproxy 控制台输出:
   - 浏览场地列表（捕获查询接口）
   - 选择场地并预约（捕获预约接口）
   - 查看预约记录（捕获状态接口）

### 5. 分析抓包数据

```bash
python capture/parse_captured.py
```

脚本会自动:
- 分析域名和端点
- 提取认证信息
- 生成 `config.yaml` 配置片段
- 显示请求/响应样本

### 6. 更新配置

将 `parse_captured.py` 输出的配置片段粘贴到 `config/config.yaml` 对应位置。

然后根据样本数据修改 `src/api/venue_client.py` 中的 PLACEHOLDER 方法:
- `_build_booking_payload()` — 请求体结构
- `_parse_slots()` — 场地列表解析
- `_parse_booking_response()` — 预约响应解析

## 常见问题

**Q: 看不到 HTTPS 流量?**
A: 确保 CA 证书已正确安装并信任。

**Q: 微信小程序流量抓不到?**
A: 部分小程序使用固定 TLS 证书 (certificate pinning)。可尝试:
- 使用 Xposed + TrustMeAlready 模块
- 使用 Android 模拟器 + root

**Q: 域名关键字不匹配?**
A: 设置环境变量调整: `CAPTURE_KEYWORDS=keyword1,keyword2 mitmproxy -s capture/mitmproxy_addon.py`
