# 原机只读证据索引
目标：保留本次实测的来源、采样限制及文件完整性，不用状态快照代替合同验收。

| 文件 | 内容 |
| --- | --- |
| `frame-check/` | 后续97帧姿态、506条IMU及短时速度订阅；离线分析和6项安装转换候选测试，未部署 |
| `apt-packages.tsv` | 已安装包名、版本、架构，不含安装包 |
| `build-runtime.json` | Python导入、编译器、上游提交/改动、二进制哈希和实际环境ldd |
| `comparison.json` | 本地源码与远端文件的映射、当前及历史哈希 |
| `files.json` | 项目根、787项文件/链接清单、排除范围；不是全盘备份 |
| `project-materials-manifest.json` | S1至S10原件字节SHA256、大小及仓库位置 |
| `python-packages.json` | 126项Python发行包名称和版本 |
| `ros.json` | Master图、参数、节点、选择性进程环境及日志；移除了通用握手函数源码 |
| `source-support-manifest.json` | 64项补充参考原始路径、字节数和原字节SHA256 |
| `streams.json` | 约3秒TCPROS消息摘要、频率、字段/范围及只读HTTP状态，不含原始rosbag |
| `system.json` | UTC、系统版本、服务、设备、网络与进程快照 |

原始UTC保留在JSON内。未保存SSH凭据或认证链接。采样时间不完全相同，禁止按表中不同采样位置直接估算真实机器人速度；用户确认当时机器人静止。

采集通过SSH远端Python标准库、ROS现有消息反序列化、systemctl查询、dpkg-query、git只读命令及短时订阅完成。未发布ROS指令、修改运行文件或控制硬件。完整方法与限制见[核查报告](../../live-audit-20261023.md)。

离线校验：新增快照检查器8项测试通过，涵盖LF/CRLF、BOM、二进制、变更、缺失、路径越界和schema；旧历史audit在采集时失败30项，合入后续远端三个保护文件后为33项。当前快照检查仅证明被清单覆盖文件完整，不证明构建、定位、导航或验收通过。
