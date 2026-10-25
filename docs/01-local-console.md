# 电脑安装与编辑

## 安装

Windows：Python 3.10 或更新版本，安装时勾选 Python 的 PATH 选项。
解压到普通文件夹，在该目录打开 PowerShell，执行 README 的三条命令。
直接调用 `.venv\Scripts\python.exe` 不需要修改 PowerShell 执行策略。
要复现本轮依赖版本，可将安装命令改为 `-m pip install -r requirements-lock.txt`；
锁定版本实测环境是 Windows / Python 3.12。

Linux / macOS（尚未实测）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python src/web_console.py --host 127.0.0.1 --port 8001
```

中文渲染需要中文字体。Windows 默认尝试微软雅黑；Linux 尝试 Noto Sans CJK，macOS 尝试 PingFang。
缺字体时设置 `KINDLE_DASHBOARD_FONT` 和 `KINDLE_DASHBOARD_FONT_BOLD` 为自己的字体绝对路径。
项目不分发操作系统字体。先查看预览中的中文是否正常，再传到设备。

## 日常操作

1. 选择猫咪、双历或节点示例模板。
2. 点击预览上的分区，选择文字、图片、时钟、天气、月历、进度或自定义指标。
3. 图片模块可选择工作猫、休息猫，或上传自己的 PNG/JPEG/WebP；支持等比留白与裁切填满。
4. “全局数据与设备参数”可调整进度、台词、横屏方向、前光和天气。
5. “刷新预览”只预览；“保存并发布”写入本机配置，供图片端点使用，不会上传 GitHub。
6. 打开 <http://127.0.0.1:8001/kindle-dashboard.png> 可保存物理屏尺寸的 PNG。
7. “立即推送 · USB”会先保存设置，再尝试连接设备；未配置设备时会明确报告未配置。

横屏网页预览为正常阅读方向；下载的设备 PNG 为 1072×1448，电脑看起来旋转属于正常现象。
Logo 朝向相反时在全局参数中切换 90°/270°。节点模板为竖屏，不使用横屏旋转。

## 天气

默认使用离线示例，图片上标注 `demo` / 示例。
要获取实际天气，展开全局参数，填写城市显示名、纬度和经度，切换到 Open-Meteo。
**只修改城市名不会自动查找坐标**。纬度 -90～90，经度 -180～180。
联网后会把坐标发送给 Open-Meteo；缓存按城市与坐标隔离，三小时更新一次。
请求失败时显示旧缓存并标注，或者显示获取失败，不会把示例温度冒充实时值。

天气图层显示数据获取时的电脑时间；时钟、日期使用电脑时区。跨时区使用时自行核对电脑时区。
天气来源和服务条件参见 [Open-Meteo 文档](https://open-meteo.com/en/docs)。

## 运行数据

默认目录：`~/.kindle-dashboard-starter/`，Windows 即当前用户目录下的同名文件夹。
内容包括 `console_config.json`、上传图片 `uploads/`、天气缓存 `weather/`、最近生成图片。
SSH 设置另放 `device.json`，网页状态 API 不返回此文件。

完全隔离的测试运行可在启动前设置：

```powershell
$env:KINDLE_DASHBOARD_DATA_DIR = Join-Path $PWD '.runtime'
.\.venv\Scripts\python.exe src/web_console.py --host 127.0.0.1 --port 8001
```

重启后读取相同目录，才能保留之前的设置与上传图片。停止控制台用 Ctrl+C。
