"""Inventory must preserve overloads, constructors and erased descriptors."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from flowdist_service_static import descriptor_types, inventory


class ServiceInventoryChecks(unittest.TestCase):
    def test_array_and_primitive_method_descriptor(self):
        self.assertEqual(descriptor_types('([[ILjava/util/List;[B)Ljava/lang/Object;'),
            ('java.lang.Object',['int[][]','java.util.List','byte[]']))
        with self.assertRaises(ValueError):descriptor_types('(I)Vextra')

    def test_original_generic_constructor_and_overloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); classes=root/'classes'; classes.mkdir()
            source=root/'Example.java'
            source.write_text('''package fixture;
import java.util.List;
public class Example<T> {
 static { System.setProperty("unused-inventory-fixture", "1"); }
 public Example(List<T> values) {}
 public T convert(T value) { return value; }
 public int convert(int value) { return value; }
 public void arrays(String[][] value) {}
}''')
            subprocess.run(['javac','--release','8','-d',str(classes),str(source)],check=True,capture_output=True)
            self.assertEqual(inventory(classes,root),[
                '<fixture.Example: int convert(int)>',
                '<fixture.Example: java.lang.Object convert(java.lang.Object)>',
                '<fixture.Example: void <clinit>()>',
                '<fixture.Example: void <init>(java.util.List)>',
                '<fixture.Example: void arrays(java.lang.String[][])>'])


if __name__=='__main__':unittest.main()
