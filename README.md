# PaperBridge

PaperBridge 是一个面向论文初学者的论文理解与讲解视频生成系统。

系统输入一篇论文 PDF，自动完成论文文本解析、结构化理解、段落级证据索引、Grounded PPT 规划、PPT 生成、中文讲解稿生成、语音合成和带字幕讲解视频合成。

它既可以作为 Web 应用使用，也可以通过源码脚本分步骤运行和调试。

---

## 1. 项目目标

很多初学者读论文时会遇到这些问题：

- 不知道论文到底在解决什么问题
- 看不懂前置知识
- 方法流程太抽象
- 公式和实验细节太密集
- 看完以后不知道该记住什么
- 使用大模型总结后，很难确认结论来自论文哪里

PaperBridge 的目标是把一篇论文转换成更适合学习的形式：

- 小白友好的论文总结
- 前置知识解释
- 推荐学习路径
- 段落级 evidence 引用
- 论文理解学习地图
- 方法流程图
- 专业术语解释
- 带 evidence 超链接的 PPT
- 中文讲解稿
- 中文语音讲解
- 带字幕讲解视频

---

## 2. 核心功能

1. PDF 文本解析：从论文 PDF 中提取文本，并尽量保留页码信息。
2. 论文结构化理解：调用大模型分析研究问题、贡献、方法、实验和结论。
3. 段落级 Evidence Grounding：将论文拆成 evidence blocks，每个 block 包含页码、段落编号、原文摘录、总结和关键词。
4. Grounded PPT 规划：根据论文分析和 evidence blocks 生成 PPT 页面规划。
5. PPT 文案风格优化：使用可编辑风格 Prompt，使页面文字更简洁、准确、克制。
6. 术语注释：自动识别专业术语并生成术语解释页。
7. Evidence 超链接：点击 PPT 中的 evidence 小卡片，可以跳转到 Evidence Appendix 页面。
8. 中文讲解稿生成：讲解稿不是照读 PPT，而是补充上下文和推理过程。
9. 口播稿优化与 TTS：将讲解稿优化成适合语音合成的课堂口播风格。
10. 视频合成：将 PPT 页面、语音和字幕合成为完整讲解视频。
11. Web 应用界面：支持输入 API Key、上传 PDF、选择音色、选择运行步骤、下载结果。
12. 安全 Prompt 编辑：只开放风格类 Prompt，隐藏 JSON 模板和字段结构，避免改坏生成流程。

---

## 3. 项目结构

    PaperBridge/
    ├── app.py
    ├── input/
    │   └── paper.pdf
    ├── outputs/
    │   ├── paper_text.txt
    │   ├── paper_analysis.json
    │   ├── paragraph_index.json
    │   ├── grounded_slides.json
    │   ├── narration.json
    │   ├── narration.md
    │   ├── audio/
    │   ├── pdf/
    │   ├── slide_images/
    │   ├── subtitles/
    │   ├── video_segments/
    │   ├── <PaperName>_PaperBridge_Slides.pptx
    │   └── <PaperName>_PaperBridge_Video.mp4
    ├── prompts/
    │   ├── defaults/
    │   ├── custom/
    │   └── prompt_manifest.json
    ├── src/
    │   ├── pdf_parser.py
    │   ├── llm_client.py
    │   ├── agents.py
    │   ├── paragraph_indexer.py
    │   ├── grounded_slide_planner.py
    │   ├── fix_grounded_evidence.py
    │   ├── style_refiner.py
    │   ├── term_explainer.py
    │   ├── ppt_generator.py
    │   ├── narration_generator.py
    │   ├── speech_style_refiner.py
    │   ├── tts_generator.py
    │   ├── video_generator.py
    │   ├── project_namer.py
    │   ├── prompt_manager.py
    │   └── prompt_extractor.py
    ├── requirements.txt
    ├── process.txt
    ├── .env.example
    ├── .gitignore
    └── README.md

---

## 4. 环境配置

建议使用 Python 3.10。

### 4.1 创建 conda 环境

    conda create -n paperbridge python=3.10 -y
    conda activate paperbridge

