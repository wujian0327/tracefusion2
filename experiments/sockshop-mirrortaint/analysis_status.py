"""Analysis capability limits are distinct from invalid execution evidence."""
class AnalysisLimit(ValueError):
    def __init__(self, stage, message):
        self.stage=stage
        super().__init__(stage+': '+message)


def failure_status(error):
    return 'analysis_limited' if isinstance(error,AnalysisLimit) else 'evidence_invalid'
