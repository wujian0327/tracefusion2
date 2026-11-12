# 观测协议增量

## exception_dispatch_version = 1

start 声明版本。每个解释方法的 collection-catch/abort 内嵌 exception_dispatch：version、method、caller Class节点、异常object、actual_type、实际super链、按原异常表顺序解析的targets（catch-all为null）。节点包含Class对象ID、内部名、定义加载器ID（bootstrap=null）、直接super Class ID和class SHA256。使用调用方法的类加载器、不初始化catch类；不使用线程context loader猜catch类型。abort现在携带原异常身份及类型，支持未捕获和跨方法传播。

离线按原方法PC保护范围及表顺序选首个匹配Class身份；验证完整Throwable链、应用元数据哈希、Class身份/加载器/父类稳定性和异常对象实际类稳定性。collector复用ExecutionKernelHooks.classHash及原typeTest的Class身份机制。普通业务类由已固定原class元数据核验。跨应用加载器当前明确exception-loader能力限制，不能仅靠同名或相同字节码哈希匹配；bootstrap Throwable父类链保留运行时见证。

旧捕获没有版本字段时沿用有限JDK异常表。任意自定义异常遇到typed catch明确exception-dispatch限制，即使后面有catch-all也不能跳过前面的未知typed catch。纯catch-all可用。旧证据不能伪造新见证；版本缺失但出现新见证、未知版本、必要见证丢失/矛盾均拒绝。
