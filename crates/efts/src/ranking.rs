//! Keyword extraction and document ranking algorithms.
//!
//! Provides YAKE, TF-IDF, RAKE, and TextRank algorithms via PyO3 bindings.

use pyo3::prelude::*;

use keyword_extraction::rake::{Rake, RakeParams};
use keyword_extraction::text_rank::{TextRank, TextRankParams};
use keyword_extraction::tf_idf::{TfIdf, TfIdfParams};
use keyword_extraction::yake::{Yake, YakeParams};
use stop_words::{get, LANGUAGE};

/// Result of keyword extraction: (keyword, score).
/// Lower scores indicate more important keywords for YAKE.
/// Higher scores indicate more important keywords for TF-IDF, RAKE, TextRank.
#[pyclass(name = "KeywordResult", frozen, module = "efts", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct KeywordResult {
    #[pyo3(get)]
    pub keyword: String,
    #[pyo3(get)]
    pub score: f64,
}

#[pymethods]
impl KeywordResult {
    fn __repr__(&self) -> String {
        format!(
            "KeywordResult(keyword='{}', score={:.4})",
            self.keyword, self.score
        )
    }
}

/// Result of document ranking: (document_index, score).
#[pyclass(name = "DocumentScore", frozen, module = "efts", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct DocumentScore {
    #[pyo3(get)]
    pub index: usize,
    #[pyo3(get)]
    pub score: f64,
}

#[pymethods]
impl DocumentScore {
    fn __repr__(&self) -> String {
        format!(
            "DocumentScore(index={}, score={:.4})",
            self.index, self.score
        )
    }
}

fn get_stop_words() -> Vec<String> {
    get(LANGUAGE::English)
        .iter()
        .map(|s| s.to_string())
        .collect()
}

/// YAKE keyword extractor.
///
/// YAKE (Yet Another Keyword Extractor) is an unsupervised automatic keyword
/// extraction method that uses text statistical features. Lower scores indicate
/// more important keywords.
///
/// Example:
///     extractor = YakeExtractor()
///     keywords = extractor.extract_keywords(text, top_n=10)
///     for kw in keywords:
///         print(f"{kw.keyword}: {kw.score}")
#[pyclass(name = "YakeExtractor", module = "efts")]
pub struct YakeExtractor {
    stop_words: Vec<String>,
    ngram_size: usize,
    threshold: f32,
    window_size: usize,
}

#[pymethods]
impl YakeExtractor {
    #[new]
    #[pyo3(signature = (ngram_size=3, threshold=0.85, window_size=2))]
    fn new(ngram_size: usize, threshold: f32, window_size: usize) -> Self {
        Self {
            stop_words: get_stop_words(),
            ngram_size,
            threshold,
            window_size,
        }
    }

    /// Extract keywords from text using YAKE algorithm.
    ///
    /// Args:
    ///     text: The text to extract keywords from.
    ///     top_n: Maximum number of keywords to return.
    ///
    /// Returns:
    ///     List of KeywordResult objects sorted by score (ascending - lower is better).
    #[pyo3(signature = (text, top_n=10))]
    fn extract_keywords(&self, text: &str, top_n: usize) -> Vec<KeywordResult> {
        if text.trim().is_empty() {
            return Vec::new();
        }

        // YakeParams::All takes: text, stop_words, punctuation, threshold, ngram, window_size
        let yake = Yake::new(YakeParams::All(
            text,
            &self.stop_words,
            None, // Use default punctuation
            self.threshold,
            self.ngram_size,
            self.window_size,
        ));

        yake.get_ranked_keyword_scores(top_n)
            .into_iter()
            .map(|(keyword, score)| KeywordResult {
                keyword,
                score: score as f64,
            })
            .collect()
    }

    fn __repr__(&self) -> String {
        format!(
            "YakeExtractor(ngram_size={}, threshold={}, window_size={})",
            self.ngram_size, self.threshold, self.window_size
        )
    }
}

