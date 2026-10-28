import java.util.*;
/** Independent library semantics controls, not a claimed real service path. */
public final class CollectionServiceFixture {
    public static class Input {
        private List<String> labels; private List<Integer> samples; private double scale;
        public Input(List<String> a,List<Integer> b,double c){labels=a;samples=b;scale=c;}
        public List<String> getLabels(){return labels;}
        public List<Integer> getSamples(){return samples;}
        public double getScale(){return scale;}
    }
    public static final class OverriddenInput extends Input {
        private double other=2.5;
        public OverriddenInput(List<String> a,List<Integer>b){super(a,b,2.5);}
        public double getScale(){return other;}
    }
    public static final class Output {
        private Map<String,String> cells;
        public Map<String,String> getCells(){return cells;}
        public void setCells(Map<String,String> v){cells=v;}
    }
    public static void irrelevant(Input in){if(in.getScale()>0)System.out.println("IRRELEVANT_HELPER_BRANCH");}
    public static Output transform(Input in,String left,String right,boolean zero) {
        irrelevant(in);
        Output out=new Output();int a=in.getLabels().indexOf(left),b=in.getLabels().indexOf(right);
        Map<String,String> values=new HashMap<>();
        // Irrelevant collection and field work must not join the target slice.
        StringBuilder noise=new StringBuilder();noise.append(in.getScale());noise.toString();
        try {
            int delta=0;if(!zero)delta=in.getSamples().get(b).intValue()-in.getSamples().get(a).intValue();
            double value=delta*in.getScale();
            values.put("a/b~c",new StringBuilder().append("").append(value).toString());
            values.put("other",new StringBuilder().append("").append(value).toString());
            // Overwrite must erase the old source set of this entry.
            if(zero)values.put("other","constant");
        } catch(Exception e) {values.put("a/b~c","fallback");values.put("other","fallback");}
        out.setCells(values);return out;
    }
    public static void main(String[] args) throws Exception {
        List<String> labels=Arrays.asList("same","middle","last");
        Input equal=new Input(labels,Arrays.asList(7,7,7),2.5);
        Input different=new Input(labels,Arrays.asList(7,11,19),1.25);
        if(args.length>0){
            if(args[0].equals("mutation")){
                try{Class.forName("CollectionServiceHooks").getMethod("received",Object.class).invoke(null,equal.getSamples());}catch(ClassNotFoundException original){}
                equal.getSamples().set(0,7);System.out.println("MUTATION_BUSINESS_RESULT="+equal.getSamples());return;
            }
            if(args[0].equals("virtual")){
                System.out.println("DISPATCH_BUSINESS_RESULT="+transform(new OverriddenInput(labels,Arrays.asList(7,7,7)),"same","last",false).getCells());return;
            }
        }
        System.out.println(transform(equal,"same","last",false).getCells());
        System.out.println(transform(different,"middle","last",false).getCells());
        System.out.println(transform(equal,"missing","last",false).getCells());
        System.out.println(transform(equal,"same","last",true).getCells());
        System.out.println(transform(equal,"same","last",false).getCells());
    }
}
