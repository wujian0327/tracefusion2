package demo;

/** Repeated original sum calls; whole-process diagnostic cost, no steady-state claim. */
public final class Bench {
    public static void main(String[] args) {
        int rounds = Integer.parseInt(args[0]);
        Cell left = new Cell(17), right = new Cell(17);
        long checksum = 0;
        for (int i = 0; i < rounds; i++) checksum += Subject.sum(left, right, 3);
        System.out.println(checksum);
    }
}
