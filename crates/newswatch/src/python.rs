use pyo3::prelude::*;
use pyo3::types::PyAny;

use crate::client::NewsClientCore;
use crate::models::NewsItem;

#[pyclass(name = "NewsClient")]
pub struct NewsClient {
    core: NewsClientCore,
}

#[pymethods]
impl NewsClient {
    #[new]
    #[pyo3(signature = (feeds, user_agent, rate_limit_secs=0.0))]
    fn new(
        feeds: Vec<(String, String, String)>,
        user_agent: String,
        rate_limit_secs: f64,
    ) -> PyResult<Self> {
        Ok(Self {
            core: NewsClientCore::from_tuples(feeds, user_agent, rate_limit_secs)?,
        })
    }

    #[pyo3(signature = (keywords, max_results=100))]
    fn fetch(&self, keywords: Vec<String>, max_results: usize) -> PyResult<Vec<NewsItem>> {
        self.core
            .fetch_blocking(&keywords, max_results)
            .map_err(Into::into)
    }

    #[pyo3(signature = (keywords, max_results=100))]
    fn fetch_async<'py>(
        &self,
        py: Python<'py>,
        keywords: Vec<String>,
        max_results: usize,
    ) -> PyResult<Bound<'py, PyAny>> {
        let core = self.core.clone();

        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let items = core
                .fetch_async_internal(&keywords, max_results)
                .await
                .map_err(|err| err.to_py_err())?;

            Python::attach(|py| {
                items
                    .into_iter()
                    .map(|item| Py::new(py, item))
                    .collect::<PyResult<Vec<Py<NewsItem>>>>()
            })
        })
    }
}
