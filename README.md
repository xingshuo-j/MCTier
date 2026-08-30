<div align="center">

  # MCTier for Debian

  **MCTier 的 Debian/Linux 原生适配分支（与官方 Windows / Android 客户端互通）**

  <p>
    <img src="https://img.shields.io/badge/fork自-upstream%20MCTier-blue?style=flat-square" alt="Fork">
    <img src="https://img.shields.io/badge/Debian-13%20(trixie)-a80036?style=flat-square" alt="Debian 13">
    <img src="https://img.shields.io/badge/KDE%20Plasma-6%20Wayland-1d99f3?style=flat-square" alt="KDE Wayland">
    <img src="https://img.shields.io/badge/EasyTier-2.5.0%20(88a45d11)-2ea44f?style=flat-square" alt="EasyTier">
    <img src="https://img.shields.io/badge/状态-联机已通%2F媒体推进中-orange?style=flat-square" alt="Status">
  </p>

  [上游仓库](https://github.com/pmh1314520/MCTier)（Windows / Android 官方构建） · [本分支](https://github.com/xingshuo-j/MCTier)

</div>

---

## 项目简介

fork 自 [MCTier](https://github.com/pmh1314520/MCTier)，因为 wine 几乎不可用，于是让 agent 做了对 Debian 系统的支持。

本分支让 MCTier 在 **Debian 13 + KDE Plasma 6 (Wayland)** 的桌面环境下原生运行，
与官方 **Windows / Android 客户端**互连互通：同一大厅、同一信令、同一 EasyTier 节点、同一聊天协议。
适配只做平台层，不改动任何协议逻辑——好友使用官方客户端**无需任何改动**。

## 当前状态

> 保留自实机测试的一手结论，更新随进度同步。

目前已实现：**联机房间、发送文字、图片、文件夹共享**。
在主播的机子上还不能跑通**连麦和屏幕共享**功能（根因与解法见下方"媒体层说明"）。

| 功能 | 状态 | 说明 |
| --- | :---: | --- |
| 创建 / 加入大厅、二维码邀请、成员列表 | ✅ | 真机验证：与手机官方 APK 同大厅互通 |
| 发送文字 / 图片 / Emoji、消息弹幕 | ✅ | 纯前端信令 + WebRTC 数据面，跨平台零改动 |
| 文件夹共享 / 文件传输 | ✅ | axum HTTP 服务器纯 Rust，跨平台 |
| EasyTier 虚拟组网（TUN） | ✅ | `tun device ready. dev: MCTier_Net`，DHCP 分配 `10.126.126.1/24`（与 Windows 同网段） |
| Minecraft 世界自动发现 / 游戏快连 | ✅ | 纯 Rust：UDP 组播扫描 + TCP 代理 + 端口预设 |
| 虚拟域名 Magic DNS | ✅ | `/etc/hosts` 写入，无权限时 pkexec 图形授权 |
| 开机自启动 / 系统托盘 / 迷你悬浮窗 | ✅ | XDG autostart；libayatana 托盘（KDE 实测正常） |
| 网络诊断 | ✅ | 真实现：`/sys/class/net` 网卡、ufw/firewalld、ping/UDP 探测 |
| 语音（连麦） | 🔄 | 见媒体层说明，推进中 |
| 屏幕共享 / 远程控制 | 🔄 | 同上；被控端键鼠注入已就绪待验 |
| 回声消除参考（system_audio） | 🟡 | PipeWire monitor 回采已实现，待语音链路通后调优 |
| MC 启动器助手（注册表检测） | ❌ | Windows 专属，Linux 降级（世界发现/游戏快连不受影响） |

### 媒体层说明（连麦 / 屏幕共享的根因）

Debian 官方 `webkit2gtk` 构建在**编译期未启用 WebRTC**：
离屏 WebView 探针实测 `RTCPeerConnection === undefined`，且任何运行时设置都无法挽回。
因此上游的语音/屏幕/远控媒体管线在 Debian 的系统 WebKit 上从未启动过——
这不是适配引入的回归，而是发行版构建策略问题（上游 Windows 端的 WebView2 不受影响）。

**解法（进行中）**：使用 Debian 自己的 webkit2gtk 源码与补丁集，注入
`-DENABLE_WEB_RTC=ON -DUSE_LIBRICE=OFF` 自建一份引擎，放入私有目录、
经 `LD_LIBRARY_PATH` 仅对本应用生效——系统 WebKit 不动，其他应用不受影响。
完成后本表将逐一更新实测结果。

## 快速开始

### 系统要求

| 项目 | 要求 |
| --- | --- |
| 发行版 | Debian 13 (trixie)（其他发行版未验证，欢迎反馈） |
| 桌面 | KDE Plasma / GNOME，Wayland 或 X11 |
| 网络 | 能访问所配置的 EasyTier 节点与信令服务 |

### 第零步：获取第三方二进制

与上游同理，内嵌的 EasyTier 二进制不入库。Linux 侧来自
[EasyTier 官方 Release v2.5.0](https://github.com/EasyTier/EasyTier/releases/tag/v2.5.0)
的 `easytier-linux-x86_64-v2.5.0.zip`（与上游 Windows 侧同版本同 commit `88a45d11`）：

```bash
mkdir -p src-tauri/resources/binaries/linux
cd src-tauri/resources/binaries/linux
# 解压后取 easytier-core / easytier-cli 两个文件放入本目录（chmod 755）
```

### 第一步：构建

```bash
npm install
npm run tauri build -- --no-bundle   # 产物：src-tauri/target/release/mctier
npm test                             # 前端逻辑单测（34 用例）
cd src-tauri && cargo test --lib     # Rust 单测（133 用例）
```

Linux 编译期只依赖上面的两个 easytier 文件；Windows 的 `.exe/.dll/.sys`
已按平台 `#[cfg]` 分离，不参与 Linux 编译。

### 第二步：启动

**请使用启动包装脚本**（它带两个 Linux 必需的环境修正，直接跑裸二进制会踩已知问题）：

```bash
./scripts/run-linux.sh
```

脚本做的事：
1. `GTK_IM_MODULE=""`——绕开 WebKitGTK + fcitx5 下掩码密码框吞按键的问题
   （本项目已将密码框改为"文本框 + `-webkit-text-security: disc`"圆点伪装，双保险）；
2. `WEBKIT_DISABLE_DMABUF_RENDERER=1`——规避 AMD + Wayland 上 DMABUF 渲染器的视频挂死；
3. `RUST_LOG=info`——后端日志可见（完整日志在 `~/.local/share/MCTier/mctier.log`）。

### 第三步：TUN 能力授权（仅首次）

首次创建/加入大厅时，应用会通过 **pkexec**（polkit 图形授权框）为提取出的
`easytier-core` 执行一次 `setcap cap_net_admin,cap_net_raw+ep`。
此后普通用户运行不再弹窗；仅当二进制被重新提取（更新）时需重新授权一次。

## 技术实现要点

对应上游关注的几处平台边界，与本分支的实际落点：

- **EasyTier / TUN 权限模型**：应用本体与 easytier 进程**全程普通用户运行**。
  创建 TUN 所需能力通过**文件能力（setcap）**授予 easytier-core 二进制，启动前由
  `linux_platform::ensure_easytier_tun_capability` 做 `getcap` 预检，缺失才请求 pkexec。
  未动用 nftables/iptables。孤儿进程清理用 `pkill -9 -f easytier-core`。
- **`include_bytes!` 平台切分边界**：以 `#[cfg(windows)] / #[cfg(not(windows))]` 为界——
  Windows 侧保留原 5 个文件不动；Linux 侧只内嵌
  `resources/binaries/linux/{easytier-core,easytier-cli}`；三个 DLL 的获取函数整体
  `#[cfg(windows)]`（Linux 走内核 TUN 无此依赖）；提取函数补 `#[cfg(unix)]` chmod 755；
  平台文件名收敛为 `EASYTIER_CORE_FILE / EASYTIER_CLI_FILE` 常量。
- **音频**：PipeWire（经 pipewire-pulse 兼容层）。麦克风 = WebKitGTK getUserMedia
  → GStreamer pulsesrc；系统回环（AEC 参考）= 默认输出的 `.monitor` 源经
  `parec --format=float32le` 子进程采集，事件结构（768 帧/块 base64 PCM）与
  WASAPI 版逐字段对齐。
- **Wayland**：屏幕共享"查看端"为纯 WebRTC 接收；本机被控的键鼠注入用 **uinput 双设备**
  （REL 鼠标 + ABS 触摸绝对定位，RustDesk 同方案），未走 xdg-desktop-portal，
  与合成器无关；logind 对活动会话用户的 `/dev/uinput` ACL 天然放行，无需提权。
  已修复 tao 在 Wayland 下的一个竞态：`visible(false)` 窗口在 GTK realize 前调用
  `set_ignore_cursor_events` 会 `unwrap()` panic（弹幕/HUD 窗口进大厅即闪退），
  修法是先 `show()` 完成 realize 再设穿透。

## 验证记录

- **组网（真机）**：创建大厅 → `tun device ready. dev: MCTier_Net` → 虚拟 IP
  `10.126.126.1/24` → `ping` 通 → `easytier-cli peer` 显示 p2p 直连公共节点
  （261ms / 0% 丢包）→ 退出大厅资源干净回收。手机官方 APK 同大厅互连。
- **独立链路**：无特权基线（EasyTier 静默跳过 TUN，佐证权限模型）→ setcap 后完整链路复测。
- **测试**：前端 34 用例 + Rust 133 用例全绿；顺带修正上游遗留的
  `test_extract_ip_edge_cases` 两处与实现矛盾的期望（上游 CI 不跑 cargo test，故未暴露）。
- **待补**：连麦有声 / 屏幕画面 / 远控实测——正随自建 WebKit 引擎推进，完成后在此更新。

## 已知问题与取舍

1. WebKitGTK 无 WebRTC 的解法是"自建引擎"，WebKit 大版本更新时需要重新构建。
2. 掩码密码输入框替换为"文本框 + `-webkit-text-security: disc`"组件
   （`MaskedTextInput`）：WebKitGTK + fcitx5 的 `type=password` 字段吞按键，
   文本框伪装可完全绕开。上游如遇同类反馈可参考。
3. 聊天回车发送已补 IME 组合保护（`isComposing` / `keyCode 229`）——
   中文输入法确认候选词的回车会误发空消息，这在 WebView2 上同样可能触发，
   建议上游一并吸收。
4. `detect_security_software` 在 Linux 上返回空列表（杀软扫描是 Windows 语义，
   保留空实现并日志说明，不打算伪装）。

## 上游与许可

- 上游：[pmh1314520/MCTier](https://github.com/pmh1314520/MCTier)
  （Windows / Android 构建下载、完整文档、赞助渠道均在上游）。
- 本分支继承上游全部许可条款（自定义源码可得非商业许可 + EasyTier LGPL-3.0 等，
  详见上游 [LICENSE](LICENSE) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)）；
  Linux 适配新增代码同样遵循该许可。
- Linux 侧 EasyTier 二进制来自 EasyTier 官方 Release（LGPL-3.0），不入库，构建时获取。
