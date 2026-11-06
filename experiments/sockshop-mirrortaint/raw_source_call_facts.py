"""Capture-local RAW call candidates for independent scoring, never propagation."""
from collections import defaultdict

class RawSourceCallFacts:
 def __init__(self,rows):
  self.rows=rows;self.candidates=defaultdict(list)
  for position,row in enumerate(rows):
   kind=row['kind']
   if kind in('source-call-enter','source-call-exit'):key=row.get('source_call_id')
   elif kind in('collection-call-enter','collection-call-exit'):key=row.get('call_id')
   else:continue
   self.candidates[(kind,key)].append((position,row))
 def matching(self,rows,source):
  if rows is not self.rows:raise ValueError('Raw source index belongs to another capture')
  kinds=('source-call-enter','source-call-exit')if source.get('source_scope')=='observation-only-call'else('collection-call-enter','collection-call-exit')
  # Keep all candidates, duplicates and original order. The original validator
  # still checks cardinality, scope, Frame, callee, caller, PC and interval.
  return [row for _,row in sorted((item for kind in kinds for item in self.candidates[(kind,source.get('source_call_id'))]),key=lambda pair:pair[0])]
