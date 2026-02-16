use pyo3::prelude::*;

use crate::models::{Entity, EventMention};
use crate::tagger::CoreEntityTagger;

#[pyclass(name = "EntityTagger")]
pub struct EntityTagger {
    inner: CoreEntityTagger,
}

#[pymethods]
impl EntityTagger {
    #[new]
    #[pyo3(signature = (dictionary_path = None))]
    fn new(dictionary_path: Option<String>) -> PyResult<Self> {
        Ok(Self {
            inner: CoreEntityTagger::new(dictionary_path.as_deref())?,
        })
    }

    fn tag_text(&self, text: &str) -> PyResult<Vec<Entity>> {
        Ok(self.inner.tag_text(text))
    }

    fn detect_events(&self, text: &str) -> PyResult<Vec<EventMention>> {
        Ok(self.inner.detect_events(text))
    }

    fn tag_and_detect(&self, text: &str) -> PyResult<(Vec<Entity>, Vec<EventMention>)> {
        Ok(self.inner.tag_and_detect(text))
    }
}