/// TF-IDF document ranker.
///
/// TF-IDF (Term Frequency-Inverse Document Frequency) ranks documents based on
/// the importance of query terms within a corpus. Higher scores indicate more
/// relevant documents.
///
/// Example:
///     ranker = TfIdfRanker()
///     ranker.add_documents(["doc1 text", "doc2 text", "doc3 text"])
///     scores = ranker.rank_by_query(["search", "terms"], top_n=10)
#[pyclass(name = "TfIdfRanker", module = "efts")]
pub struct TfIdfRanker {
    documents: Vec<String>,
    stop_words: Vec<String>,
}

#[pymethods]
impl TfIdfRanker {
    #[new]
    fn new() -> Self {
        Self {
            documents: Vec::new(),
            stop_words: get_stop_words(),
        }
    }

    /// Add documents to the corpus.
    fn add_documents(&mut self, documents: Vec<String>) {
        self.documents.extend(documents);
    }

    /// Clear all documents from the corpus.
    fn clear(&mut self) {
        self.documents.clear();
    }

    /// Get the number of documents in the corpus.
    fn document_count(&self) -> usize {
        self.documents.len()
    }

    /// Extract top keywords from the entire corpus using TF-IDF.
    ///
    /// Args:
    ///     top_n: Maximum number of keywords to return.
    ///
    /// Returns:
    ///     List of KeywordResult objects sorted by TF-IDF score (descending).
    #[pyo3(signature = (top_n=10))]
    fn extract_keywords(&self, top_n: usize) -> Vec<KeywordResult> {
        if self.documents.is_empty() {
            return Vec::new();
        }

        // TfIdfParams::UnprocessedDocuments takes: documents, stop_words, punctuation
        let tf_idf = TfIdf::new(TfIdfParams::UnprocessedDocuments(
            &self.documents,
            &self.stop_words,
            None, // Use default punctuation
        ));

        tf_idf
            .get_ranked_word_scores(top_n)
            .into_iter()
            .map(|(keyword, score)| KeywordResult {
                keyword,
                score: score as f64,
            })
            .collect()
    }

    /// Rank documents by relevance to query terms.
    ///
    /// Args:
    ///     query_terms: List of search terms.
    ///     top_n: Maximum number of documents to return.
    ///
    /// Returns:
    ///     List of DocumentScore objects sorted by relevance (descending).
    #[pyo3(signature = (query_terms, top_n=10))]
    fn rank_by_query(&self, query_terms: Vec<String>, top_n: usize) -> Vec<DocumentScore> {
        if self.documents.is_empty() || query_terms.is_empty() {
            return Vec::new();
        }

        let tf_idf = TfIdf::new(TfIdfParams::UnprocessedDocuments(
            &self.documents,
            &self.stop_words,
            None,
        ));

        // Get TF-IDF scores for each term
        let term_scores: Vec<(String, f32)> = tf_idf.get_ranked_word_scores(1000);
        let term_score_map: std::collections::HashMap<String, f32> =
            term_scores.into_iter().collect();

        // Score each document based on query term presence and TF-IDF weights
        let mut doc_scores: Vec<(usize, f64)> = self
            .documents
            .iter()
            .enumerate()
            .map(|(idx, doc)| {
                let doc_lower = doc.to_lowercase();
                let score: f64 = query_terms
                    .iter()
                    .map(|term| {
                        let term_lower = term.to_lowercase();
                        if doc_lower.contains(&term_lower) {
                            term_score_map.get(&term_lower).copied().unwrap_or(1.0) as f64
                        } else {
                            0.0
                        }
                    })
                    .sum();
                (idx, score)
            })
            .filter(|(_, score)| *score > 0.0)
            .collect();

        doc_scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        doc_scores.truncate(top_n);

        doc_scores
            .into_iter()
            .map(|(index, score)| DocumentScore { index, score })
            .collect()
    }

    fn __repr__(&self) -> String {
        format!("TfIdfRanker(documents={})", self.documents.len())
    }
}

