mod beta;
mod correlation;
mod error;
mod event_study;
mod returns;
mod util;
mod volatility;

use pyo3::prelude::*;

#[pymodule]
fn corr(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(correlation::pearson, m)?)?;
    m.add_function(wrap_pyfunction!(correlation::spearman, m)?)?;
    m.add_function(wrap_pyfunction!(returns::simple_returns, m)?)?;
    m.add_function(wrap_pyfunction!(returns::cumulative_return, m)?)?;
    m.add_function(wrap_pyfunction!(returns::car, m)?)?;
    m.add_function(wrap_pyfunction!(returns::rolling_returns, m)?)?;
    m.add_function(wrap_pyfunction!(volatility::std_dev, m)?)?;
    m.add_function(wrap_pyfunction!(volatility::volume_spike, m)?)?;
    m.add_function(wrap_pyfunction!(volatility::average_true_range, m)?)?;
    m.add_function(wrap_pyfunction!(volatility::garman_klass, m)?)?;
    m.add_function(wrap_pyfunction!(beta::beta, m)?)?;
    m.add_function(wrap_pyfunction!(event_study::event_study, m)?)?;

    m.add_class::<event_study::EventStudyResult>()?;

    Ok(())
}
