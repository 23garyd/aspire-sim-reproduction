# ASPIRE 技能积累复现

**仿真研究 · Gary 的机器人工程实习项目**

这是 Gary 实习中的 ASPIRE 复现与评估项目。系统在仿真中生成并执行机器人程序，记录轨迹、修复失败，并将可复用技能放入技能库。项目重点是复现技能积累的效果、检查评分方法和保留可复核实验。

**研究问题：** 积累和检索已有技能，能否帮助机器人程序在未见过的任务种子上泛化？

**已有结果：** 已有验证集重分析：技能库条件 31/69，冷启动 15/69。这是跨任务的事后探索分析；重复样本共享任务，不能将其当作已完成的独立确认性实验。预注册实验尚未闭合。 [查看原始分析与边界](runs/VAL-REANALYSIS.md)。

## 演示与图像

[![双臂 lift 仿真对照，seed100、rep1 个案。左侧 baseline 未抬起锅，右侧所选程序抬起锅；这不是 B601 实机，也不能代表所有重复均成功。](docs/portfolio/assets/demo-poster.png)](runs/2026-07-17-lift-repeats/clips/two_arm_lift_BEFORE_vs_AFTER_seed100.mp4)

[播放原始演示片段](runs/2026-07-17-lift-repeats/clips/two_arm_lift_BEFORE_vs_AFTER_seed100.mp4)。双臂 lift 仿真对照，seed100、rep1 个案。左侧 baseline 未抬起锅，右侧所选程序抬起锅；这不是 B601 实机，也不能代表所有重复均成功。

## Gary 的实习工程工作

以下说明项目中的复现、实现、集成与分析工作。上游 ASPIRE／HarnessVLA 的论文方法不作为实习生原创方法；共享代码历史与本次文档整理不重复计为新增实现。

| 工作 | 具体内容 | 可检查入口 |
|---|---|---|
| 实现规划、执行和轨迹修复链 | 组织 coordinator、actor 和执行引擎，将运行结果用于程序修复。 | [代码或证据](aspire/coordinator.py) |
| 实现技能存储与检索 | 将技能积累、检索条件与冷启动对照分开，研究迁移和负迁移。 | [代码或证据](aspire/skill_library.py) |
| 建立实验与评分分析 | 区分调试种子得分和验证集泛化，保留事后分析的统计限制。 | [代码或证据](scripts/reanalyze_val.py) |
| 保留确认性实验材料 | 60格中收回48份可解析JSON、2份错误文本，10格缺summary；未补造完成结论。 | [代码或证据](docs/evidence/nov-m4/confirmatory/audit.json) |

这些材料可供评审检查机器人接口、状态机、实验设计、日志追踪与结果分析能力。实际实现提交见[代码与证据映射](docs/evidence/oct-m3/implementation-commits.csv)，不以证据整理提交替代实现贡献。

## 里程碑与当前状态

| 阶段 | 技术成果入口 | 如何理解完成范围 |
|---|---|---|
| 基础复现与接口准备 | 下方代码目录、[原技术说明](docs/history/readme-before-showcase-2026-11-14.md) | 按各项目区分仿真、软件验证和实体实验 |
| October／M3 集成 | [实现与验证索引](docs/evidence/oct-m3/README.md) | 有可复核实现和所列测试，不能推定所有合同条款已验收 |
| November／M4 比较 | [对照与演示索引](docs/evidence/nov-m4/README.md) | 既有结果与失败分析；无线比较和两项工业演示仍有缺口 |
| December／M5 准备 | [复现、归档与后续工程](docs/evidence/dec-m5/README.md) | 准备／部分证据；完整干净机器重建、最终演示和大文件取回尚未闭合 |

月份是交付组织标签，实验日期见原始记录。2026-11-14 的证据整理和无硬件测试不表示当日新增实机或仿真实验。完整说明见[评审阅读指南](docs/portfolio/README.md)。

## 结果限制与后续工作

本仓库没有证明物理 B601 执行成功。确认性实验和完整外部可取回的大文件归档仍未完成。双臂演示的重复存在高方差，所选视频是单例。

## 代码导航与复核

| 路径 | 内容 |
|---|---|
| `aspire/` | 规划、执行、技能库和轨迹结构 |
| `scripts/` | 实验调度和离线分析 |
| `runs/` | 研究设计、结果和失败记录 |
| `docs/evidence/` | 按交付阶段整理的技术证据 |

已有环境中的软件检查入口如下；准确依赖和平台条件按[复现说明](docs/evidence/dec-m5/reproduce.md)配置。本页面整理未重新运行完整实验，也不要求评审者驱动实体机械臂。

```sh
python3 -m pytest tests/ -q -p no:anyio
```

## 四条项目轨道

| 项目 | 研究／验证环境 |
|---|---|
| [ASPIRE 技能积累复现](https://github.com/23garyd/aspire-sim-reproduction) | 仿真研究 |
| [ASPIRE 到 reBot B601 的机器人适配](https://github.com/23garyd/aspire-robot-B601) | 软件适配与假驱动验证 |
| [HarnessVLA 固定策略与外层控制复现](https://github.com/23garyd/harnessvla-sim-reproduction) | LIBERO-Pro 仿真研究 |
| [HarnessVLA 在 reBot B601 上的实机实验](https://github.com/23garyd/harnessvla-rebot-b601) | B601 实机研究与工程验证 |

四个仓库是相关但不同的复现和工程项目，结果不混算。原始论文与框架归属见仓库中的引用及许可说明。商业审批报告、发票和付款信息不属于本技术展示页。
