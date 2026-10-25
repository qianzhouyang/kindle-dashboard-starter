# Kindle PW3 越狱与基建实战指南（脱敏修订版）

适用案例：Kindle Paperwhite 3（第七代），固件 **5.16.2.1.1**，Windows 电脑和 Micro-USB 数据线。
本页整理项目原有实战记录，修正旧流程并移除个人路径、主机和网络信息。
上游资料核对日期：2026-10-25；这是特定设备路径，不是所有 Kindle 的统一操作方法。

已完成越狱、KUAL、USBNetwork 和独立 SSH 的读者可直接进入
[USB 显示与恢复阅读](02-kindle-usb.md)。电脑端可先按 [README](../README.md) 离线试用。

## 1. 开始前：确认型号、固件与备份

在设备设置中记录自己的型号、固件版本；序列号和账号信息只存本地，不放进分享截图。
PW3 的设备图像为 1072×1448；看板横屏通过电脑软件旋转生成，不靠自动方向感应。
电脑运行渲染和控制台，Kindle 运行显示脚本，不需要在 Kindle 上安装本项目的 Python 环境。

**LanguageBreak 会删除设备内容。** 先备份需要保留的书籍、笔记及其他文件，抽查备份可读；
移除锁屏密码、保持飞行模式，充分充电，并确认数据线能稳定传输文件。
操作人应明确接受本次数据清空，再进入该流程。尚未完成备份时停在准备阶段。

