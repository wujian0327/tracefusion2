"""Integrity boundaries for baseline downloads and imported upstream code."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

spec=importlib.util.spec_from_file_location('baseline_manage',Path(__file__).with_name('manage.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class IntegrityTests(unittest.TestCase):
    def test_bad_download_is_not_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.write_bytes(b'unexpected version');dest=root/'dest/tool.jar'
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                m.download(source.as_uri(),dest,'0'*64)
            self.assertFalse(dest.exists())

    def test_verified_download_survives_an_unavailable_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.write_bytes(b'pinned upstream artifact');dest=root/'dest/tool.jar';expected=m.sha(source)
            m.download(source.as_uri(),dest,expected);source.unlink()
            m.download(source.as_uri(),dest,expected)
            self.assertEqual(dest.read_bytes(),b'pinned upstream artifact')
            dest.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Checksum mismatch'):m.download(source.as_uri(),dest,expected)
            self.assertEqual(dest.read_bytes(),b'changed')

    def test_archive_rejects_traversal_and_links_before_writing(self):
        for name,link in [('root/../../escape',False),('/absolute',False),('root/link',True)]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);archive=root/'source.zip';dest=root/'source'
                with ZipFile(archive,'w') as z:
                    z.writestr('root/valid','okay');entry=ZipInfo(name)
                    if link:entry.external_attr=0o120777<<16
                    z.writestr(entry,'outside')
                with self.assertRaises(ValueError):m.unpack_source(archive,dest)
                self.assertFalse(dest.exists())

    def test_multiple_archive_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'source.zip'
            with ZipFile(archive,'w') as z:z.writestr('a/src/A.java','a');z.writestr('b/src/B.java','b')
            with self.assertRaisesRegex(ValueError,'one upstream archive root'):m.unpack_source(archive,root/'out')

    def test_source_change_and_additional_java_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'source';src.mkdir();file=src/'A.java';file.write_text('class A {}');hashes={'A.java':m.sha(file)}
            with patch.object(m,'load',return_value=hashes):
                self.assertEqual(m.verify_source(root),hashes)
                file.write_text('class A {int injected;}')
                with self.assertRaisesRegex(ValueError,'source changed'):m.verify_source(root)
                file.write_text('class A {}');(src/'Injected.java').write_text('class Injected {}')
                with self.assertRaisesRegex(ValueError,'inventory differs'):m.verify_source(root)

    def test_missing_tool_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertFalse(m.doctor(Path(tmp),['mirrortaint']))
            self.assertIn('"ready": false',output.getvalue())


if __name__=='__main__':unittest.main()
