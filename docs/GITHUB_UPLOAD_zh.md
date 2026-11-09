# GitHub 上传说明

此包尚未发布到任何公开仓库，正文也尚未填写 GitHub 链接。

## 上传步骤

1. 解压 `mt-memory-icde-artifact-20261109.zip`，使用 GitHub Desktop 或 Git，将解压目录中的文件作为仓库内容上传，保留 `.github`、`.gitignore`、`LICENSE`。不要只把 ZIP 当作仓库内容上传。
2. 创建版本标签和对应 Release，例如 `v0.2.0`。将 `mt-memory-raw-evidence-20261109.tar.gz` 及对应 `.sha256` 文件放在该 Release 的附件中，不要加入 Git 历史。
3. 主仓库包括源代码、公开原始数据压缩包、论文使用的处理数据、全部最终文本实验记录、图表代码和四张正文图。大附件包括逐查询/请求数组、验证状态及真实检查点镜像。两部分共同组成完整证据。
4. 按英文 README 安装和验证。导入大附件后运行 `python reproduce.py verify --full`，应显示 5307 个原始文件均已安装且无校验差异。`tables`、`figures` 是基于记录重建，`run` 才是重新实验；计时实验请串行运行，每次使用新的输出目录。
5. 确认仓库和 Release 能公开访问后，使用 `docs/AVAILABILITY.md` 模板填写真实仓库 URL、版本标签、提交 SHA 和 Release 附件链接，再修改正文。CITATION.cff 暂用原项目已有的集体署名；请在确认作者身份后再填写个人作者。不要编造 DOI 或使用尚不存在的链接。

## 许可证

自有代码和文档使用 MIT，保留原项目版权声明。UCI 数据、处理数据及数据衍生实验记录保留 CC BY 4.0，引用和加工说明位于 `data/README.md` 与 `data/CITATIONS.bib`。Scotty 保留 Apache 2.0。MIT 不能替代第三方许可证；上传时一并保留 `THIRD_PARTY_NOTICES.md` 和 `licenses/`。

## 已验证与范围

在重新创建的 macOS/arm64 环境及异目录解压副本中完成了独立安装、28 项测试、六张正文表、四张正文图和三种服务变体的冒烟验证。两套数据共 65 个数组精确重建。RQ2 的 8385 条主记录和 2808 条相位控制记录完全复现；联合质量的 104 个配置、479232 次查询检查与原记录一致；216 个故障案例、120 个支持算术检查、8000 次融合诊断检查和 138 次联合性能运行也已完成。原始大附件的 5307 个成员逐文件校验通过。

性能复跑完成了 1380 万次请求，预算、最终全数组恢复及 K 间隔检查通过。新计时结果单独位于 `provenance/validation/`，没有替换论文原记录。性能数值、线程交错和内存受环境影响，不承诺逐位一致。本轮没有重跑 30 分钟旧组件实验、全部旧调优/并发网格或 Java/SQL 基线；相应源代码、协议和原始结果已经提供。未声称 Linux/x86 实验已验证。完整验收记录见 `provenance/VALIDATION.json`。

本次只建立新的 releases 打包目录；原项目受保护的 6117 个文件及当前 11 个正文相关文件均保持原校验值，见 `provenance/validation/original-protection.json`。
