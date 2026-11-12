/** Plain JVM safety counterexample. Not a propagation or business benchmark. */
public class ConstructorNativeDispatchProbe {
    static class Old {int value=7;}
    static Old old;
    static int callbacks;
    static class Override extends IllegalArgumentException {
        Override(String s){super(s);}
        public synchronized Throwable fillInStackTrace(){callbacks++;old.value=9;return this;}
    }
    public static void main(String[] args){
        old=new Old();callbacks=0;new IllegalArgumentException("same");
        if(old.value!=7||callbacks!=0)throw new AssertionError();
        System.out.println("plain: old=7 callbacks=0");
        new Override("same");
        if(old.value!=9||callbacks!=1)throw new AssertionError();
        System.out.println("override: old=9 callbacks=1");
    }
}
