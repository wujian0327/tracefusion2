from pathlib import Path
import subprocess
import tempfile
import unittest


class ResumptionProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='flowdist-resumption-check-');root=Path(cls.temp.name)
        tool=root/'tool';tool.mkdir();app=root/'app';app.mkdir();monitor=root/'OTMonitor.java';fixture=root/'Fixture.java'
        asm=[Path('artifacts/java-collection-deps')/(name+'-9.7.1.jar') for name in ('asm','asm-tree')]
        subprocess.run(['javac','--release','8','-cp',':'.join(map(str,asm)),'-d',str(tool),
            str(Path(__file__).with_name('FlowDistResumeCalls.java'))],capture_output=True,check=True)
        monitor.write_text('''package disttaint;
public class OTMonitor {
 public static final java.util.List<String> events=new java.util.ArrayList<>();
 public static void enter(String m){events.add("E:"+m);}
 public static void returnInto(String m,String c){events.add("R:"+m+"|"+c);}
}''')
        fixture.write_text('''import disttaint.OTMonitor;
public class Fixture {
 static int normal(){OTMonitor.enter("<Fixture: int normal()>");return Math.abs(-7);}
 static double wide(){OTMonitor.enter("<Fixture: double wide()>");return Math.sqrt(9d);}
 static int bad(){OTMonitor.enter("<Fixture: int bad()>");return Integer.parseInt("bad");}
 static void legacy(){OTMonitor.enter("<Fixture: void legacy()>");OTMonitor.returnInto("legacy","existing");}
 static int unmonitored(){return Math.abs(-9);}
 public static void main(String[]args){
  System.out.println("VALUE="+normal()+":"+wide());
  try{bad();throw new AssertionError("lost exception");}catch(NumberFormatException expected){}
  legacy();if(unmonitored()!=9)throw new AssertionError("changed unmonitored call");
  boolean resumedBad=false,resumedUnmonitored=false;int legacy=0;
  for(String e:OTMonitor.events){if(e.startsWith("R:")&&e.contains("parseInt"))resumedBad=true;
   if(e.startsWith("R:")&&e.contains("unmonitored"))resumedUnmonitored=true;
   if(e.equals("R:legacy|existing"))legacy++;}
  System.out.println("FAILED_CALL_RESUMED="+resumedBad);
  System.out.println("LEGACY_PROBE_COUNT="+legacy);
  System.out.println("UNMONITORED_RESUMED="+resumedUnmonitored);
 }
}''')
        subprocess.run(['javac','--release','8','-d',str(app),str(monitor),str(fixture)],capture_output=True,check=True)
        modified=root/'Fixture.modified.class'
        patched=subprocess.run(['java','-cp',':'.join(map(str,[tool,*asm])),'FlowDistResumeCalls',
            str(app/'Fixture.class'),str(modified)],capture_output=True,text=True,check=True)
        (app/'Fixture.class').write_bytes(modified.read_bytes())
        cls.output=subprocess.run(['java','-Xverify:all','-cp',str(app),'Fixture'],capture_output=True,text=True,check=True).stdout
        cls.patch_output=patched.stdout

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_int_and_wide_return_values_preserved(self):self.assertIn('VALUE=7:3.0',self.output)
    def test_exception_does_not_emit_successful_return(self):self.assertIn('FAILED_CALL_RESUMED=false',self.output)
    def test_existing_monitor_probe_not_recursively_instrumented(self):self.assertIn('LEGACY_PROBE_COUNT=1',self.output)
    def test_unentered_method_not_given_return_events(self):self.assertIn('UNMONITORED_RESUMED=false',self.output)
    def test_probe_removal_restores_other_class_data(self):self.assertIn('inverse-canonical-comparison=passed',self.patch_output)


if __name__=='__main__':unittest.main()
