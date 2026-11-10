# 手动上传说明

目标：https://github.com/KenserJia/ICDE-2027 。本次只在本地准备v0.3.0，没有修改远程仓库。

1. 用Git或GitHub Desktop将 `mt-memory-icde-artifact-20261110/` 目录内的内容更新到仓库根目录，包含隐藏的 `.github/` 和 `.gitignore`。Household处理后数据文件为26,543,937字节，超过网页单文件25MiB限制，应通过Git提交。两个完整压缩包都不要提交进Git历史。
2. 在新提交上建立v0.3.0 Release，把源码数据ZIP、完整原始证据TAR.GZ及SHA256校验文件作为附件上传。两包合起来才是完整实验包。保留旧Release和旧附件。
3. 论文当前仍链接旧的v0.2.0 Release，按你的要求本轮不改网址。为使该网址也能访问新增实验，请将本次两个带20261110日期的附件及校验文件同时追加到旧Release，在说明中注明“2026-11-10补充实验快照”。不要覆盖旧附件或移动旧标签。旧Release自动生成的“Source code”仍是旧代码，提醒审稿人下载明确命名的新实验ZIP。以后若更新论文版本，可再改成新Release直链。
4. 上传后从未登录浏览器下载两包，在新目录解压源码ZIP，按照README核验，再导入对应原始记录包并运行 `verify --full`。提交系统填写实际可访问的链接和对应版本。发布前，当前公开v0.2.0不能替代这次新增材料。
5. 保留根MIT、第三方声明、CC BY4.0数据归属、Apache2.0条款及原Scotty来源。代码MIT不等于整个目录内所有第三方材料都是MIT。

可直接参考 `docs/RELEASE_NOTES.md` 编写发布说明；完整目录、记录范围和验证结果见README及 `provenance/VALIDATION.json`。ICDE核对见 `docs/ICDE_SUPPLEMENTAL_CHECKLIST.md`。官方GitHub依据见同目录英文上传说明。
