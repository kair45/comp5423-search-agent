# COMP5423 · Evidence Search

同一套程序用于验证、测试、交互式问答和轨迹回放。模型推理由硅基流动或阿里云百炼运行；三个检索器只访问本地固定语料。

## 当前工作区直接运行

从包含 code、data 和 .env 的项目目录打开 PowerShell 7。

    .\code\run.ps1 ui
    .\code\run.ps1 search "Cobalt mining and historical company mergers"
    .\code\run.ps1 read 5412 --focus "cultural activities"

网页中 Explore the collection 支持无密钥三路检索和原文阅读。Ask an agent 运行真实 API。Replay a run 自动展示实际 JSONL 中的答案、所选技能、证据和调用过程。CLI 启动时请等待模型首次载入。

## 模型服务和密钥

项目根目录 .env 使用 UTF-8；新机器从 code/.env.example 复制。进程环境变量优先于文件。不要提交填好密钥的 .env。每次新建问答或批次都会读取配置。

- 硅基流动（默认）设置 LLM_PROVIDER=siliconflow 和 SILICONFLOW_API_KEY。直连 https://api.siliconflow.cn/v1，模型 deepseek-ai/DeepSeek-V4-Flash。
- 阿里云百炼设置 LLM_PROVIDER=aliyun、DASHSCOPE_API_KEY、DASHSCOPE_WORKSPACE_ID 和 DASHSCOPE_REGION。北京默认 cn-beijing，香港可用 cn-hongkong。密钥须属于所填业务空间和地域。使用该地域的 maas.aliyuncs.com 兼容接口，模型快照 deepseek-v4-flash-0731。

[硅基流动 API](https://docs.siliconflow.cn/docs/api/chat-completions-post) · [阿里云百炼 API](https://help.aliyun.com/zh/model-studio/deepseek-api)

## 新环境安装与索引复现

在压缩包解压根目录执行以下步骤。实测 Python 3.10、PyTorch 2.5.1 CUDA 12.1、NVIDIA RTX 3060 Laptop 6 GB。也可用 CPU；编码速度随设备变化。安装合适的 PyTorch 构建后安装依赖。

    python -m venv .venv
    .\.venv\Scripts\python -m pip install -r code/requirements.txt
    Copy-Item code/.env.example .env
    pwsh -File code/fetch-public.ps1
    .\code\run.ps1 index bm25
    .\code\run.ps1 index qwen
    .\code\run.ps1 index e5 --windows 2 --batch-size 32

fetch-public.ps1 下载 code/public-revisions.json 固定版本的课程验证集、测试集、七个 Parquet 语料分片、两种模型权重和 Qwen 公开向量。它校验大小和上游提供的 SHA-256；若网络中断，重跑时复用已完成文件。大文件全部位于 data。BM25 的中间数据库和 E5 的分片支持中断重启。已完成的 BM25 索引无需重建。包中不分发权重、索引或密钥。

## 验证、测试和复现

    .\code\run.ps1 ask "Your question" --trace runs/example.jsonl
    .\code\run.ps1 batch data/validation/validation.jsonl runs/smoke.jsonl --limit 1
    .\code\run.ps1 experiment data/validation/validation.jsonl runs/holdout --split holdout
    .\code\run.ps1 batch data/test.jsonl deliverables/test_prediction.jsonl
    .\code\run.ps1 verify data/test.jsonl deliverables/test_prediction.jsonl
    .\code\run.ps1 score data/validation/validation.jsonl runs/holdout/E.jsonl --split holdout

请在命令行使用的 Python 与运行界面的 Python 保持一致。在非 Windows 系统使用 python code/main.py 替换 run.ps1；可通过 PowerShell 7 下载依赖数据。默认配置 E 综合使用三个检索方法、迭代控制、证据状态与原创技能。A/B 单轮，C 加入迭代，D 加入上下文管理。生成程序忽略输入文件的参考答案，验证评分器单独读取。API 超时、无用量、模型错误或断网会保留已接收的检查点，重新运行原命令即恢复。固定配置和索引版本；如改变配置，使用新的输出文件名。整批完成后发布 JSONL。

批处理默认逐题运行。在 PowerShell 设置 `$env:COMP5423_WORKERS='6'` 即可并行处理六道独立问题，输出仍按题目原始顺序排列。若模型给出带大段解释的草稿，智能体会让同一模型单独提取答案，草稿和提取调用的返回用量都保存在轨迹中。

实际 API 返回若在传输中丢失，服务方可能已经计费，本地无法恢复未接收的用量。此类情况会报错；记录只包含服务方已返回的真实消息和用量。

## 代码结构

| 文件 | 作用 |
|---|---|
| main.py、run.ps1 | 建索引、搜索、答题、运行实验、评分、提交核验 |
| app.py | 网页交互、文档阅读和轨迹回放 |
| searchkit/store.py | SQLite FTS5 BM25、压缩原文、原文窗口与偏移量 |
| searchkit/dense.py、retrieval.py | E5、Qwen3-Embedding、FAISS、RRF 融合 |
| searchkit/provider.py、agent.py | 直连模型 API、三种工具、结构化证据状态、按需技能 |
| searchkit/runs.py、diagnostics.py | 断点恢复、六字段校验、EM、检索片段覆盖率 |
| skills/follow-clues、skills/resolve-entity | 多跳线索追踪与候选实体消歧 |
| test_core.py | 合成离线测试，独立于正式预测 |

    Set-Location code
    ..\.venv\Scripts\python -m unittest -v test_core
    ..\.venv\Scripts\python -c "from pathlib import Path; from searchkit.diagnostics import evaluate; evaluate(Path('../data'),Path('../data/validation/validation.jsonl'),Path('../runs/validation-retrieval'))"

## 数据、方法与限制

文档数 100,195。E5 默认按文档开头与中部建立最多两个窗口，在这台机器得到 188,956 个向量；--windows 0 可改为全文重叠窗口。Qwen 使用公开文档向量与本地指令感知查询编码。search 对三路候选按文档 ID 进行 RRF 融合，返回原文片段；read_document 按 ID 和位置读取上下文；load_skill 在运行时加载技能。三路查询在 search 内部只发生一次对外工具调用。界面可单独查看每路贡献。最多 8 次工具调用为默认配置。报告和调试使用的检索覆盖率不能替代最终答案的 normalized EM。

[固定语料](https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus) · [上游索引与基准](https://github.com/texttron/BrowseComp-Plus) · [课程验证集](https://huggingface.co/datasets/HongruCai/COMP5423-BrowseComp-Plus-Val) · [课程测试集](https://huggingface.co/datasets/HongruCai/COMP5423-BrowseComp-Plus-Test)
