class RetrievalHit: ...
class RetrieveResult: ...

class RetrieveSettings:
    pipeline_type: str

class RetrievePipeline:
    pipeline_type: str
    config: RetrieveSettings
