import java.util.*;

/** Independent semantic program, never used as a substitute for original apps. */
public final class ExecutionKernelFixture {
    public static final class Item {
        private String label;private List<String> flags;
        public Item(String label,List<String> flags){this.label=label;this.flags=flags;}
        public String getLabel(){return label;}public List<String> getFlags(){return flags;}
        public void setLabel(String label){this.label=label;}
    }
    public static final class Output {
        private List<String> data;
        public Output(List<String> data){this.data=data;}public List<String> getData(){return data;}
    }
    public static Output filter(List<Item> input,String wanted){
        List<String> output=new ArrayList<>();
        for(Item item:input){if(item.getFlags().contains(wanted))output.add(item.getLabel());}
        return new Output(output);
    }
    public static Output counted(List<Item> input){
        List<String> output=new ArrayList<>();
        for(int i=0;i<input.size();i++)output.add(input.get(i).getLabel());
        return new Output(output);
    }
    static String opaque(Item input){return input.getLabel();}
    public static Output overwrite(Item target,Item source){
        target.setLabel(source.getLabel());List<String> out=new ArrayList<>();out.add(target.getLabel());return new Output(out);
    }
    public static Output unrelated(Item target,Item source){
        target.setLabel("changed");List<String> out=new ArrayList<>();out.add(source.getLabel());return new Output(out);
    }
    public static Output constantOverwrite(Item target){
        target.setLabel("same");List<String> out=new ArrayList<>();out.add(target.getLabel());return new Output(out);
    }
    public static Output opaqueResult(List<Item> input){
        List<String> output=new ArrayList<>();output.add(opaque(input.get(0)));return new Output(output);
    }
    static List<String> flags(String... xs){return new ArrayList<>(Arrays.asList(xs));}
    static List<Item> items(Item... xs){return new ArrayList<>(Arrays.asList(xs));}
    public static void main(String[] args){
        Item a=new Item("same",flags("yes")),b=new Item("same",flags("no")),c=new Item("same",flags("yes"));
        List<Item> input=items(a,b,c);
        if(args.length>0&&args[0].equals("overwrite")){overwrite(a,c);return;}
        if(args.length>0&&args[0].equals("unrelated")){unrelated(a,c);return;}
        if(args.length>0&&args[0].equals("constant-overwrite")){constantOverwrite(a);return;}
        if(args.length>0&&args[0].equals("opaque")){opaqueResult(input);return;}
        if(args.length>0&&args[0].equals("counted")){counted(input);counted(items());counted(items(c,a));return;}
        filter(input,"yes");filter(input,"absent");filter(items(),"yes");filter(items(c,a),"yes");
        try{filter(null,"yes");}catch(NullPointerException expected){System.out.println("EXPECTED_ABORT");}
        a.setLabel("updated");filter(input,"yes");filter(input,"no");
    }
}
