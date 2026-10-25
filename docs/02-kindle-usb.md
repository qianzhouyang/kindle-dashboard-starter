# Kindle 准备与 USB 显示

## 先核对设备

记录自己的型号、固件、电池状态，并备份书籍与需要保留的资料。
本项目设备脚本只面向 PW3 的 1072×1448 帧缓冲；其他型号不能只改图片尺寸就视为兼容。

尚未越狱的设备先读本包的 [PW3 越狱与基建实战指南](JAILBREAK_AND_BASE_SETUP.md)，
再通过其中的上游入口按自己的型号和固件选择路径。越狱可能包含设备重置；本教程不自动执行越狱、清空或 OTA 改动。
不要把某台 PW3 的旧步骤复制到不同固件。

继续本节前，应已有适配该固件的越狱底座、KUAL、USBNetwork、可用的 `eips` 或 `fbink`。
在电脑安装自己的 Windows OpenSSH 客户端；用 `ssh -V`、`scp` 检查可执行文件。
USBNetwork 的下载、驱动、切换方式以所安装版本的说明为准；没有网卡时先处理驱动，不是反复尝试 SSH。

## 建立自己的 SSH 连接

USBNetwork 模式与 U 盘模式不同。按 USBNetwork 自带文档核对 Kindle USB 地址、电脑地址和子网；
不能把网上教程的地址当作你设备的实际地址。Wi-Fi SSH 不属于本教程的必要条件。

在 PowerShell 生成**自己专用**的密钥（已有同名文件时不要覆盖）：

```powershell
ssh-keygen -t ed25519 -f "$HOME/.ssh/kindle_dashboard_ed25519" -C "kindle-dashboard"
```

将 `.pub` 公钥按 USBNetwork 文档追加到设备的授权公钥文件，保留原有内容。
私钥留在电脑；不要复制到 Kindle 或提交到仓库。
控制台使用非交互 SSH，带口令的密钥需提前加入可用的 ssh-agent。

以下占位符都要替换。首次连接使用独立 known_hosts 文件；先通过可信 USB/设备侧信息核对指纹，
再接受保存。不要跳过主机指纹检查，也不要盲目覆盖发生变化的指纹。

```powershell
ssh -i "$HOME/.ssh/kindle_dashboard_ed25519" -o UserKnownHostsFile="$HOME/.ssh/kindle_dashboard_known_hosts" root@YOUR_KINDLE_USB_IP
```

确认登录后 `exit`。把 `config/device.example.json` 复制到**正在使用的数据目录**的 `device.json`。
默认目录可这样准备：

```powershell
$dataDir = Join-Path $HOME '.kindle-dashboard-starter'
New-Item -ItemType Directory -Force -Path $dataDir
Copy-Item config/device.example.json (Join-Path $dataDir 'device.json')
```

如果上一步已指定 `KINDLE_DASHBOARD_DATA_DIR`，改用那个目录。
编辑 `device.json`：填自己的 `host`，核对两个 SSH 路径，把 `enabled` 改为 `true`。
JSON 的 Windows 路径请使用 `/`，或者双写反斜杠；示例的 `~/` 也支持。
控制台强制校验已有主机指纹，只使用指定身份文件；不会自动扫描/信任新设备。

## 安装看板脚本

先退出现有看板。如果设备上已有 `/mnt/us/dashboard` 或同名 KUAL 扩展，
先复制备份；不要把这套教程当成对已有安装的自动升级器。

在 Kindle 的可见 USB 存储根目录准备：

```text
dashboard/
  refresh.sh
  power-cycle.sh
  watch_power.sh
extensions/
  dashboard/
    config.xml
    menu.json
    bin/
      start.sh
      start-auto.sh
      stop.sh
```

对应文件来自本项目的 `scripts/` 和 `scripts/extensions/dashboard/`。
完整复制扩展目录，保持 `.sh` 为 LF 换行。安全弹出存储后，按 USBNetwork 文档切到 USB 网络模式。
登录 Kindle，给自己的安装文件加执行权限：

```sh
chmod +x /mnt/us/dashboard/refresh.sh /mnt/us/dashboard/power-cycle.sh /mnt/us/dashboard/watch_power.sh
chmod +x /mnt/us/extensions/dashboard/bin/*.sh
```

如果习惯 SCP，新版 OpenSSH 向旧 USBNetwork 传文件可能需要 `scp -O`（旧 SCP 协议）；
本地控制台已使用该选项。不要关闭主机指纹检查来解决文件传输问题。

## 第一次显示与恢复

1. 电脑控制台先预览并保存自己的图片。
2. USB 已连接时点击“立即推送 · USB”。
3. 核对 Kindle 上的文字、朝向、完整边缘；控制台命令成功仍需要肉眼确认。
4. 短按并释放电源键，核对原生阅读画面与触摸恢复。
5. 原生界面打开 KUAL，选择 `Dashboard → 显示缓存看板 (Offline)`。
6. 拔掉 USB 再验证缓存显示和短按返回阅读。

缓存图片位于 `/mnt/us/dashboard/dashboard.png`；缓存模式不会让时钟或天气自动更新。
控制台“恢复阅读”或以下设备命令可请求退出看板：

```sh
/mnt/us/dashboard/refresh.sh --restore
/mnt/us/dashboard/refresh.sh --status
```

不要把“停止整个 GUI 再冷启动”当成正常切换流程。正常脚本会保存原画面并暂停/恢复原有 GUI 进程。
切换未通过时先停在本节，不继续配置自动联网。原始安装备份是回滚依据；
卸载前先恢复阅读，再移走自己添加的扩展与脚本，保留自己需要的图片和日志副本。
