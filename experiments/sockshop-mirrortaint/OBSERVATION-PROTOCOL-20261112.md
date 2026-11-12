# 观测协议增量

## exception_dispatch_version = 1

start 声明版本。每个解释方法的 collection-catch/abort 内嵌 exception_dispatch：version、method、caller Class节点、异常object、actual_type、实际super链、按原异常表顺序解析的targets（catch-all为null）。节点包含Class对象ID、内部名、定义加载器ID（bootstrap=null）、直接super Class ID和class SHA256。使用调用方法的类加载器、不初始化catch类；不使用线程context loader猜catch类型。abort现在携带原异常身份及类型，支持未捕获和跨方法传播。

离线按原方法PC保护范围及表顺序选首个匹配Class身份；验证完整Throwable链、应用元数据哈希、Class身份/加载器/父类稳定性和异常对象实际类稳定性。collector复用ExecutionKernelHooks.classHash及原typeTest的Class身份机制。普通业务类由已固定原class元数据核验。跨应用加载器当前明确exception-loader能力限制，不能仅靠同名或相同字节码哈希匹配；bootstrap Throwable父类链保留运行时见证。

旧捕获没有版本字段时沿用有限JDK异常表。任意自定义异常遇到typed catch明确exception-dispatch限制，即使后面有catch-all也不能跳过前面的未知typed catch。纯catch-all可用。旧证据不能伪造新见证；版本缺失但出现新见证、未知版本、必要见证丢失/矛盾均拒绝。

## field_value_version = 1

start声明版本。实例read/write、反射字段快照、getter字段见证、静态读取、构造输入投影和默认/enum字段见证使用声明描述符：基本类型observed为 `{object:null, primitive:"I", value:1000000}`。F/D另带原始IEEE754十六进制bits，保留负零及NaN载荷；非有限value遵循JSON编码器的NaN/Infinity/-Infinity字符串。普通字段行继续携带owner、声明field、真实version和descriptor。

插桩调用8种基本类型field入口，操作数不再先转成Object传给通用value/id。JSON Map中的数值仍可能有短命包装对象，反射Field.get也会装箱；它们不登记到IDS或保留为业务身份。反射快照在id之前依据原Field类型分流。引用字段（包括Integer/Long）仍使用原value/id；null为object:null/value:null且没有primitive标记。列表/Map的元素属于真实引用，不能因为Number值而清除身份。

离线校验描述符、基本类型范围、类型/值/浮点bits和物理坐标；基本类型禁止object身份，引用字段禁止primitive编码。来源和已写入引用字段的读取增加身份一致性核验，不能靠同值数值包装对象互换。旧格式缺少版本时仍可读，原人工基本类型包装ID按原解释器投影丢弃；新标记缺少版本或未知版本拒绝。旧HTTP字段行的boolean primitive元数据不是新observed类型标签。

metrics增加ids_size、versions_size、active_owners、checked_classes_size、library_hashes_size、array_versions_size、array_slots_size、initialized_classes_size。它们是状态表计数，不是对象存活/内存占用估算，也不作为来源认证依据。未改变ID生命周期、计数版本或原对象身份上限。