### 4.2 安装 Python 依赖

    pip install -r requirements.txt

如果还没有 requirements.txt，可以先安装：

    pip install gradio openai python-dotenv pymupdf python-pptx edge-tts

如果代码中仍保留 dashscope 相关导入，也需要：

    pip install dashscope

### 4.3 安装系统依赖

视频生成需要系统工具：

    sudo apt update
    sudo apt install -y libreoffice ffmpeg fonts-noto-cjk

用途说明：

- LibreOffice：将 PPT 转换为 PDF
- ffmpeg：合成音频、字幕和视频
- fonts-noto-cjk：保证中文字幕显示正常

---

## 5. API 配置与模型选择

PaperBridge 的推理部分默认使用 DashScope / 通义千问，但不局限于 Qwen。

系统通过 OpenAI-compatible 调用方式访问大模型。因此，只要模型服务兼容 OpenAI Chat Completions 风格接口，就可以通过修改 API Key、Base URL 和模型名称来切换模型。

### 5.1 Web 应用模式

如果使用 app.py 启动 Web 应用，用户不需要把 API Key 写入 .env。

直接在页面顶部的“大模型 API 设置”中填写：

    API Key
    Base URL
    模型名称

默认配置为：

    Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1
    模型名称: qwen-plus

如果使用默认 DashScope / 通义千问接口，一般只需要填写自己的 API Key。

也可以填写其他 OpenAI-compatible 服务，例如：

| 服务 | Base URL 示例 | 模型名示例 |
|---|---|---|
| DashScope / Qwen | https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus |
| OpenAI | https://api.openai.com/v1 | 填写你的账号可用模型名 |
| DeepSeek / OpenRouter / 本地 vLLM | 填写对应 OpenAI-compatible Base URL | 填写对应模型名 |

注意：PaperBridge 支持的是 OpenAI-compatible API，不是所有任意格式的大模型 API。  
如果某个服务商的接口格式完全不同，需要另外写 client adapter。

API Key 只会作为本次运行的环境变量传给后续脚本，不会显示在日志中。

### 5.2 源码脚本模式

如果不通过 Web 页面，而是直接运行源码脚本，可以使用 .env。

复制环境变量模板：

    cp .env.example .env

然后编辑 .env：

    DASHSCOPE_API_KEY=your_api_key_here
    QWEN_MODEL=qwen-plus
    QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

如果使用其他 OpenAI-compatible 服务，可以按实际情况改成对应的 Key、Base URL 和模型名称。

注意：.env 中包含 API Key，不要提交到 GitHub。

---

## 6. TTS 模型与音色说明

当前项目的 TTS 部分主要使用 Edge TTS。

Web 页面中用户可以选择不同中文音色，例如：

- zh-CN-YunyangNeural：男声，正式可靠，适合论文讲解
- zh-CN-YunxiNeural：男声，年轻自然
- zh-CN-YunjianNeural：男声，更有力量感
- zh-CN-XiaoxiaoNeural：女声，自然温和
- zh-CN-XiaoyiNeural：女声，较活泼

当前支持的是 TTS 音色选择，不是任意 TTS 服务商或任意 TTS 模型选择。

如果后续要支持 DashScope CosyVoice、OpenAI TTS 或其他 TTS 服务，需要在 tts_generator.py 中增加对应 provider adapter。

---

## 7. 方式一：直接运行 Web 应用

这是推荐使用方式。

### 7.1 启动

    python app.py

然后浏览器打开：

    http://localhost:7861

### 7.2 页面使用流程

1. 在页面顶部填写自己的 API Key、Base URL 和模型名称。
2. 上传论文 PDF。
3. 选择音色。
4. 可点击“试听音色”测试语音效果。
5. 选择执行步骤。
6. 点击“开始生成”。
7. 在日志区查看进度。
8. 生成完成后，在右侧下载 PPT 和视频。

### 7.3 API Key 缺失提示

如果选择了需要大模型的步骤，但没有填写 API Key，页面会弹出错误提示并停止运行。

