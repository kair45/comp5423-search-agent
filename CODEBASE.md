# 项目结构

2026-11-28 · COMP5423 搜索智能体

| 位置 | 内容 |
|---|---|
| code/main.py、app.py、run.ps1 | 批处理、评分和网页界面的入口 |
| code/searchkit/ | 文档库、三路检索、模型适配、逐题并发执行、答案格式化、截断恢复与轨迹 |
| code/searchkit/clues.py | 整题与线索双查询、原文片段排序和证据保留 |
| code/skills/ | 多跳线索追踪、实体消歧两个运行时技能 |
| code/README.md、requirements.txt、public-revisions.json | 复现入口、依赖和公开数据版本 |
| data/ | 固定语料、验证与测试题、模型、本地索引 |
| runs/ | 真实检索实验，以及已配置服务后的运行记录 |
| report/ | 课程 ACM 模板、英文报告、贡献声明和真实界面截图 |
| tools/、finish.ps1 | 实机演示录制、报告生成、提交打包 |
| deliverables/ | 源码包、报告、视频及生成后的正式预测 |
| .env | 本机服务商和密钥配置 |
