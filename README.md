# PaperBridge

项目地址：

```text
https://github.com/chushanxiaodaoshi/PaperBridge.git
```

PaperBridge 是一个面向论文初学者的论文理解与讲解视频生成系统。

它可以把一篇论文 PDF 转换成：

- 结构化论文分析
- 段落级 evidence 索引
- grounded PPT 课件
- 中文讲解稿
- Edge TTS 讲解音频
- 带字幕的讲解视频

目前项目提供 Gradio 界面，并支持使用 PyInstaller 打包成 Windows 桌面窗口程序。

---

## 1. 当前流程概览

核心流程：

```text
论文 PDF
↓
解析论文文本
↓
大模型结构化分析
↓
构建段落 evidence 索引
↓
规划 grounded slides
↓
修复 evidence 对齐
↓
优化 PPT 文案风格
↓
生成术语解释
↓
生成 PPT
↓
生成中文讲解稿
↓
优化口播稿
↓
Edge TTS 生成音频
↓
LibreOffice 将 PPT 转 PDF，再由 PyMuPDF 渲染为图片
↓
FFmpeg 合成带字幕讲解视频
```

也就是说：

- PPT 是主要课件输出；
- 视频画面来自 PPT 渲染结果；
- 合成视频需要 `ffmpeg / ffprobe / LibreOffice`；
- 打包版会在启动页面顶部检查这些运行环境。

---

## 2. 项目结构

推荐源码目录结构：

```text
PaperBridge/
├── app.py
├── src/
│   ├── pdf_parser.py
│   ├── main.py
│   ├── agents.py
│   ├── llm_client.py
│   ├── paragraph_indexer.py
│   ├── grounded_slide_planner.py
│   ├── fix_grounded_evidence.py
│   ├── style_refiner.py
│   ├── term_explainer.py
│   ├── ppt_generator.py
│   ├── narration_generator.py
│   ├── lecture_narration_refiner.py
│   ├── tts_generator.py
│   ├── video_generator.py
│   ├── project_namer.py
│   └── prompt_manager.py
├── prompts/
├── input/
├── outputs/
├── tools/
│   ├── ffmpeg/
│   │   └── bin/
│   │       ├── ffmpeg.exe
│   │       └── ffprobe.exe
│   └── LibreOffice/
│       └── App/
│           └── libreoffice/
│               └── program/
│                   └── soffice.exe
├── requirements.txt
├── process.txt
└── README.md
```

其中：

- `input/`：用户上传或手动放入的论文 PDF；
- `outputs/`：中间结果和最终输出；
- `tools/`：本地外部工具，不建议提交到 Git；
- `dist/`：PyInstaller 打包产物，不建议提交到 Git。

建议 `.gitignore` 至少包含：

```gitignore
build/
dist/
*.spec

input/
outputs/
tools/

.env
__pycache__/
*.pyc
```

---

## 3. Python 环境配置

推荐使用 Python 3.10：

```bash
conda create -n paperbridge-build python=3.10 -y
conda activate paperbridge-build
pip install -r requirements.txt
```

---

## 4. 大模型 API 配置

PaperBridge 使用 OpenAI-compatible Chat Completions 接口。

可以在页面顶部填写：

```text
LLM_API_KEY
LLM_BASE_URL
LLM_MODEL
```

默认 Base URL：

```text
https://dashscope.aliyuncs.com/compatible-mode/v1
```

默认模型名：

```text
qwen-plus
```

也可以在 `.env` 中配置：

```env
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
```

注意：不要把 `.env` 或自己的 API Key 提交到 GitHub。

---

## 5. 外部工具要求

### 5.1 ffmpeg / ffprobe

用于：

- TTS 音频转码；
- 音频时长检测；
- 视频片段合成；
- 字幕烧录。

推荐放在：

```text
tools/ffmpeg/bin/ffmpeg.exe
tools/ffmpeg/bin/ffprobe.exe
```

验证：

```cmd
tools\ffmpeg\bin\ffmpeg.exe -version
tools\ffmpeg\bin\ffprobe.exe -version
```

### 5.2 LibreOffice / soffice

用于：

- 将生成的 PPTX 转换成 PDF；
- 后续由 PyMuPDF 将 PDF 每页渲染成图片。

推荐放在：

```text
tools/LibreOffice/App/libreoffice/program/soffice.exe
```

验证：

```cmd
tools\LibreOffice\App\libreoffice\program\soffice.exe --version
```

如果不想把 LibreOffice 放进 `tools`，也可以让用户自己安装 LibreOffice。程序会尝试查找：

```text
tools/LibreOffice/App/libreoffice/program/soffice.exe
tools/LibreOffice/program/soffice.exe
C:\Program Files\LibreOffice\program\soffice.exe
C:\Program Files (x86)\LibreOffice\program\soffice.exe
PATH 中的 soffice / libreoffice
```

---

## 6. 启动 Web / 桌面界面

源码环境运行：

```cmd
python app.py
```

打包桌面版运行：

```cmd
dist\PaperBridge\PaperBridge.exe
```

如果使用桌面版 `pywebview` 窗口，默认会打开 PaperBridge 小窗口；关闭窗口后后台服务也会退出。

