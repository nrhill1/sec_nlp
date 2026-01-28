use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::IntoPyObjectExt;
use serde_json::Value;

use crate::client::EftsClient;
use crate::constants::{
    DEFAULT_MAX_RETRIES, DEFAULT_RATE_LIMIT_SECS, DEFAULT_RETRY_DELAY_SECS,
};

#[pyfunction]
#[pyo3(signature = (email, company_name="SEC NLP Tool".to_string(), timeout=30.0))]
pub fn create_efts_client(
    email: String,
    company_name: String,
    timeout: f64,
) -> PyResult<EftsClient> {
    let user_agent = format!("{} ({})", company_name, email);
    EftsClient::new(
        Some(user_agent),
        timeout,
        DEFAULT_MAX_RETRIES,
        DEFAULT_RETRY_DELAY_SECS,
        DEFAULT_RATE_LIMIT_SECS,
        None,
        None,
    )
}

pub(crate) fn json_to_py(py: Python<'_>, value: &Value) -> PyResult<PyObject> {
    match value {
        Value::Null => Ok(py.None()),
        Value::Bool(item) => Ok(item.into_py_any(py)?),
        Value::Number(item) => {
            if let Some(value) = item.as_i64() {
                Ok(value.into_py_any(py)?)
            } else if let Some(value) = item.as_u64() {
                Ok(value.into_py_any(py)?)
            } else if let Some(value) = item.as_f64() {
                Ok(value.into_py_any(py)?)
            } else {
                Ok(py.None())
            }
        }
        Value::String(item) => Ok(item.into_py_any(py)?),
        Value::Array(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(json_to_py(py, item)?)?;
            }
            list.into_py_any(py)
        }
        Value::Object(items) => {
            let dict = PyDict::new(py);
            for (key, item) in items {
                dict.set_item(key, json_to_py(py, item)?)?;
            }
            dict.into_py_any(py)
        }
    }
}