/// RAKE keyword extractor.
///
/// RAKE (Rapid Automatic Keyword Extraction) identifies key phrases by analyzing
/// word frequency and co-occurrence. Higher scores indicate more important keywords.
///
/// Example:
///     extractor = RakeExtractor()
///     keywords = extractor.extract_keywords(text, top_n=10)
#[pyclass(name = "RakeExtractor", module = "efts")]
pub struct RakeExtractor {
    stop_words: Vec<String>,
}

#[pymethods]
impl RakeExtractor {
    #[new]
    fn new() -> Self {
        Self {
            stop_words: get_stop_words(),
        }
    }

    /// Extract keywords from text using RAKE algorithm.
    ///
    /// Args:
    ///     text: The text to extract keywords from.
    ///     top_n: Maximum number of keywords to return.
    ///
    /// Returns:
    ///     List of KeywordResult objects sorted by score (descending - higher is better).
    #[pyo3(signature = (text, top_n=10))]
    fn extract_keywords(&self, text: &str, top_n: usize) -> Vec<KeywordResult> {
        if text.trim().is_empty() {
            return Vec::new();
        }

        let rake = Rake::new(RakeParams::WithDefaults(text, &self.stop_words));

        // RAKE uses get_ranked_keyword_scores, not get_ranked_word_scores
        rake.get_ranked_keyword_scores(top_n)
            .into_iter()
            .map(|(keyword, score)| KeywordResult {
                keyword,
                score: score as f64,
            })
            .collect()
    }

    fn __repr__(&self) -> String {
        "RakeExtractor()".to_string()
    }
}

/// TextRank keyword extractor.
///
/// TextRank is a graph-based ranking algorithm for keyword extraction, similar to
/// PageRank. Higher scores indicate more important keywords.
///
/// Example:
///     extractor = TextRankExtractor()
///     keywords = extractor.extract_keywords(text, top_n=10)
#[pyclass(name = "TextRankExtractor", module = "efts")]
pub struct TextRankExtractor {
    stop_words: Vec<String>,
    window_size: usize,
    damping: f32,
    tolerance: f32,
    phrase_length: Option<usize>,
}

#[pymethods]
impl TextRankExtractor {
    #[new]
    #[pyo3(signature = (window_size=2, damping=0.85, tolerance=0.00005, phrase_length=None))]
    fn new(window_size: usize, damping: f32, tolerance: f32, phrase_length: Option<usize>) -> Self {
        Self {
            stop_words: get_stop_words(),
            window_size,
            damping,
            tolerance,
            phrase_length,
        }
    }

    /// Extract keywords from text using TextRank algorithm.
    ///
    /// Args:
    ///     text: The text to extract keywords from.
    ///     top_n: Maximum number of keywords to return.
    ///
    /// Returns:
    ///     List of KeywordResult objects sorted by score (descending - higher is better).
    #[pyo3(signature = (text, top_n=10))]
    fn extract_keywords(&self, text: &str, top_n: usize) -> Vec<KeywordResult> {
        if text.trim().is_empty() {
            return Vec::new();
        }

        // TextRankParams::All takes: text, stop_words, punctuation, window_size, damping, tolerance, phrase_length
        let text_rank = TextRank::new(TextRankParams::All(
            text,
            &self.stop_words,
            None, // Use default punctuation
            self.window_size,
            self.damping,
            self.tolerance,
            self.phrase_length,
        ));

        text_rank
            .get_ranked_word_scores(top_n)
            .into_iter()
            .map(|(keyword, score)| KeywordResult {
                keyword,
                score: score as f64,
            })
            .collect()
    }

    fn __repr__(&self) -> String {
        format!(
            "TextRankExtractor(window_size={}, damping={}, tolerance={}, phrase_length={:?})",
            self.window_size, self.damping, self.tolerance, self.phrase_length
        )
    }
}

