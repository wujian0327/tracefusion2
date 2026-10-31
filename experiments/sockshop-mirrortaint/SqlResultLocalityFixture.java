import java.util.*;
import java.lang.reflect.*;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.InnerInterceptor;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.session.*;
import org.apache.ibatis.session.defaults.DefaultSqlSessionFactory;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.apache.ibatis.reflection.*;
import org.apache.ibatis.reflection.invoker.Invoker;
import org.apache.ibatis.reflection.factory.DefaultObjectFactory;
import org.apache.ibatis.plugin.*;
import org.apache.ibatis.executor.Executor;
import org.apache.ibatis.mapping.*;
import org.mybatis.spring.SqlSessionTemplate;
import org.h2.jdbcx.JdbcDataSource;
import com.fasterxml.jackson.databind.ObjectMapper;

public class SqlResultLocalityFixture {
 public static class Row {private Long id;private String text;private Date created;public Row(){}public Long getId(){return id;}public void setId(Long x){id=x;}public String getText(){return text;}public void setText(String x){text=x;}public Date getCreated(){return created;}public void setCreated(Date x){created=x;}}
 public static class Result {private List<Row> rows;public Result(){}public List<Row> getRows(){return rows;}public void setRows(List<Row> x){rows=x;}}
 public interface Store {@Select("select id, text, created from witness order by id") List<Row> read(Map<String,Object> parameters);}
 Store store;
 public Result root(int mode){Map<String,Object> parameters=new HashMap<>();List<Row> rows=store.read(parameters);
  if(mode==4)rows.get(0).setText("same");
  else if(mode==5){parameters.put("escape",rows);OpaqueSqlResult.parameters(parameters);}
  else if(mode==6)OpaqueSqlResult.touch(rows.get(0));
  else OpaqueSqlResult.unrelated();
  Result result=new Result();result.setRows(rows);return result;
 }
 public static class LeakingFactory extends DefaultObjectFactory {public <T>T create(Class<T> c,List<Class<?>> types,List<Object> args){T x=super.create(c,types,args);if(x instanceof Row)OpaqueSqlResult.published=(Row)x;return x;}}
 @Intercepts(@Signature(type=Executor.class,method="query",args={MappedStatement.class,Object.class,RowBounds.class,ResultHandler.class}))
 public static class LeakingPlugin implements Interceptor {public Object intercept(Invocation i)throws Throwable{Object x=i.proceed();if(x instanceof List&&!((List)x).isEmpty()&&((List)x).get(0)instanceof Row)OpaqueSqlResult.published=(Row)((List)x).get(0);return x;}public Object plugin(Object x){return Plugin.wrap(x,this);}public void setProperties(Properties p){}}
 static void leakInvoker(Configuration c)throws Exception{Reflector reflector=c.getReflectorFactory().findForClass(Row.class);Field f=Reflector.class.getDeclaredField("setMethods");f.setAccessible(true);Map<String,Invoker> m=(Map)f.get(reflector);final Invoker original=m.get("text");m.put("text",new Invoker(){public Object invoke(Object target,Object[] args)throws IllegalAccessException,InvocationTargetException{OpaqueSqlResult.published=(Row)target;return original.invoke(target,args);}public Class<?> getType(){return String.class;}});}
 static Store configure(JdbcDataSource data,int mode)throws Exception{
  MybatisConfiguration c=new MybatisConfiguration();c.setEnvironment(new Environment("fixture",new JdbcTransactionFactory(),data));c.setLazyLoadingEnabled(false);
  if(mode==1)c.setObjectFactory(new LeakingFactory());
  if(mode==2)leakInvoker(c);
  if(mode==3)c.addInterceptor(new LeakingPlugin());
  if(mode==7||mode==8||mode==9){final int scenario=mode;MybatisPlusInterceptor outer=new MybatisPlusInterceptor();outer.addInnerInterceptor(new InnerInterceptor(){public void beforeQuery(Executor executor,MappedStatement statement,Object parameter,RowBounds bounds,ResultHandler handler,BoundSql sql)throws java.sql.SQLException{OpaqueSqlResult.heldExecutor=executor;if(scenario==8)try{leakInvoker(statement.getConfiguration());}catch(Exception error){throw new IllegalStateException(error);}if(scenario==9)try{Field flag=ResultMap.class.getDeclaredField("hasNestedQueries");flag.setAccessible(true);for(ResultMap mapping:statement.getResultMaps())flag.set(mapping,true);}catch(Exception error){throw new IllegalStateException(error);}}});c.addInterceptor(outer);}
  c.addMapper(Store.class);return new SqlSessionTemplate(new DefaultSqlSessionFactory(c)).getMapper(Store.class);
 }
 public static void main(String[] ignored)throws Exception{
  JdbcDataSource data=new JdbcDataSource();data.setURL("jdbc:h2:mem:locality;DB_CLOSE_DELAY=-1");try(java.sql.Connection c=data.getConnection();java.sql.Statement s=c.createStatement()){s.execute("create table witness(id bigint primary key, text varchar(20), created timestamp)");s.execute("insert into witness values(1,'same',TIMESTAMP '2020-01-01 00:00:00'),(2,'same',TIMESTAMP '2020-01-02 00:00:00')");}
  List<Map> output=new ArrayList<>();for(int mode=Boolean.getBoolean("fixture.nested.mapping")?9:0;mode<=(Boolean.getBoolean("fixture.nested.mapping")?9:8);mode++){SqlResultLocalityFixture f=new SqlResultLocalityFixture();f.store=configure(data,mode);OpaqueSqlResult.published=null;W3CTraceContext context=W3CTraceContext.server("00-cccccccccccccccccccccccccccccccc-"+String.format("%016x",mode+1)+"-01",null);SpringTransportAgent.Transport.ASYNC.set(context);Result result;try{result=f.root(mode);}finally{SpringTransportAgent.Transport.ASYNC.remove();}for(String key:new String[]{"frames","scopes","calls","sql_locality","constructors"})if(((Number)MonitorSafety.inspect().get(key)).intValue()!=0)throw new IllegalStateException("State retained after root: "+key);if((mode>=1&&mode<=3||mode==8)&&OpaqueSqlResult.published!=result.rows.get(1)&&OpaqueSqlResult.published!=result.rows.get(0))throw new IllegalStateException("Actual leak witness missing");Map r=new LinkedHashMap();r.put("mode",mode);r.put("message",context.message());r.put("values",Arrays.asList(result.rows.get(0).text,result.rows.get(1).text));r.put("ids",Arrays.asList(result.rows.get(0).id,result.rows.get(1).id));r.put("dates",Arrays.asList(result.rows.get(0).created.getTime(),result.rows.get(1).created.getTime()));output.add(r);}
  System.out.println(new ObjectMapper().writeValueAsString(output));
 }
}

// Deliberately omitted from the planner's JAR: actual effects cannot be proved
// from matching pre/post values or complete-looking instrumented write counts.
class OpaqueSqlResult {static Executor heldExecutor;static SqlResultLocalityFixture.Row published;static void unrelated(){if(published!=null)published.setText("same");}static void touch(SqlResultLocalityFixture.Row r){r.setText("same");}static void parameters(Map<String,Object> p){((List<SqlResultLocalityFixture.Row>)p.get("escape")).get(0).setText("same");}}
