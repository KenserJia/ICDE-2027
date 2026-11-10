# MT-Memory 实验包（v0.3.0）

本包对应当前论文，包含模块化代码、三套UCI原始及处理后数据、完整实验记录索引、28个独立复现协议。当前六张表和两张图有专用重建入口。论文版本由 `provenance/PAPER.json` 的摘要值确定。代码与数据目录已更新；完整附件见v0.3.0 Release，发布说明见PUBLICATION.md。论文文件及其中的旧Release网址未改动。

`src/mtmemory_icde/core/` 保留16个原科学模块；数据处理、证据读取和复现调度单独放在 `src/mtmemory_artifact/`。实验驱动按研究批次保留在 `repro/`，通过 `experiments/catalog.json` 统一调用。这样可以整理工程结构，同时保持原实验代码及已记录结果的来源可追踪。

安装、快速核验、数据重建和图表重建命令见英文 `README.md`。先运行 `verify`、`make test`、`smoke`、`prepare-data`、`tables`、`figures`，再按需要运行 `list` 中的完整实验。所有输出目录必须是新目录，运行器不会把已有结果作为断点续跑目录。

完整交付有两个互补文件：源码和数据 ZIP，以及 `mt-memory-raw-evidence-20261110.tar.gz`（7,131份二进制原始记录）。后者作为GitHub Release附件上传，安装后运行 `verify --full`。源码包本身已经包含图表重建所需记录及确定性分区输入；原始记录包额外提供逐请求数组和检查点镜像等审计材料。

代码和项目文档采用MIT；UCI数据及派生记录采用CC BY 4.0；Scotty保留Apache 2.0。请保留全部许可证及数据归属，不要把第三方资产一并标为MIT。三套数据的来源、DOI、处理方式和数组结构见 `data/README.md`。

完整记录保留高负载不满足20ms约束、年龄匹配平局、不同请求先验下的性能反转等结果。图表重建、快速功能检查和重新测量是不同验证层次，本次整理不声称重新测量所有长时实验。详见 `provenance/VALIDATION.json`。

人工上传步骤见 `docs/GITHUB_UPLOAD_zh.md`；ICDE核对见 `docs/ICDE_SUPPLEMENTAL_CHECKLIST.md`。目标仓库：https://github.com/KenserJia/ICDE-2027 。
