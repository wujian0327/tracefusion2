package lineage.business;

/** Ordinary single-entry process cache. No observer fields or provenance labels. */
public final class Cache {
    public static final class Request {
        public int op; // 0 read, 1 replace, 2 overwrite, 3 public constant
        public String key;
        public String value;
        public String fallback;
    }
    public static final class Cell {
        public String text;
        public Cell(String text) { this.text = text; }
    }
    public static final class Reply {
        public String text;
        public Reply() {}
        public Reply(String text) { this.text = text; }
    }
    public String key;
    public Cell cell;

    // Separate ordinary service methods for the disclosed read-only diagnostic.
    public void replace(Request input) { key = input.key; cell = new Cell(input.value); }
    public void overwrite(Request input) { cell.text = input.value; }
    public void publish() { cell.text = "PUBLIC"; }
    public Reply read(Request input) {
        if (cell != null && input.key.equals(key)) return new Reply(cell.text);
        return new Reply(input.fallback);
    }

    public Reply process(Request input) {
        if (input.op == 1) {
            key = input.key;
            cell = new Cell(input.value);
        } else if (input.op == 2) {
            cell.text = input.value;
        } else if (input.op == 3) {
            cell.text = "PUBLIC";
        }
        if (cell != null && input.key.equals(key)) return new Reply(cell.text);
        return new Reply(input.fallback);
    }
}
