mod dictionary;
mod error;
pub mod events;
pub mod models;
pub mod patterns;
mod python;
pub mod tagger;

use pyo3::prelude::*;

#[pymodule]
fn entity(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<python::EntityTagger>()?;
    m.add_class::<models::Entity>()?;
    m.add_class::<models::EventMention>()?;
    Ok(())
}
