// crates/market/src/runtime.rs
//! Shared tokio runtime for async operations.

use pyo3::prelude::*;
use std::future::Future;
use std::sync::OnceLock;
use tokio::runtime::Runtime;

use crate::types::to_py_err;

/// Global shared runtime.
static RUNTIME: OnceLock<Runtime> = OnceLock::new();

/// Get or initialize the shared tokio runtime.
fn get_runtime() -> &'static Runtime {
    RUNTIME.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()
            .expect("Failed to create tokio runtime")
    })
}

/// Run an async future on the shared runtime.
pub fn run_async<T, F>(future: F) -> PyResult<T>
where
    F: Future<Output = PyResult<T>>,
{
    get_runtime().block_on(future)
}

/// Run an async future that returns a Result, converting errors.
pub fn run_async_result<T, E, F>(future: F) -> PyResult<T>
where
    E: std::fmt::Display,
    F: Future<Output = Result<T, E>>,
{
    get_runtime()
        .block_on(future)
        .map_err(to_py_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runtime_initializes_once() {
        let rt1 = get_runtime();
        let rt2 = get_runtime();
        assert!(std::ptr::eq(rt1, rt2));
    }

    #[test]
    fn run_async_executes() {
        let result: PyResult<i32> = run_async(async { Ok(42) });
        assert_eq!(result.unwrap(), 42);
    }
}
