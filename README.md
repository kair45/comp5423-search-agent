# COMP5423 搜索智能体

首次克隆请按 [代码使用说明](code/README.md) 创建环境、从配置样例生成本机 .env 并构建三路索引。下文的实验结果、报告与视频路径指运行脚本后生成的本地文件。

## 本机使用

- 在项目根目录的 .env 填 SILICONFLOW_API_KEY 即可用硅基流动运行课程模型。如果使用阿里云百炼，按 .env 中的说明改选 aliyun 并填业务空间、地域和该服务的密钥。
- 执行 .\code\run.ps1 ui 打开网页。已构建的三路本地索引可直接在 Explore the collection 中使用。
- 完整运行参数、索引复现与六种配置见 [代码使用说明](code/README.md)。

## 交付与复现

deliverables/Source.zip 是可分发的源码包。Project-Report-Draft.pdf 来自所提供的 Overleaf 模板和真实验证集检索实验。Project-Video.mp4 展示真实检索、文档阅读和模型在不同题上的技能选择。当前每份文件的适用范围请以文件名和报告内容为准。

配置密钥后执行 .\finish.ps1 将通过所选平台生成 100 道正式测试题预测、核验已有对照结果并完成六种配置的 30 题比较、录制带真实轨迹的视频，并更新报告。此步骤会产生所选服务的实际调用费用。单独跑一题可使用代码说明中的 smoke 命令。拆分使用固定种子 5423。优化时分析过 30 题的旧版结果，正式排名由课程方用测试集统一评测。

要生成最终小组 ZIP，请复制 report/group.example.json 为 report/group.json，按实际成员填写姓名、分工、比例及本人签名文件的相对路径。获准三人组只填写三人，比例合计 100%。核对成员认可的声明后执行：

    .\finish.ps1 -GroupFile .\report\group.json

同一实验和题集的检查点可复用。最终包包含 test_prediction.jsonl、code/、Group-X-Report.pdf 和 Group-X-Video.mp4。程序只在本地创建压缩包。

## 新版效果

F 是默认配置。70 道开发题中，原版 E 完成 68 题、答对 21 题，另 2 题连续输出截断。F 完成全部 70 题、答对 33 题。在原来的 30 题验证比较中，E 答对 6 题，F 答对 12 题。工具请求从 224 次降至 196 次，Token 总量从 609,184 增至 748,759。逐项统计存放在 `runs/optimization/comparison.json`。

## 实验记录

- runs/validation-retrieval/retrieval-queries.jsonl 保留 100 题逐方法文档排名和证据片段。
- runs/validation-retrieval/retrieval-metrics.json 记录 Top 5 原文片段的规范化参考答案字符串覆盖率。
- runs/validation-retrieval/coverage-by-depth.json 补充 Top 1、3、5 的全文/片段命中及遗漏案例。全文中的字符串出现不表示该段支持回答。
- data/test.jsonl 和 data/validation/validation.jsonl 是课程方分别发布的无答案正式测试集和带答案验证集。
- 生成报告与演示可使用系统 pdflatex、FFmpeg、Chrome/Edge，以及 Python 的 Pillow 和 playwright。当前机器已具备这些依赖。若更换机器，安装后可用 finish.ps1 的 -Chrome 和 -FFmpeg 指定程序路径。

从已有实验重算分析和论文图表：

    .\.venv\Scripts\python tools/evidence_analysis.py
    python tools/plot_results.py
    .\.venv\Scripts\python tools/build_report.py

完整项目结构见 [CODEBASE.md](CODEBASE.md)。