/// Score a single document against a list of keywords.
///
/// Args:
///     text: The document text to score.
///     keywords: List of keywords to search for.
///     case_insensitive: Whether to perform case-insensitive matching.
///
/// Returns:
///     Tuple of (total_hits, keyword_counts) where keyword_counts is a dict
///     mapping each found keyword to its count.
#[pyfunction]
#[pyo3(signature = (text, keywords, case_insensitive=true))]
pub fn score_document_keywords(
    text: &str,
    keywords: Vec<String>,
    case_insensitive: bool,
) -> (u32, std::collections::HashMap<String, u32>) {
    let haystack = if case_insensitive {
        text.to_lowercase()
    } else {
        text.to_string()
    };

    let mut counts: std::collections::HashMap<String, u32> = std::collections::HashMap::new();
    let mut total = 0u32;

    for keyword in keywords {
        let needle = if case_insensitive {
            keyword.to_lowercase()
        } else {
            keyword.clone()
        };

        let count = haystack.matches(&needle).count() as u32;
        if count > 0 {
            counts.insert(keyword, count);
            total += count;
        }
    }

    (total, counts)
}

/// Rank multiple documents by keyword hits.
///
/// Args:
///     documents: List of document texts.
///     keywords: List of keywords to search for.
///     case_insensitive: Whether to perform case-insensitive matching.
///     min_hits: Minimum number of keyword hits required to include a document.
///
/// Returns:
///     List of DocumentScore objects sorted by total hits (descending).
#[pyfunction]
#[pyo3(signature = (documents, keywords, case_insensitive=true, min_hits=0))]
pub fn rank_documents_by_keywords(
    documents: Vec<String>,
    keywords: Vec<String>,
    case_insensitive: bool,
    min_hits: u32,
) -> Vec<DocumentScore> {
    let mut scores: Vec<(usize, f64)> = documents
        .iter()
        .enumerate()
        .filter_map(|(idx, doc)| {
            let (total, _) = score_document_keywords(doc, keywords.clone(), case_insensitive);
            if total >= min_hits {
                Some((idx, total as f64))
            } else {
                None
            }
        })
        .collect();

    scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    scores
        .into_iter()
        .map(|(index, score)| DocumentScore { index, score })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_yake_extractor() {
        let extractor = YakeExtractor::new(2, 0.9, 1);
        let text = "Machine learning is a subset of artificial intelligence. \
                    Machine learning algorithms learn from data.";
        let keywords = extractor.extract_keywords(text, 5);
        assert!(!keywords.is_empty());
    }

    #[test]
    fn test_rake_extractor() {
        let extractor = RakeExtractor::new();
        let text =
            "Compatibility of systems of linear constraints over the set of natural numbers.";
        let keywords = extractor.extract_keywords(text, 5);
        assert!(!keywords.is_empty());
    }

    #[test]
    fn test_tfidf_ranker() {
        let mut ranker = TfIdfRanker::new();
        ranker.add_documents(vec![
            "The quick brown fox jumps over the lazy dog".to_string(),
            "A fast brown fox leaps across the sleepy hound".to_string(),
            "The cat sat on the mat".to_string(),
        ]);
        assert_eq!(ranker.document_count(), 3);

        let scores = ranker.rank_by_query(vec!["fox".to_string(), "brown".to_string()], 10);
        assert!(!scores.is_empty());
    }

    #[test]
    fn test_score_document_keywords() {
        let text = "The Company recorded warranty reserves of $10 million. \
                    Warranty claims increased during the period.";
        let keywords = vec!["warranty".to_string(), "reserves".to_string()];
        let (total, counts) = score_document_keywords(text, keywords, true);
        assert_eq!(total, 3);
        assert_eq!(counts.get("warranty"), Some(&2));
        assert_eq!(counts.get("reserves"), Some(&1));
    }

    #[test]
    fn test_rank_documents_by_keywords() {
        let docs = vec![
            "This document mentions warranty once.".to_string(),
            "Warranty warranty warranty - lots of warranty claims.".to_string(),
            "No relevant keywords here.".to_string(),
        ];
        let keywords = vec!["warranty".to_string()];
        let scores = rank_documents_by_keywords(docs, keywords, true, 1);
        assert_eq!(scores.len(), 2);
        assert_eq!(scores[0].index, 1); // Second doc has most hits
    }
}
