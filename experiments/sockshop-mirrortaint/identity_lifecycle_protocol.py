"""Runtime reclamation counters never alter historical observation coordinates."""
from query_observation_planner import require


def validate(rows):
    headers=[r for r in rows if r.get('kind')=='start'];version=headers[0].get('identity_lifecycle_version',0)if len(headers)==1 else 0
    require(type(version)is int and version in (0,1),'Unsupported identity lifecycle protocol')
    if not version:
        require(not any(r.get('kind')=='metrics'and 'lifecycle'in r for r in rows),'Lifecycle counters without versioned header');return 0
    footers=[r for r in rows if r.get('kind')=='metrics'];require(len(footers)==1,'Lifecycle metrics footer absent/duplicate');counts=footers[0].get('lifecycle')
    require(isinstance(counts,dict),'Lifecycle counters absent')
    keys=('ids_allocated','ids_registered','ids_retired','ids_weak_cleared','ids_terminal_deferred','field_version_entries','field_versions_retired','field_cleanup_pending','array_version_entries','array_slot_entries')
    require(all(type(counts.get(k))is int and counts[k]>=0 for k in keys),'Lifecycle counter absent/invalid')
    require(counts['ids_allocated']==counts['ids_registered']+counts['ids_retired'],'Lifecycle identity allocation/retirement accounting differs')
    require(counts['ids_terminal_deferred']<=counts['ids_registered']and counts['field_cleanup_pending']<=counts['field_version_entries'],'Lifecycle pending counts differ')
    return 1
