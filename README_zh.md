# 使用说明

本包对应当前正文的五个RQ、六张表和四张图。自有代码及文档为MIT；UCI数据及其处理版本保留CC BY 4.0；Scotty源代码保留Apache 2.0。

1. 按英文README安装固定依赖，运行`verify`与测试。
2. `tables`重建正文数值表；`figures`重建四张主图。这两项使用记录数据，不是新的性能实验。
3. `smoke`验证服务行为；`run`从头运行正式协议。每次使用新输出目录，计时实验串行运行。
4. 主仓库包含预处理数据、UCI源压缩包及所有最终文本记录；完整逐请求数组、查询真值和恢复镜像位于另附原始证据包。用`install-raw`导入后，`verify --full`逐文件校验。
5. 参考`docs/GITHUB_UPLOAD_zh.md`：将主仓库目录上传GitHub，把大证据包放到同一版本Release附件。不要把本机虚拟环境、运行输出或该大压缩包直接提交到Git。

正文和原项目没有被本次打包修改。待你建立真实GitHub仓库和Release后，再用`docs/AVAILABILITY.md`中的模板替换正文占位符。发布前验证记录见`provenance/VALIDATION.json`。数值与结论以原始实验记录为准，未承诺跨机器时延逐位相同。
