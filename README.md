# 智柜 V2026

柜体设计与参数空间编辑桌面应用（PySide6）。

## 环境要求

- Python 3.10 或 3.11（推荐 3.11）
- Windows / Linux / macOS

## 安装与运行

1. **获取完整源码**（任选其一）：

   ```bash
   git clone https://github.com/charoumiaoth2759-alt/zhigui.git
   cd zhigui
   ```

   或从 GitHub 下载 ZIP 后解压，**进入解压后的项目根目录**（该目录下应能看到 `main.py`）。

2. **安装依赖**：

   ```bash
   pip install -r requirements.txt
   ```

3. **启动**（必须在包含 `main.py` 的目录下执行）：

   ```bash
   python main.py
   ```

   Windows 也可双击同目录下的 `启动.bat`。

## 常见错误

### `can't open file '...\main.py': [Errno 2] No such file or directory`

当前工作目录里**没有** `main.py`，通常是因为：

- 只复制了部分子文件夹（如 `ui/`、`core/`），未包含项目根目录的 `main.py`；
- 在错误的父目录（例如桌面上的 `软件`）里运行，而实际项目在 `zhigui` 或 `zhigui-main` 子目录中；
- 尚未克隆/解压完整仓库。

**处理**：在资源管理器中打开项目，确认与 `requirements.txt` 同级存在 `main.py`，再在该目录打开终端执行 `python main.py`，或使用 `启动.bat`。
