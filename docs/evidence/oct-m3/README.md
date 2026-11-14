# ASPIRE 算法实现与技能附件索引

整理日期：2026-11-14。实现基线：`a8c608fb10317a43d240047c726edbcb62a4d1ff`，原默认分支为 `aspire_original_sim`。
本次只整理技术附件，不新增模型调用或仿真实验。

| 功能 | 实现 | 技术文档与附件 |
|---|---|---|
| coordinator → actor 调度 | [coordinator](../../../aspire/coordinator.py)、[actors](../../../aspire/actors.py) | [执行记录示例](../../../runs/2026-07-16-m3-aspire-pilot/)、[测试输出](verification/2026-11-14-tests.txt) |
| 轨迹结构与执行结果 | [schemas](../../../aspire/schemas.py)、[engines](../../../aspire/engines.py) | [结构化结果](../../../runs/2026-07-16-m3-aspire-pilot/two_arm_lift/report.json) |
| 技能存储、检索与复用 | [skill_library](../../../aspire/skill_library.py)、[evosearch](../../../aspire/evosearch.py) | [课程技能索引](skills/curriculum/index.md)、[动作预算技能索引](skills/m3x/index.md) |
| 仿真研究的实验边界 | [分析脚本](../../../scripts/reanalyze_val.py) | [验证集重分析技术记录](../../../runs/VAL-REANALYSIS.md) |

两个技能索引与既有 2026-08-25 证据包中的索引字节完全相同。现已从 EPYC 的原技能库补齐各自链接的技能正文，并保留原目录关系，索引不再指向缺失文件。来源目录分别为 `aspire_runs/curriculum/accumulated_library` 和 `aspire_runs/m3x/skill_library`；来源路径用于追溯，审批者直接读取本仓库附件即可。

[测试输出](verification/2026-11-14-tests.txt) 是 2026-11-14 对所列 59 项无硬件测试的检查，不是新仿真结果，也不证明 B601 实机已完成全部任务。

ASPIRE 的技能积累实验与 HarnessVLA 的固定策略／harness 对照实验是不同研究。`15/40` 对 `23/40` 的历史数字属于 HarnessVLA 仿真记录，不能归到本仓库的 ASPIRE 结果。本仓库原有验证性实验的未完成边界仍按各实验技术记录解释。

[manifest.csv](manifest.csv) 给出本目录附件的哈希及来源。

[implementation-commits.csv](implementation-commits.csv) 将每项功能对应到实现文件、最后修改该文件的历史提交、完整基线中的代码链接和附件路径。历史实现提交与本次证据整理提交分别保留，避免把文档整理称作新增实现。
