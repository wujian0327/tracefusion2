# 第二轮预先固定的问题定义

基线 `e48832dc171357c614912d8795c17e186eabd0c1`，main，初始工作区干净。实际运行时、依赖及原预期哈希见 `round-two-initial-state.json`。第一轮 workload、expected、报告和捕获不改。新增 `expected-round-two.json` 在本轮实现与预测前封存于 `artifacts/cross-request-lineage-round-two-spec-20261113-01/`。

只推进真实外部 HTTP 直接进入 B 的既有 split 业务：replace、overwrite、publish、read，组内同 JVM、同工作线程。五个正常控制分别验收，第六组完整证据副本另计，派生缺证义务不与正例分母混用。不处理原 process 的条件写限制、A→B、并发、异步、持久化存储或性能。

实际缺少的事实包括 replace 中 Cache.key、Cache.cell 和 Cell.text 构造写入、overwrite／publish 中 Cell.text 写入；还缺少这些实际方法的入口、参数、执行事件及正常／异常完成。方案是显式版本化的会话观测，纳入真正执行的应用方法及已有构造协议，不合成调用、不增加 native／构造许可。

来源仅为 B 外部 request-read 的真实字段。重复方法入口对同一输入的观察必须绑定到同一 HTTP 字段实例；缓存或普通方法返回不是 source。value／fallback 是显式数据来源；op／key 继续属于控制选择，观察其事实以核验控制，但不混入数据来源评分。

每个根调用保留独立 State、局部变量、调用栈、异常和临时上下文。捕获会话历史以 capture、process、object、声明字段、版本为位置，保存不可变右值来源、建立版本的真实写事件／调用、完成和效果状态，并记录后续实际读取。只按确切版本读取，不按值匹配、不回退旧版本、不把未知当空集合，不延长 ACTIVE 只读域；原状态退役规则保持。

逐请求检查点新增但不修改业务输入：首次写后及常量覆盖前须 known R1/value；覆盖后应 known 空数据集合；miss 应来自 R2/fallback，同时缓存仍为 R1/value 的原版本。来源、对象关系、读取版本和正常完成分别评分。

负例从正确 known 的完整捕获制作，原始证据保持不动：删除必要写入、删除历史外部 source／入口绑定、将读版本改成无写证明版本、同值错误复用旧来源、引入异捕获／异进程相同对象号。传输序号或计数损坏判证据无效；重新生成合成序号后仍不得产生错误 known；故意错误标签须被独立预期检出。已有 unknown 不计作缺证保护成功。

MirrorTaint 复跑同一业务、相同外部数据字段粒度；公开导出不支持的严格版本和离线缺证查询保持 N/A。保留第一轮 direct-B 正确结果。新 Agent 捕获与旧捕获在新核心下的复算分列；旧格式按旧规则读取，不补造未记录的写入。
