"""A true badge must not admit different captures, builds, or audit evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import audit_current_acceptance as a


class ReceiptTests(unittest.TestCase):
    def test_capture_and_auditor_change_invalidates_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);proof=root/'proof';proof.write_text('audited')
            current={'build_sha256':'one','capture_sha256':{'events':'one'},'audit_sources':{'auditor':'one'}}
            (root/'current-acceptance.json').write_text(json.dumps({'kind':'current-two-application-acceptance',
                'all_passed':True,'signature':current,'audit_evidence_sha256':{'proof':a.sha(proof)}}))
            with patch.object(a,'check'),patch.object(a,'signature',return_value=current):a.verify(root,root,root)
            for part in ('build_sha256','capture_sha256','audit_sources'):
                changed=dict(current);changed[part]='changed'
                with patch.object(a,'check'),patch.object(a,'signature',return_value=changed):
                    with self.assertRaisesRegex(ValueError,'hashes differ'):a.verify(root,root,root)
            proof.write_text('tampered')
            with patch.object(a,'check'),patch.object(a,'signature',return_value=current):
                with self.assertRaisesRegex(ValueError,'evidence changed'):a.verify(root,root,root)


if __name__=='__main__':unittest.main()
