# ASPIRE 比较研究与确认性实验附件

整理日期：2026-11-14。本次恢复原实验文件和技术索引，没有调用模型、补跑仿真或宣布确认性实验完成。

| 工作 | 实现 | 技术记录 |
|---|---|---|
| 技能积累与检索对比 | [skill_library](../../../aspire/skill_library.py)、[离线重分析](../../../scripts/reanalyze_val.py) | [既有验证集分析](../../../runs/VAL-REANALYSIS.md) |
| 预注册任务选择与分析 | [选择逻辑](../../../scripts/val_confirmatory_select.py)、[分析程序](../../../scripts/analyze_libero_tiling.py) | [预注册](../../../runs/2026-07-26-val-confirmatory/PREREGISTRATION.md)、[原始单元文件清单](confirmatory/source-inventory.csv)、[60 格文件审计](confirmatory/cell-audit.csv) |
| 双臂场景候选 | [既有双臂试验目录](../../../runs/2026-07-16-m3-aspire-pilot/two_arm_handover/) | 该目录的结果文件记为 fail，修复未成功重放；不得当作已验收的第二项工业演示 |
| 分析与调度软件检查 | [相关测试](../../../tests/aspire/) | [Linux 上 6 项通过的输出](verification/2026-11-14-tests.txt) |

## 现存文件与历史实验状态

[文件审计](confirmatory/audit.json) 对原来选择的三任务、两条件、每条件十次重复列出 60 格：现存 48 份可解析 JSON，2 份错误文本，10 格没有 summary。错误文本保留为 `.json.invalid.txt`，没有伪造 JSON 或补作零分。

原技术记录将实验记为 50/60、尚未结束；48 份有效 JSON 与 2 份错误文件是这次收集到的 50 个摘要文件。此文件审计不是新的完成率，也不替换原统计中对失败的处理。仅用 48 份有效 JSON 重算最终显著性会改变分母，本次不这样做。

`confirmatory/results.json` 是源目录原有的中间结果，只含 spatial_6 的 20 行；保留原字节用于追溯，不能当成三任务的最终汇总。统计确认结论尚未形成，原 [技术研究记录](../../../ASPIRE-reproduction-report.pdf) 的“不完整”边界仍然成立。

ASPIRE 与 HarnessVLA 的两种仿真研究分别引用；本仓库不承担物理无线比较或 B601 ACT 对照的证明。所列 runner 的 dry-run 检查依赖 Linux `/proc`；在 macOS 上该项检查因平台条件失败，随后在 EPYC 的现有环境通过，未修改实现来掩盖平台差异。

[implementation-commits.csv](implementation-commits.csv) 与 [manifest.csv](manifest.csv) 分别记录代码历史及附件哈希。