如果要用浏览器调试：

```cmd
python app.py --browser
```

---

## 7. 使用方式

### 方式 A：通过界面上传 PDF

1. 启动 `python app.py`；
2. 在页面顶部查看运行环境检查；
3. 填写大模型 API Key；
4. 拖入论文 PDF；
5. 保持默认步骤全选；
6. 点击“开始生成”。

生成结果会在右侧下载区显示，同时保存在 `outputs/` 中。

### 方式 B：手动把 PDF 放进 input

也可以手动把论文 PDF 放入：

```text
input/
```

如果没有在界面上传新 PDF，而是直接运行第 1 步，程序会从 `input` 目录中选择**最新修改的 PDF** 进行解析。

解析完成后，输入 PDF 会按项目名重命名，例如：

```text
input/RLAC_paper.pdf
```

---

## 8. 输出文件

常见输出包括：

```text
outputs/paper_text.txt
outputs/paper_analysis.json
outputs/paragraph_index.json
outputs/grounded_slides.json
outputs/narration.json
outputs/narration.md
outputs/audio/
outputs/pdf/
outputs/slide_images/
outputs/video_segments/
outputs/subtitles/
```

最终输出会按项目名命名，例如：

```text
outputs/RLAC_PaperBridge_Slides.pptx
outputs/RLAC_PaperBridge_Video.mp4
```

---

## 9. 单独运行脚本

如果通过 `python app.py` 启动，app 会自动给子进程配置 `tools` 路径。

如果你直接运行脚本，例如：

```cmd
python src\tts_generator.py
python src\video_generator.py
```

需要先设置环境变量：

```cmd
set PATH=%CD%\tools\ffmpeg\bin;%PATH%
set SOFFICE_PATH=%CD%\tools\LibreOffice\App\libreoffice\program\soffice.exe
```

然后再运行脚本。

---

## 10. 打包 Windows 桌面版

打包前确认：

```cmd
python -m py_compile app.py
python -m py_compile src\video_generator.py
python -m py_compile src\tts_generator.py
python -m py_compile src\project_namer.py
```

清理旧产物：

```cmd
rmdir /s /q build
rmdir /s /q dist
del /q PaperBridge.spec
```

打包：

```cmd
pyinstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --name PaperBridge ^
  --add-data "src;src" ^
  --add-data "prompts;prompts" ^
  --add-data "process.txt;." ^
  --collect-all gradio ^
  --collect-all gradio_client ^
  --collect-all safehttpx ^
  --collect-all groovy ^
  --collect-all fastapi ^
  --collect-all starlette ^
  --collect-all uvicorn ^
  --collect-all pydantic ^
  --collect-all pydantic_core ^
  --collect-all anyio ^
  --collect-all aiofiles ^
  --collect-all httpx ^
  --collect-all httpcore ^
  --collect-all websockets ^
  --collect-all python_multipart ^
  --collect-all huggingface_hub ^
  --collect-all jinja2 ^
  --collect-all markupsafe ^
  --collect-all yaml ^
  --collect-all orjson ^
  --collect-all pandas ^
  --collect-all numpy ^
  --collect-all edge_tts ^
  --collect-all aiohttp ^
  --collect-all openai ^
  --collect-all dotenv ^
  --collect-all pptx ^
  --collect-all fitz ^
  --collect-all webview ^
  --hidden-import=webview.platforms.edgechromium ^
  --hidden-import=webview.platforms.winforms ^
  --hidden-import=fitz ^
  --hidden-import=pymupdf ^
  --hidden-import=frontend ^
  --hidden-import=tools ^
  app.py
```

打包完成后，把 `tools` 复制到发布目录：

```cmd
xcopy /E /I /Y tools dist\PaperBridge\tools
```

验证：

```cmd
dist\PaperBridge\tools\ffmpeg\bin\ffmpeg.exe -version
dist\PaperBridge\tools\ffmpeg\bin\ffprobe.exe -version
dist\PaperBridge\tools\LibreOffice\App\libreoffice\program\soffice.exe --version
dist\PaperBridge\PaperBridge.exe
```

发布时压缩整个文件夹：

```cmd
powershell Compress-Archive -Path dist\PaperBridge -DestinationPath PaperBridge-Windows.zip -Force
```

不要只发 `PaperBridge.exe`，必须发送整个 `dist\PaperBridge` 文件夹压缩包。

---

## 11. 目前依赖边界

生成 PPT、讲解稿：

```text
需要 Python 依赖 + 大模型 API
```

生成音频：

```text
需要 Edge TTS 网络访问 + ffmpeg
```

合成视频：

```text
需要 ffmpeg + ffprobe + LibreOffice
```

如果运行环境缺少工具，app 启动页会显示检查结果；用户勾选相关步骤时也会提前报错。

---

## 12. 当前局限

- 结果质量依赖大模型输出；
- PPT 版式仍然是模板式生成；
- 视频生成依赖 LibreOffice 对 PPT 的渲染效果；
- Edge TTS 需要网络访问；
- 目前主要面向 Windows 打包演示，Linux/macOS 仍建议通过源码运行。
