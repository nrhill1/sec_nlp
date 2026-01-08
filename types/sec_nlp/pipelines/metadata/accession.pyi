from sec_nlp.pipelines.types import (
    AnalysisResultDict as AnalysisResultDict,
    MetadataMap as MetadataMap,
)

def get_accession_from_metadata(metadata: MetadataMap | None) -> str: ...
def group_results_by_accession(
    results: list[AnalysisResultDict], fallback_meta: MetadataMap | None
) -> dict[str, list[AnalysisResultDict]]: ...
