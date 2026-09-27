// crates/market/src/session.rs
//! Cancellable fresh market requests sharing one HTTP connection pool.

use std::future::Future;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use pyo3::exceptions::{PyConnectionError, PyRuntimeError, PyTimeoutError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyList};
use tokio::sync::Notify;
use yahoo_finance_api::{YahooConnector, YahooError};

use crate::api::{filter_quotes_by_range, parse_date_range, unix_ts};
use crate::cache::range_cache;
use crate::types::to_py_err;

fn source_error(error: YahooError) -> PyErr {
    match error {
        YahooError::FetchFailed(status) => {
            PyRuntimeError::new_err(format!("Yahoo fetch failed (status {status})"))
        }
        YahooError::ConnectionFailed(cause) if cause.is_timeout() => {
            PyTimeoutError::new_err(cause.to_string())
        }
        YahooError::ConnectionFailed(cause) if cause.is_connect() || cause.is_body() => {
            PyConnectionError::new_err(cause.to_string())
        }
        other => to_py_err(other),
    }
}

fn cancellable_request<F>(py: Python<'_>, request: F) -> PyResult<Bound<'_, PyAny>>
where
    F: Future<Output = PyResult<Py<PyList>>> + Send + 'static,
{
    pyo3_async_runtimes::tokio::future_into_py(py, request)
}

/// Own a shared Yahoo connector without fetching data during construction.
#[pyclass]
pub struct MarketSession {
    provider: Arc<YahooConnector>,
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
impl MarketSession {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(Self {
            provider: Arc::new(YahooConnector::new().map_err(to_py_err)?),
            active: Arc::default(),
        })
    }

    /// Fetch fresh quotes; cancelling the Python future drops the HTTP future.
    fn retrieve_range_async<'py>(
        &self,
        py: Python<'py>,
        ticker: String,
        date_range: String,
    ) -> PyResult<Bound<'py, PyAny>> {
        let (start, end) = parse_date_range(&date_range)?;
        let start_ts = unix_ts(&start)?;
        let end_ts = unix_ts(&end)?;
        let provider = Arc::clone(&self.provider);
        let guard = self.active.begin();
        cancellable_request(py, async move {
            let _request = guard;
            let response = tokio::time::timeout(
                Duration::from_secs(20),
                provider.get_quote_history(&ticker, start, end),
            )
            .await
            .map_err(|_| PyTimeoutError::new_err("market request exceeded 20 seconds"))?
            .map_err(source_error)?;
            let quotes =
                filter_quotes_by_range(response.quotes().map_err(to_py_err)?, start_ts, end_ts);
            // Explicit refreshes bypass reads but populate the specialist cache.
            range_cache().insert(&ticker, &date_range, quotes.clone());
            Python::attach(|py| {
                let result = PyList::empty(py);
                for quote in quotes {
                    result.append(quote.to_py_dict(py)?)?;
                }
                Ok(result.unbind())
            })
        })
    }

    /// Acknowledge native cleanup after cancelling Python request futures.
    fn wait_idle_async<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let active = Arc::clone(&self.active);
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            active.wait_idle().await;
            Ok(())
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::ffi::c_str;
    use pyo3::types::{PyDict, PyModule};
    use std::sync::atomic::AtomicBool;
    use std::sync::OnceLock;

    static STARTED: AtomicBool = AtomicBool::new(false);
    static DROPPED: AtomicBool = AtomicBool::new(false);
    static ACTIVE: OnceLock<Arc<ActiveRequests>> = OnceLock::new();

    struct DropNotice;

    impl Drop for DropNotice {
        fn drop(&mut self) {
            DROPPED.store(true, Ordering::SeqCst);
        }
    }

    #[pyfunction]
    fn pending_request(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
        let guard = ACTIVE.get_or_init(Arc::default).begin();
        cancellable_request(py, async move {
            let _request = guard;
            let _guard = DropNotice;
            STARTED.store(true, Ordering::SeqCst);
            std::future::pending().await
        })
    }

    #[pyfunction]
    fn wait_idle(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
        let active = Arc::clone(ACTIVE.get_or_init(Arc::default));
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            active.wait_idle().await;
            Ok(())
        })
    }

    #[pyfunction]
    fn started() -> bool {
        STARTED.load(Ordering::SeqCst)
    }

    #[pyfunction]
    fn dropped() -> bool {
        DROPPED.load(Ordering::SeqCst)
    }

    #[test]
    fn preserves_provider_status_for_transient_retry_classification() {
        Python::initialize();
        for status in [
            "429 Too Many Requests",
            "503 Service Unavailable",
            "404 Not Found",
        ] {
            let error = source_error(YahooError::FetchFailed(status.to_string()));
            assert!(error.to_string().contains(status));
        }
    }

    #[test]
    fn cancelling_python_future_drops_native_request() {
        Python::initialize();
        Python::attach(|py| {
            let module = PyModule::new(py, "request_fixture").unwrap();
            module
                .add_function(wrap_pyfunction!(pending_request, &module).unwrap())
                .unwrap();
            module
                .add_function(wrap_pyfunction!(started, &module).unwrap())
                .unwrap();
            module
                .add_function(wrap_pyfunction!(dropped, &module).unwrap())
                .unwrap();
            module
                .add_function(wrap_pyfunction!(wait_idle, &module).unwrap())
                .unwrap();
            let globals = PyDict::new(py);
            globals.set_item("fixture", module).unwrap();
            py.run(c_str!("import asyncio\nasync def check():\n    request = fixture.pending_request()\n    async with asyncio.timeout(2):\n        while not fixture.started():\n            await asyncio.sleep(0.001)\n        request.cancel()\n        try:\n            await request\n        except asyncio.CancelledError:\n            pass\n        await fixture.wait_idle()\n        assert fixture.dropped()\nasyncio.run(check())"), Some(&globals), None).unwrap();
        });
        assert!(DROPPED.load(Ordering::SeqCst));
    }
}
