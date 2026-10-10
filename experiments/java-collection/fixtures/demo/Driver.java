package demo;
/** Setup/output outside the declared capture boundary. */
public final class Driver {
    public static void main(String[] args) throws Exception {
        String test = args[0];
        Cell a = new Cell(17), b = new Cell(17);
        int result;
        switch (test) {
            case "left": result = Subject.choose(a, b, 1); break;
            case "right": result = Subject.choose(a, b, 0); break;
            case "alias": result = Subject.choose(a, a, 0); break;
            case "overwrite": result = Subject.overwrite(a, b); break;
            case "nested": result = Subject.nested(a, b, 0); break;
            case "loop": result = Subject.sum(a, b, 3); break;
            case "null":
                try { Subject.choose(null, b, 1); throw new AssertionError("expected null failure"); }
                catch (NullPointerException expected) { System.out.println("caught-null"); return; }
            case "threads":
                Subject.choose(a, b, 1);
                Thread t = new Thread(() -> Subject.choose(a, b, 0)); t.start(); t.join();
                result = 17; break;
            case "unsupported": result = Unsupported.array(new int[]{17}); break;
            case "external": result = Unsupported.External.abs(-17); break;
            case "handler": result = Unsupported.Handler.divide(0); break;
            case "volatile": result = Unsupported.VolatileRead.read(new Unsupported.VolatileCell()); break;
            case "gc":
                Subject.choose(a, b, 1); System.gc();
                result = Subject.choose(a, b, 0); break;
            default: throw new IllegalArgumentException(test);
        }
        System.out.println(result);
    }
}
