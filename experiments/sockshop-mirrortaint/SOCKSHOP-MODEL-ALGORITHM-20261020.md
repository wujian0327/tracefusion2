# 有限读取效果检查与 HTTP 来源事实

本轮是响应目标绑定后的有限修订，不是一般方法分析器。原复制、归约、集合计算 profile 保留；新效果检查通过统一配置 `read_forward_contracts: true` 启用，只作用于 `response-forward`。该开关对本轮所有查询统一启用，不按成功结果挑字段。`source_evidence: true` 记录原始 HTTP 读取事实。

## 组合读取不是 helper 白名单

`plan_read_effects.py` 从已固定的字节码生成候选组合方法。它限制指令与无环控制流，拒绝普通方法内字段写、外部类静态初始化风险、任意构造器、反射/native 指令效果、一般循环和数组等；允许本类已初始化后的静态字段读取。构造器限于已有简单字段赋值结构及固定 JDK 的空 Object、ArrayList、StringBuilder 构造，字段版本保护仍生效。

候选方法可以包含尚未解释的调用，但这不是宣告这些调用只读。Agent 核对实际虚调用实现来自哈希检查过的类，记录每个执行调用的开始、完成、接收对象、输入相关字段版本、返回对象和子调用状态；不透明子调用使组合证明失败。调用前后的相关字段版本发生变化也不能得到组合读取证明。根方法本身没有取得效果证明时，返回目标保持 unknown，防止跳过构造器内部效果。

固定 JDK 模型仅支持允许的具体 List 类创建新的顺序流、`findFirst` 选实际首元素，以及同一个已核验、非空 Optional 的 `orElseGet`。列表成员和选择结果按对象身份核验，不按值连接。空 Optional 可能调用 Supplier，继续保持不透明。嵌套方法的标准 LambdaMetafactory Supplier 创建只作为分配效果支持，不执行或概括其回退体；根方法中的 invokedynamic 仍按前轮规则拒绝。任意 stream pipeline、平行流和自定义 List 没有由此获得支持。

JDK 版本和相关类哈希固定在 `read-forward-runtimes-20261020.json`，来自原固定镜像的无网络探针。离线端核对运行时清单、调用配对、数量、实际实现、流创建/首对象/Optional 的身份链。缺失或矛盾的必要证据导致证据无效；未证明的调用效果导致 unknown。

效果检查不创建来源。来源仍须来自原先声明的入口、仓储读取返回或实际 RPC 读取证据，并匹配对象、字段、版本和根调用。返回对象及其序列化快照不能替代这些来源。

## HTTP 原始事实与 HATEOAS

`SourceEvidenceHooks.java` 在 Jackson 实际消费输入流时旁路记录字节，不另行读取、耗尽或重新请求业务流。记录实际 RPC span、父消息、URI、原始字节哈希、完整性、解码对象身份及字段版本。完整性要求单个无重复键 JSON，且观察到 EOF 或字节数等于 Content-Length；超界、skip/reset、解析失败等不能证明完整。特殊 MappingJacksonInputMessage 不包装，读取异常时释放旁路状态。

对固定 Spring HATEOAS 0.20.0 Resource，先核对类哈希，再记录 content 对象的字段投影。这是来源事实与一致性资料，不是“所有 JSON 位置都能直接连接”的保证，原始事实没有被直接注册为已知答案来源。

独立的 `HateoasOracleProbe.java` 不加载 TF Agent，使用原版 JAR 内的默认 RestTemplate/Jackson 库重新解码捕获字节。原 AsyncGetService 虽构造额外 HAL template，真实 getResource 使用的却是 RestProxyTemplate 中的默认 RestTemplate。默认 Resource 的忽略属性会使原始 id 没有写入 content.id；这些 null 不能错误连回原始 `/id`。

## 保存、异步及剩余边界

本轮没有把 Mongo save、异步工作、Future.get、HTTP POST helper 或任意 toString 统一声明为只读。审阅的 SimpleMongoRepository.save 返回原参数，但其 MongoTemplate 调用仍可能进行 ID/版本写和回调；只验证返回身份或相同数值不足以证明来源保持。异步也需要工作实例、输入、完成及最终返回值的独立配对，W3C 上下文只能提供其中的通信上下文。

因此 Cart 的只读仓储转发可以成为完整验证路径，Orders 的这些必要效果仍可保留 unknown。共享可变对象、反射/native、自定义序列化、任意流和一般循环的保证没有扩大。新增完整调用配对有在线成本，本轮不引用旧成本表来评价新配置。

实现入口：[规划](plan_read_effects.py)、[运行核验](ReadEffectHooks.java)、[离线核验](infer_response_binding.py)、[原始事实](SourceEvidenceHooks.java)、[独立真值与实验](run_sockshop_model_revision.py)、[语义控制](run_read_forward_semantics.py)。