需要大模型的步骤包括：

    2. 论文结构化分析
    3. 构建段落证据索引
    4. 规划 Grounded PPT
    5. 修复 Evidence 对齐
    6. 优化 PPT 文案风格
    7. 生成术语注释
    9. 生成讲解稿
    10. 优化口播稿

不需要大模型的步骤包括：

    1. 解析 PDF
    8. 生成 PPT
    11. 生成音频
    12. 合成视频

注意：不需要大模型的步骤虽然可以单独运行，但通常要求前面的中间文件已经存在。

---

## 8. 方式二：直接运行源码脚本

源码脚本模式适合调试、复现实验或单独修改某一步。

### 8.1 准备输入 PDF

把论文放到：

    input/paper.pdf

### 8.2 完整运行链路

按顺序运行：

    python src/pdf_parser.py
    python src/main.py
    python src/paragraph_indexer.py
    python src/grounded_slide_planner.py
    python src/fix_grounded_evidence.py
    python src/style_refiner.py
    python src/term_explainer.py
    python src/ppt_generator.py
    python src/narration_generator.py
    python src/speech_style_refiner.py
    python src/tts_generator.py
    python src/video_generator.py

---

## 9. 当前 Pipeline 说明

    用户打开 Web 页面
     ↓
    填写 API Key、Base URL、模型名称
     ↓
    上传论文 PDF
     ↓
    选择音色、选择执行步骤
     ↓
    pdf_parser.py
    提取论文文本，生成 paper_text.txt
     ↓
    main.py / agents.py
    问大模型：整篇论文讲了什么？
     ↓
    paper_analysis.json
     ↓
    paragraph_indexer.py
    问大模型：把论文拆成 paragraph-level evidence blocks
     ↓
    paragraph_index.json
     ↓
    grounded_slide_planner.py
    问大模型：根据论文分析和段落证据规划 10 页 Grounded PPT
     ↓
    grounded_slides.json
     ↓
    fix_grounded_evidence.py
    修复和补全 evidence 信息
     ↓
    style_refiner.py
    根据可编辑风格 Prompt 优化 PPT 文案
     ↓
    term_explainer.py
    提取专业术语，生成术语编号和解释
     ↓
    ppt_generator.py
    生成 PPT，并为 evidence 小卡片添加内部超链接
     ↓
    <PaperName>_PaperBridge_Slides.pptx
     ↓
    narration_generator.py
    生成中文讲解稿，不照读 PPT，而是补充解释逻辑
     ↓
    narration.json / narration.md
     ↓
    speech_style_refiner.py
    优化口播稿
     ↓
    tts_generator.py
    调用 Edge TTS，为每页讲解稿生成语音
     ↓
    video_generator.py
    PPT 转 PDF，PDF 转图片，图片 + 音频 + 字幕合成视频
     ↓
    <PaperName>_PaperBridge_Video.mp4

---

## 10. 主要输出文件

    outputs/paper_text.txt
    outputs/paper_analysis.json
    outputs/paragraph_index.json
    outputs/grounded_slides.json
    outputs/narration.json
    outputs/narration.md
    outputs/audio/
    outputs/<PaperName>_PaperBridge_Slides.pptx
    outputs/<PaperName>_PaperBridge_Video.mp4

---

## 11. Prompt 编辑说明

Web 应用中的 Prompt 编辑页面只开放风格类 Prompt，例如：

- PPT 文案风格
- 讲解稿风格
- 口播稿风格

JSON 模板、字段结构和系统流程相关 Prompt 不开放修改，避免破坏生成流程。

Prompt 编辑逻辑：

- 有自定义 Prompt 时，使用自定义版本。
- 没有自定义 Prompt 时，使用默认 Prompt。
- 文本框清空并保存时，自动回退默认 Prompt。
- 修改 Prompt 后，需要重新运行对应步骤才会生效。

示例：

    修改 PPT 文案风格：
    重新运行 6. 优化 PPT 文案风格
    再运行 8. 生成 PPT

    修改口播风格：
    重新运行 10. 优化口播稿
    再运行 11. 生成音频
    再运行 12. 合成视频

---

