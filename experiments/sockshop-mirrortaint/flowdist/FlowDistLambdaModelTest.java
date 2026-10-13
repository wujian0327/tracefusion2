import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;
import dua.util.Util;
import dua.method.CFGDefUses.ObjVariable;
import dua.method.CFGDefUses.Variable;
import soot.*;
import soot.jimple.*;

/** Test the disclosed reference/alias extension, including ordinary cases. */
public final class FlowDistLambdaModelTest {
    private static int checks;
    @SuppressWarnings("unchecked")
    private static List<RefLikeType> types(Value value) throws Exception {
        Method method=Util.class.getDeclaredMethod("getAllPossibleRuntimeRefTypes",Value.class);
        method.setAccessible(true);
        try { return (List<RefLikeType>)method.invoke(null,value); }
        catch (java.lang.reflect.InvocationTargetException failure) {
            if (failure.getCause() instanceof IllegalArgumentException)
                throw (IllegalArgumentException)failure.getCause();
            throw failure;
        }
    }
    private static void check(boolean condition) {
        if (!condition) throw new AssertionError("Failed model check " + checks);
        checks++;
    }
    private static Value dynamic(final Type type) {
        return (Value)Proxy.newProxyInstance(FlowDistLambdaModelTest.class.getClassLoader(),
            new Class<?>[]{DynamicInvokeExpr.class}, (proxy,method,args) -> {
                if (method.getName().equals("getType")) return type;
                if (method.getName().equals("hashCode")) return System.identityHashCode(proxy);
                if (method.getName().equals("equals")) return proxy==args[0];
                if (method.getName().equals("toString")) return "dynamic-fixture";
                throw new UnsupportedOperationException(method.getName());
            });
    }
    private static SootClass klass(String name, int flags, SootClass parent) {
        SootClass c = new SootClass(name, flags);
        c.setResolvingLevel(SootClass.BODIES);
        if (parent!=null) c.setSuperclass(parent);
        Scene.v().addClass(c);
        return c;
    }
    public static void main(String[] args) throws Exception {
        check(Util.class.desiredAssertionStatus());
        SootClass object=klass("java.lang.Object",Modifier.PUBLIC,null);
        SootClass contract=klass("fixture.Callback",Modifier.PUBLIC|Modifier.INTERFACE|Modifier.ABSTRACT,null);
        SootClass implementation=klass("fixture.CallbackImpl",Modifier.PUBLIC,object);
        implementation.addInterface(contract);
        SootClass unrelated=klass("fixture.Other",Modifier.PUBLIC,object);
        Scene.v().setActiveHierarchy(new Hierarchy());
        Value a=dynamic(contract.getType()), b=dynamic(contract.getType());
        List<RefLikeType> types=types(a);
        check(types.contains(contract.getType()));
        check(types.contains(implementation.getType()));
        check(!types.contains(unrelated.getType()));
        Local compatible=Jimple.v().newLocal("callback",contract.getType());
        Local incompatible=Jimple.v().newLocal("other",unrelated.getType());
        check(types.equals(types(compatible)));
        check(Util.objValuesMayEqual(a,compatible));
        check(!Util.objValuesMayEqual(a,incompatible));
        check(Util.objValuesMustEqual(a,a,false));
        check(!Util.objValuesMustEqual(a,b,false));
        check(!Util.objValuesMustEqual(a,compatible,false));
        check(!Util.objValuesMustEqual(compatible,a,false));
        check(Util.objValuesMustEqual(compatible,compatible,false));
        Method alias=ObjVariable.class.getDeclaredMethod("mayAlias",Variable.class);
        alias.setAccessible(true);
        check((Boolean)alias.invoke(new ObjVariable(a,null),new ObjVariable(compatible,null)));
        check(!(Boolean)alias.invoke(new ObjVariable(a,null),new ObjVariable(incompatible,null)));
        Value array=dynamic(ArrayType.v(IntType.v(),1));
        check(types(array).get(0).equals(array.getType()));
        try { types(dynamic(IntType.v())); throw new AssertionError("Primitive accepted"); }
        catch (IllegalArgumentException expected) {checks++;}
        System.out.println("Passed " + checks + " lambda reference/alias model checks");
    }
}