先用 [Kindle Modding 的路径选择器](https://kindlemodding.org/jailbreak-wizard.html)
核对适合自己设备的路径。LanguageBreak 的上游范围为固件不高于 5.16.2.1.1；
本指南的实战案例仅为上述 PW3。不同型号或固件应重新选路，不盲目升级或降级。

## 2. 下载与准备

从维护者入口获取软件，阅读压缩包内的说明；下载文件保留在自己的电脑上。
本分享包不捆绑越狱载荷、厂商固件、驱动或第三方二进制工具。

| 组件 | 获取与用途 |
| --- | --- |
| LanguageBreak 与匹配 Hotfix | [上游项目](https://github.com/notmarek/LanguageBreak)、[Release](https://github.com/notmarek/LanguageBreak/releases/latest)；本轮核对 Release 指向 1.0.2.1 |
| MRPI、KUAL Booklet、USBNetwork | [NiLuJe 维护者下载入口](https://www.mobileread.com/forums/showthread.php?t=225030)；按设备和固件选择适用构建 |
| KUAL / MRPI 安装说明 | [原项目所用 Booklet 路径的说明](https://kindlemodding.gitbook.io/kindlemodding/post-jailbreak/installing-kual-mrpi) |
| USBNetwork 说明 | [维护者主题](https://www.mobileread.com/forums/showthread.php?t=186645)；读取其中 USBNetwork 部分和下载包内 README，不采用该主题早期固件的越狱方法 |

解压时保留隐藏文件、目录结构和 LF 换行。不要把整个源码仓库当成 Release 载荷；
也不要把面向不同固件/架构的 KUAL、MRPI、USBNetwork 版本混装。
如果当前上游推荐其他底座或安装器，完整跟随对应路径，不把其中一半拼到本例。

## 3. LanguageBreak：关键顺序与 Hotfix

执行时将 [上游安装原文](https://github.com/notmarek/LanguageBreak#installation) 放在手边。
以下是操作检查点，菜单、特殊手势与异常恢复以该原文为准：

1. 搜索 `;enter_demo` 后重启；跳过联网，依上游演示设置进入主界面。
2. 搜索 `;demo`，进入侧载内容菜单，连接电脑；第一次复制 Release 中 `LanguageBreak` 目录的**内容**到设备根目录，包含隐藏项。
3. 安全弹出、拔线，回到演示配置，选择转售设备并确认。
4. 出现按电源键的提示时立即接回电脑；**第二次复制同一批内容**，完成写入并弹出后才重启。这一步有时序要求。
5. 语言页面按上游指示选择简体中文，等待载荷运行和重启。
6. 按上游 Hotfix 段落启用演示模式 USB，把匹配语言的 Hotfix 放到根目录，通过设置里的设备更新入口安装。

不要用“直接在普通语言设置里切换中文”替代以上过程。
Hotfix 安装结束后按上游验证方法检查；若仍有演示/受管理状态，
按其对应注册状态的分支处理，别把通用恢复出厂操作当作下一步。
Hotfix 也不能替代后续 OTA 防护。

## 4. 安装 MRPI 与 KUAL Booklet

以下为本案例采用的传统 Booklet 路径。包名随版本变化，以实际下载说明为准：

1. 在设备可见 USB 存储根目录合并放入 MRPI 的 `extensions/` 和 `mrpackages/`。
2. 将适配固件的 KUAL Booklet **安装** `.bin` 放入 `mrpackages/`，不选卸载包。
3. 安全弹出并拔线，在 Kindle 搜索栏输入 `;log mrpi` 启动安装。
4. 检查安装输出/日志，并实际打开书库中的 KUAL；只有文件被复制不算安装通过。

若安装失败，先核对构建、目录层级、剩余空间和 Hotfix 状态。
不要把重复复制文件或只看到 KUAL 图标当成验收；至少确认 KUAL 能打开并显示菜单。
此阶段保持设备原生阅读可用。

## 5. USBNetwork、Windows 驱动与自己的 SSH

### 安装和切换模式

从对应 USBNetwork 包选正确的安装 `.bin`，按其 README 用 MRPI 安装，
再检查生成的 `usbnet/` 目录和安装日志。只需要 USB SSH；不必开启 Wi-Fi SSH 或开机自动启动。
不要照抄原始记录中与无线 SSH 有关的配置。

USB 大容量存储与 USB 网络是两种模式。在本例传统 USBNetwork 中，搜索 `;un`
可切换模式，也可用相应 KUAL 菜单；以下载版本的说明为准。
切换后确认电脑看到的是磁盘还是网卡，不把 `;ud` 当成所有版本通用的返回命令。

### Windows 网卡与 IPv4

1. 设备管理器检查插拔 USB 前后的新设备及硬件 ID，定位 Kindle 的 USB 网络设备。
2. 已正确出现网络适配器时不必换驱动；未知设备或串行设备需核对包内 Windows 驱动说明。
3. 原项目曾通过 RNDIS 驱动完成连接，但不把某个厂商驱动视为所有 Windows 的必选项；
   不关闭驱动签名检查，也不对硬件 ID 不匹配的设备强制安装。
4. 按自己的 USBNetwork 配置核对 Kindle 地址、电脑地址、子网掩码，记录为
   `YOUR_KINDLE_USB_IP`、`YOUR_PC_USB_IP`、`YOUR_USB_NETMASK`。
5. 如需手工 IPv4，只修改对应 USB 网卡；电脑与 Kindle 地址须不同且处在同一子网。
   这种直连通常不需要默认网关或 DNS，不覆盖电脑日常联网网卡的设置。

检查电脑侧配置可运行只读命令：

```powershell
Get-NetAdapter
Get-NetIPConfiguration
Test-NetConnection -ComputerName YOUR_KINDLE_USB_IP -Port 22
```

端口通仅说明 TCP 可达；还需核验设备身份和自己的密钥认证。

### 配置专用密钥并验证

完整命令、known_hosts 指纹核验、公钥安装和 `device.json` 设置见
[USB 教程：建立自己的 SSH 连接](02-kindle-usb.md#建立自己的-ssh-连接)。
使用自己的密钥和已核验指纹；不复用任何人的私钥或已记录的设备指纹。
手工 SSH 登录后，以下命令用于读取设备情况：

```sh
uname -a
command -v eips
command -v lipc-get-prop
lipc-get-prop com.lab126.powerd flIntensity
```

核对设备和工具后退出登录。SSH 成功才进入看板部署；未建立连接时，
先区分线缆、USB 模式、驱动、子网、认证和指纹错误。

## 6. 底层显示与切换：使用当前脚本

设备使用物理尺寸 PNG；`eips` 是本例刷屏路径，FBInk 可作为适配设备的辅助工具，
不是本分享版必须预装的第二套显示引擎。项目不分发这些工具的二进制文件。

**以当前 `scripts/refresh.sh`、`watch_power.sh`、`power-cycle.sh` 为实现依据。**
正常切换保存原画面、暂停原有 GUI 进程，退出时恢复画面并继续进程；
按键监听识别按下和释放，不是读取任意一条输入事件就退出。

不沿用旧文档中的全局 `killall -9`、停止整个 GUI 再冷启动、
“任意情况下必定恢复”等做法。前光由控制台以所选 0–24 档位请求设备设置，
不把旧文档的 4095 映射直接当成此属性的通用输入范围。

接着按 [USB 显示与恢复阅读](02-kindle-usb.md#安装看板脚本) 复制完整脚本、KUAL 扩展，
依次核对显示方向、阅读恢复、触摸和拔线缓存。
自动联网另读 [Wi-Fi / RTC 教程](03-auto-refresh.md)，先确认 OTA 防护再启动。
续航和整机电流没有本分享版的测量结果，不承诺周级续航。

## 7. 完成这一阶段的判据

- 已核对适用越狱路径，完成备份、载荷、匹配 Hotfix 和上游验证。
- KUAL 实际可打开，MRPI/USBNetwork 安装日志无待处理错误。
- Windows USB 网卡配置正确，专用密钥和已核验指纹能完成手工 SSH。
- 实际显示与恢复阅读按 USB 教程验收；自动联网作为后续独立阶段。

这份文档的整理与本地软件测试不代表朋友设备已经完成以上步骤。
遇到与上游说明不同的界面或失败日志，保留证据并先停在该步骤处理。
