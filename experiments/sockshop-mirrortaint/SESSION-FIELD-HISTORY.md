# 可选的会话字段历史 v1

只有计划显式含 `session_history.version=1` 时启用；范围为顺序外部 HTTP 输入及明确列出的应用根方法，仅支持 full 观测。已有计划／事件仍按原规则读取。字节码规划仍调用原 `augment_calls`，额外根方法经过同一指令、构造和 native 许可检查；没有库许可扩张。

Agent 对真实方法入口／出口沿用 Frame 和 descriptor-aware 方法协议。新头及每条事件带 `session_history_version`、`capture_session`、`process_instance`，footer 带事件数。写方法被列为根之后，其实际执行的读、成功 PUTFIELD、构造开始／正常／异常完成均进入原事件流。未伪造调用或构造完成，未延长 ACTIVE 或修改对象退役规则。

离线每个实际根仍新建 State。会话历史只在一次捕获还原调用内存在，键为 `(capture, process, object, declared field, version)`。不可变版本记录包含物化后的观测、原始 HTTP 来源坐标、selectors、unknown、写事件位置、真实 Frame、site、descriptor、完成状态和支持事件。读取必须命中确切版本；后续覆盖不能改写旧记录。未知 RHS、异常根和未知效果保持未知；未知效果还对相关对象设置历史屏障，后续有证明的强写才可建立新 known 版本。

外部来源按实际 HTTP message 加解码对象／声明字段／版本绑定到早于方法入口的 request-read。重复 binding-input 是同一 HTTP 来源的别名；缺少实际 HTTP 或入口绑定就不建立来源。data_fields 与 control_fields 分开声明，后者保留 selectors，不混入数据来源评分。普通方法返回和缓存读取不成为 source，也不把历史输入加入当前 providers。

会话观测是新启用范围，不使旧捕获凭空拥有写事件。合成证据须标记，传输序号和计数先核验；对重新生成计数的合成副本仍执行字节码、调用完成、字段坐标和确切版本核验。并发、异步、GC 后复活、任意未观测写及全框架外部来源认证不属于 v1 的承诺。
