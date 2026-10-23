"""Finite immutable JDK value semantics; domain limits remain explicit."""
import re
from analysis_status import AnalysisLimit

def utf16_length(value):return len(value.encode('utf-16-le','surrogatepass'))//2

def literal_split(value,delimiter):
    if len(delimiter)!=1 or ord(delimiter)>127 or delimiter in '.$|()[{^?*+\\':
        raise AnalysisLimit('literal-string-split','Only one non-regex ASCII delimiter is modeled')
    parts=value.split(delimiter)
    if value:
        while parts and parts[-1]=='':parts.pop()
    return parts

def decimal_int(value):
    if not re.fullmatch(r'[+-]?[0-9]+',value):raise AnalysisLimit('decimal-parse','Only normal ASCII decimal parses are modeled')
    result=int(value)
    if not -2**31<=result<2**31:raise AnalysisLimit('decimal-parse','Outside successful JVM int range')
    return result
