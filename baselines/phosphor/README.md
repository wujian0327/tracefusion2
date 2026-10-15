# Phosphor 0.0.4＋来源/采集适配器

上游：[gmu-swe/phosphor](https://github.com/gmu-swe/phosphor)，官方标签
`Phosphor-0.0.4`，提交`6c15c9b2bb609b790cacfc9297d9f18724dcb1d6`。
归档SHA见[版本锁](../tools.lock.json)，源文件SHA见[source-hashes.json](source-hashes.json)。
此前0.0.3的lambda兼容失败单独保留；本入口固定最终通过校准的0.0.4。

## 工具和插桩JRE

```bash
python3 baselines/manage.py fetch --tool phosphor
# 先完成公共准备中的固定镜像拉取。主机须有Maven。
python3 baselines/manage.py build-phosphor
python3 baselines/manage.py build-jre --out artifacts/baseline-phosphor-jre
python3 baselines/manage.py smoke-phosphor \
  --jre artifacts/baseline-phosphor-jre/jre --out artifacts/baseline-phosphor-smoke
python3 baselines/manage.py doctor --tool phosphor
```

构建保持原Java源码和POM，用显式固定版本的Maven插件处理资源/编译/打包/shade，
编译器调用固定Orders镜像内的javac8。跳过测试与源码/javadoc附件，日志和实际命令
保存在工具缓存`build.log`及`manifest.json`。JAR哈希可能因时间戳不同而改变，
新manifest记录实际值，并要求源码库存和内容匹配；不将新构件假定为历史发布物。

JRE从同一固定镜像的Java8类库生成，模式为`-multiTaint`，不是替换宿主机Java。
`build-jre`验证插桩完成及该JRE启动，生成相对路径的文件哈希清单；这不等于
五方法业务已经校准。`smoke-phosphor`进一步验证一个原生算术/顺序Stream标签
传播样例，也检查JRE与当前工具JAR匹配；它不替代Sock Shop的语句评分。
CPU/内存上限与日志在命令/构件中明确保存。

## Sock Shop五方法

先执行[公共准备](../README.md)中的`apps`。历史脚本仍读取Orders/Carts/Shipping的
原始缓存路径，`apps`会从镜像提取并按相同SHA建立兼容路径，不需要从旧电脑复制JAR。

```bash
python3 experiments/sockshop-mirrortaint/phosphor_five_statements.py build \
  --tool artifacts/external-tools/phosphor-0.0.4 --out artifacts/baseline-phos-adapter
python3 experiments/sockshop-mirrortaint/phosphor_five_statements.py run \
  --tool artifacts/external-tools/phosphor-0.0.4 \
  --jre artifacts/baseline-phosphor-jre/jre --build artifacts/baseline-phos-adapter \
  --out artifacts/baseline-phos-capture
```

适配器：[PhosphorStatementAgent.java](../../experiments/sockshop-mirrortaint/PhosphorStatementAgent.java)。
它在指定来源打原生标签、在指定目标读标签，不替换Phosphor传播引擎。
Orders来源为选定getter读值，Carts为DAO返回引用图内容，Shipping为参数引用图内容。

参考准确性是五方法的**11个聚合语句关系，TP6/FP0/FN0/TN5**。不是每请求字段实例
准确率，也未验证跨JVM传递标签；当前共同Orders.total字段实例成本任务仍为N/A。
这里只给出新采集入口，业务运行成功不能代替关系评分。

历史两口径评分由`compare_two_grains.py`完成。该脚本仍引用冻结的TraceFusion/
FlowDist捕获、三个ServiceGraph、all-query launcher和Stream模型，详见
[完整记录](../../experiments/sockshop-mirrortaint/README.md)。全新clone没有这些历史
数据；重放需单独迁移它们，生成新比较则需明确重新采集各侧、冻结相同物理端点。
本目录没有把只有Phosphor运行结果的配置标成三方比较已完成。
