import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

/** No taint APIs or application dependencies: exercise a caller-sensitive handle. */
public final class GaletteCallerSensitiveProbe {
    public static void main(String[] args) throws Throwable {
        MethodHandle handle = MethodHandles.lookup().findStatic(Class.class, "forName",
                MethodType.methodType(Class.class, String.class));
        Class<?> result = (Class<?>) handle.invokeExact("java.lang.String");
        if (result != String.class) throw new AssertionError("caller-sensitive result");
        System.out.println("CALLER_SENSITIVE_OK");
    }
}
