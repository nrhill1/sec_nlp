use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use pyo3::prelude::*;
use pyo3::types::PyAny;
use tokio::sync::Notify;

use crate::client::NewsClientCore;
use crate::models::NewsItem;

#[pyclass(name = "NewsClient")]
pub struct NewsClient {
    core: NewsClientCore,
    active: Arc<ActiveRequests>,
}

#[derive(Default)]
struct ActiveRequests {
    count: AtomicUsize,
    changed: Notify,
}

impl ActiveRequests {
    fn begin(self: &Arc<Self>) -> RequestGuard {
        self.count.fetch_add(1, Ordering::SeqCst);
        RequestGuard(Arc::clone(self))
    }

    async fn wait_idle(&self) {
        loop {
            let notified = self.changed.notified();
            tokio::pin!(notified);
            notified.as_mut().enable();
            if self.count.load(Ordering::SeqCst) == 0 {
                return;
            }
            notified.await;
        }
    }
}

struct RequestGuard(Arc<ActiveRequests>);

impl Drop for RequestGuard {
    fn drop(&mut self) {
        if self.0.count.fetch_sub(1, Ordering::SeqCst) == 1 {
            self.0.changed.notify_waiters();
        }
    }
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
            active: Arc::default(),
        })
    }

    #[pyo3(signature = (keywords, max_results=100))]
    fn fetch(
        &self,
        py: Python<'_>,
        keywords: Vec<String>,
        max_results: usize,
    ) -> PyResult<Vec<NewsItem>> {
        py.detach(|| self.core.fetch_blocking(&keywords, max_results))
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
        let guard = self.active.begin();

        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let _request = guard;
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

    /// Wait until cancelled native request futures have actually been dropped.
    fn wait_idle_async<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let active = Arc::clone(&self.active);
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            active.wait_idle().await;
            Ok(())
        })
    }
}