## 12. Evidence Grounding 设计

PaperBridge 的一个核心改进是 paragraph-level grounding。

系统不是直接让大模型自由生成 PPT，而是先把论文切成 evidence blocks，并为每个 block 保存：

- 段落编号
- 页码
- 章节猜测
- 原文摘录
- 中文总结
- 关键词
- 初学者理解难度

PPT 中的每个主要结论会尽量关联到论文原文中的 evidence block。

示例：

    [P21 | Page 4 | Method]
    Original: We align the simulator by fitting a small set of parameters...
    Summary: 本段说明系统如何通过参数拟合对齐仿真和真实机器人运动。

这样读者可以根据 Page 和 Original 回到论文中定位依据，减少大模型幻觉。

---

## 13. Evidence 超链接

生成的 PPT 中，Evidence 区域可以点击。

点击后会跳转到末尾的 Evidence Appendix 页面，查看对应段落的：

- 原文摘录
- 页码
- 段落编号
- 初学者解释

在放映模式下，可以点击返回按钮回到原页面。

这个设计让 PPT 从普通总结变成了可追溯的论文阅读材料。

---

## 14. 创新点总结

1. 多阶段论文理解 Agent 流程：将论文理解拆成结构化分析、证据索引、PPT 规划、讲解稿生成、视频合成等多个步骤。
2. 段落级 Evidence Grounding：每页 PPT 观点绑定到论文具体段落，提升可追溯性。
3. Evidence 超链接跳转机制：用户可以点击 evidence，跳转到 Evidence Appendix 查看原文和解释。
4. PPT 与讲解稿分离生成：PPT 负责视觉结构，讲解稿负责补充逻辑和上下文。
5. 端到端 PDF-to-Video：从论文 PDF 自动生成 PPT、讲解稿、语音、字幕和视频。
6. 术语注释机制：自动识别术语并生成解释页，降低初学者理解门槛。
7. 安全可编辑风格 Prompt：用户可以调节生成风格，但不能破坏 JSON 结构和字段 schema。

---

## 15. 常见问题

### Q1：为什么提示需要 API Key？

因为你选择的步骤中包含需要调用大模型的任务。请在页面顶部填写自己的 API Key。

### Q2：不填 API Key 能不能用？

可以，但只能运行不需要大模型的步骤，例如生成 PPT、生成音频、合成视频。前提是对应中间文件已经存在。

### Q3：为什么生成视频很慢？

视频合成需要经历 PPT 转 PDF、PDF 转图片、音频匹配、字幕生成和视频编码，耗时会比生成 PPT 更长。

### Q4：修改 Prompt 后会立即改变已有 PPT 吗？

不会。修改 Prompt 后，需要重新运行对应步骤，新的结果才会生效。

### Q5：生成的视频中文字幕乱码怎么办？

请确认已经安装中文字体：

    sudo apt install -y fonts-noto-cjk

### Q6：PPT 转 PDF 失败怎么办？

请确认已经安装 LibreOffice：

    sudo apt install -y libreoffice

### Q7：视频合成失败怎么办？

请确认已经安装 ffmpeg：

    sudo apt install -y ffmpeg

---

## 16. Web 部署说明

本项目默认适合本地运行或单人在线 Demo。

如果希望用户不用 pull 源码、直接点击网页使用，需要部署到服务器或云平台。

正式多人使用前，建议进一步加入：

- 每次任务独立工作目录
- 输出文件按 session 隔离
- 上传文件大小限制
- 并发任务限制
- 定期清理旧文件
- API Key 不落盘、不进日志
- 任务队列或后台任务管理

当前版本更适合作为：

    本地开源版 + 单用户 Web Demo

---

## 17. GitHub 提交说明

建议提交：

    app.py
    src/
    prompts/defaults/
    requirements.txt
    process.txt
    README.md
    .env.example
    .gitignore

不建议提交：

    .env
    input/paper.pdf
    outputs/
    *.mp4
    *.mp3
    *.wav
    *.pptx
    *.pdf
    __pycache__/

---

## 18. License

This project is for educational and course project purposes.
