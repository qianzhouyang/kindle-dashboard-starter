# 开发与分享边界

必读 README、本页；修改设备脚本时按需读 USB/自动刷新教程。

## 本地验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/generate_examples.py
.\.venv\Scripts\python.exe scripts/check_share.py
.\.venv\Scripts\python.exe scripts/build_share.py
```

测试使用临时数据和模拟设备命令，不连接实际 Kindle。
HTTP 处理器通过内存请求/响应执行，不新增 TCP 监听或修改防火墙。
Shell 测试需要 POSIX shell；Windows 使用 Git Bash（自动查找常见安装位置），缺失时会明确跳过。
本地生成图和浏览器验证也不替代实机验收。

## 分享内容

`scripts/build_share.py` 采用文件/目录白名单导出 ZIP，先执行脱敏检查，生成 SHA-256。
不打包 `.git`、`.venv`、个人运行目录、日志、私钥、真实网络配置。
已生成的 `config/*.example.json` 和 `scripts/network.conf.example` 是占位符。
Public 仓库第一次提交也只用这份文件清单；不要把原项目的历史带过去。

未来每次从个人项目吸收功能时只复制所需代码，再重新检查示例数据、硬编码和图片内容。
`.gitignore` 不能清除已经提交的历史。本项目的扫描器是定向检查，不能替代人工审查，
尤其需要逐张检查新增图片，并检查是否出现新的个人标识与凭据格式。

## 数据与实现

- `starter_runtime.py`：独立数据目录、显式 SSH 配置、强制主机指纹校验。
- `weather.py`：默认无网络、按位置隔离缓存、失败与旧数据标记。
- `web_console.py`：本机编辑、远端只读图片、预览与保存、USB 命令。
- `render_*.py` / `dashboard_modules.py`：三种画布与分区渲染。
- `scripts/refresh.sh` 等：PW3 缓存/联网会话、按键退出和清理。

控制台不自动部署系统脚本、不注册后台服务、不修改系统安全配置。
网络模式由使用者按教程显式开启。实际端口/常驻服务改动须遵守使用者自己的主机管理规范。

依赖：[Pillow](https://github.com/python-pillow/Pillow)、
[lunar-python（MIT）](https://github.com/6tail/lunar-python)。
天气：[Open-Meteo](https://open-meteo.com/en/docs)，启用 live 才访问，不需要凭据。
本仓库不捆绑这些依赖的代码或系统字体。
