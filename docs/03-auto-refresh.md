# 可选：Wi-Fi / RTC 自动刷新

仅在 USB 显示、缓存启动、短按退出都通过后进行。需要可达的电脑图像服务、
设备已连接自己的 Wi-Fi，以及适用于该设备的 OTA 屏蔽措施。
电脑关机、休眠、换 IP 或离开同一网络时，设备不能继续从它得到新图。

## 先确认 OTA 与设备前提

参考 [Kindle Modding 的 OTA 指南](https://kindlemodding.gitbook.io/kindlemodding/post-jailbreak/optional-disable-ota-updates-on-5.11%2B)。
按设备当前固件的上游步骤操作，先保存原文件及恢复方法。旧的临时目录方法不能视为适用于所有固件。
本项目不会自动重命名或删除系统文件。

当前 `power-cycle.sh` 的严格检查要求：

- `/usr/bin/otaupd`、`/usr/bin/otav3`、`/etc/upstart/otaupd.conf`、`/etc/upstart/otav3.conf` 均不存在于原始路径；
- `otaupd` / `otav3` 没有运行中的进程；
- `/mnt/us/dashboard/ota-block.sha256` 存在且 SHA-256 校验通过。

清单必须对应**这台设备实际备份/改名后的文件**，不能从别人的设备复制。
在完成适配的 OTA 屏蔽后，确认四个实际保存路径，并用以下模式生成清单：

```sh
# 每个占位符替换为自己设备上确认过的、实际存在的备份/改名路径。
sha256sum /ACTUAL_PATH/otaupd_saved /ACTUAL_PATH/otav3_saved /ACTUAL_PATH/otaupd_conf_saved /ACTUAL_PATH/otav3_conf_saved > /mnt/us/dashboard/ota-block.sha256
sha256sum -c /mnt/us/dashboard/ota-block.sha256
```

如果自己的固件没有这些文件，或所用上游方法与此检查不匹配，先使用缓存模式；
不要伪造空清单或删除检查来强行联网。该 starter 未证明其他 OTA 布局兼容。

## 开放图片服务

停止原控制台，按需启动：

```powershell
.\.venv\Scripts\python.exe src/web_console.py --host 0.0.0.0 --port 8001
```

本机编辑仍用 <http://127.0.0.1:8001>。远端仅能 GET `/kindle-dashboard.png` 或 `/dashboard.png`；
网页、配置、上传和设备操作接口拒绝非本机访问。
图片本身没有鉴权，因此只在自己的可信局域网开放；不做公网端口转发。
如系统防火墙阻止访问，按自己的主机管理规则只允许所需私有网络/来源，勿直接关闭防火墙。

先用同一 Wi-Fi 的另一台设备访问 `http://YOUR_SERVER_LAN_IP:8001/kindle-dashboard.png`，确认返回图片。
`127.0.0.1` 在 Kindle 上指 Kindle 自己，不能填作电脑地址。

## 填写设备配置并启动

复制 `scripts/network.conf.example` 为设备 `/mnt/us/dashboard/network.conf`，
将 `YOUR_SERVER_LAN_IP` 换成自己的电脑局域网地址。默认 `INTERVAL=300`，即五分钟。
这是纯文本键值文件，不是 Shell 脚本；请保持 LF。

在 KUAL 选择 `Dashboard → 启动自动看板 (Auto Dashboard)`，或在设备执行：

```sh
/mnt/us/dashboard/refresh.sh --start-auto
/mnt/us/dashboard/refresh.sh --status
```

联网和下载均有限时。图片必须是非隔行、8 位灰度或 RGB 的 1072×1448 PNG，且不超过 2 MiB。
失败时保留缓存；设备代码控制本轮 Wi-Fi 关闭后才尝试睡眠。
USB 供电/网络与纯电池采用不同等待路径；不要把插线等待当作 RTC 休眠验证。

## 自己设备的验收

观察 `refresh.log`：下载成功、Wi-Fi 关闭、RTC 设闹钟、进入/退出休眠，
以及短按退出后的原 Wi-Fi 状态恢复；与设备实际画面、时间和按键结果交叉核对。
至少验证几个完整电池周期，再做长时间稳定性/续航测试。
拔掉网络检查保留缓存，恢复网络检查后续更新。退出用短按电源或 `--restore`。

本地测试使用模拟文件与命令，不能证明自己设备的耗电、挂起、Wi-Fi 或按键已通过。
