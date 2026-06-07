# PaperBridge

PaperBridge 是一个面向论文小白的论文理解与讲解视频生成系统。

系统输入一篇论文 PDF，自动完成论文文本解析、结构化理解、段落级证据索引、PPT 规划、PPT 生成、中文讲解稿生成、语音合成和视频合成。

## 项目目标

很多初学者读论文时会遇到几个问题：

- 不知道论文到底在解决什么问题
- 看不懂前置知识
- 方法流程太抽象
- 公式和实验细节太密集
- 看完以后不知道该记住什么

PaperBridge 的目标是把一篇论文转换成更适合学习的形式：

- 小白友好的论文总结
- 前置知识解释
- 推荐学习路径
- 段落级证据引用
- 论文理解思维导图
- 方法流程图
- 中文 PPT
- 中文讲解稿
- 语音讲解
- 讲解视频

## 核心功能

1. PDF 文本提取  
2. 论文结构化理解  
3. 段落级 evidence block 构建  
4. 基于 evidence 的 PPT 内容规划  
5. 自动生成带证据引用的 PPT  
6. 自动生成中文讲解稿  
7. 自动生成中文语音  
8. 自动合成讲解视频  

## 项目结构

    PaperBridge/
    ├── input/
    │   └── paper.pdf
    ├── outputs/
    │   ├── paper_text.txt
    │   ├── paper_analysis.json
    │   ├── paragraph_index.json
    │   ├── grounded_slides.json
    │   ├── paperbridge_grounded_slides.pptx
    │   ├── narration.json
    │   ├── narration.md
    │   ├── audio/
    │   ├── pdf/
    │   ├── slide_images/
    │   └── paperbridge_lecture_video.mp4
    ├── src/
    │   ├── pdf_parser.py
    │   ├── llm_client.py
    │   ├── agents.py
    │   ├── paragraph_indexer.py
    │   ├── grounded_slide_planner.py
    │   ├── fix_grounded_evidence.py
    │   ├── ppt_generator.py
    │   ├── narration_generator.py
    │   ├── tts_generator.py
    │   └── video_generator.py
    ├── prompts/
    ├── requirements.txt
    ├── .env.example
    ├── .gitignore
    └── README.md

## 环境配置

创建 conda 环境：

    conda create -n paperbridge python=3.10 -y
    conda activate paperbridge

安装 Python 依赖：

    pip install -r requirements.txt

安装系统依赖：

    sudo apt update
    sudo apt install libreoffice ffmpeg fonts-noto-cjk -y

## API 配置

复制环境变量模板：

    cp .env.example .env

然后编辑 `.env`：

    DASHSCOPE_API_KEY=your_api_key_here
    QWEN_MODEL=qwen-plus
    QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

注意：`.env` 中包含 API Key，不要提交到 GitHub。

## 使用方法

先把论文 PDF 放到：

    input/paper.pdf

然后按顺序运行下面的脚本。

### 1. 提取 PDF 文本

    python src/pdf_parser.py

输出：

    outputs/paper_text.txt

### 2. 生成论文结构化分析

    python src/main.py

输出：

    outputs/paper_analysis.json

### 3. 构建段落级 evidence index

    python src/paragraph_indexer.py

输出：

    outputs/paragraph_index.json

每个 evidence block 会包含：

- paragraph_id
- page_start
- page_end
- section_guess
- source_excerpt
- summary_sentence
- keywords
- difficulty_for_beginner

### 4. 生成 grounded slide plan

    python src/grounded_slide_planner.py

输出：

    outputs/grounded_slides.json

### 5. 修复并补全 evidence

    python src/fix_grounded_evidence.py

这一步会把每页 PPT 中的 evidence 补全成：

    [P21 | Page 4 | Method]
    Original: We align the simulator by fitting a small set of parameters...
    Summary: 本段说明系统如何通过参数拟合对齐仿真和真实机器人运动。

### 6. 生成 PPT

    python src/ppt_generator.py

输出：

    outputs/paperbridge_grounded_slides.pptx

### 7. 生成中文讲解稿

    python src/narration_generator.py

输出：

    outputs/narration.json
    outputs/narration.md

### 8. 生成语音

    python src/tts_generator.py

输出：

    outputs/audio/

### 9. 合成讲解视频

    python src/video_generator.py

输出：

    outputs/paperbridge_lecture_video.mp4

## Evidence Grounding 设计

PaperBridge 的一个核心改进是 paragraph-level grounding。

系统不是直接让大模型自由生成 PPT，而是先把论文切成 evidence block，并为每个 block 保存页码、原文摘录和中文总结。

PPT 中的每个主要结论都会尽量关联到论文原文中的 evidence block。

示例：

    [P21 | Page 4 | Method]
    Original: We align the simulator by fitting a small set of parameters...
    Summary: 本段说明 PACE 通过拟合少量关键物理参数来缩小仿真与真实机器人之间的差距。

这样读者可以根据 Page 和 Original 回到论文中定位原文，减少大模型幻觉。

## 当前局限

- 结果质量依赖大模型输出。
- 有时模型会把 P 编号写进正文，而不是写进 JSON 字段，因此需要后处理脚本修复。
- PPT 布局仍然是模板式生成，美观程度有限。
- TTS 语音还不够像真人老师。
- 思维导图和方法图目前是简化可视化，不能完全替代人工设计。

## 后续改进方向

- 加入 critic-refiner 机制，自动检查和优化 prompt。
- 加入专门的 slide layout agent，提升 PPT 美观度。
- 改进 narration，使讲解更自然、更像课堂。
- 支持多篇论文输入。
- 增加 Web 界面，支持上传论文后一键生成结果。
- 增加 evidence consistency check，自动检查每页观点是否真的有论文依据。

## GitHub 提交说明

建议提交：

    src/
    prompts/
    requirements.txt
    process.txt
    README.md
    .env.example
    .gitignore

不要提交：

    .env
    input/paper.pdf
    outputs/
    *.mp4
    *.mp3
    *.pptx
    *.pdf

## License

This project is for educational and course project purposes.
