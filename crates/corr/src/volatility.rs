use pyo3::prelude::*;

use crate::error::{CorrError, CorrResult};
use crate::util::{ensure_finite, variance};

fn std_dev_impl(values: &[f64]) -> CorrResult<f64> {
    let var = variance(values, false, "values")?;
    Ok(var.sqrt())
}

fn volume_spike_impl(values: &[f64]) -> CorrResult<Option<f64>> {
    if values.is_empty() {
        return Ok(None);
    }
    ensure_finite(values, "values")?;
    let avg = values.iter().sum::<f64>() / values.len() as f64;
    if avg == 0.0 {
        return Ok(None);
    }
    let peak = values
        .iter()
        .fold(f64::NEG_INFINITY, |acc, value| acc.max(*value));
    Ok(Some(peak / avg))
}

fn average_true_range_impl(
    high: &[f64],
    low: &[f64],
    close: &[f64],
) -> CorrResult<f64> {
    if high.len() != low.len() || high.len() != close.len() {
        return Err(CorrError::LengthMismatch {
            left: high.len(),
            right: low.len().max(close.len()),
        });
    }
    if high.is_empty() {
        return Err(CorrError::EmptyInput("high"));
    }
    ensure_finite(high, "high")?;
    ensure_finite(low, "low")?;
    ensure_finite(close, "close")?;

    let mut total = 0.0;
    for i in 0..high.len() {
        let range = high[i] - low[i];
        let tr = if i == 0 {
            range
        } else {
            let prev_close = close[i - 1];
            let high_close = (high[i] - prev_close).abs();
            let low_close = (low[i] - prev_close).abs();
            range.max(high_close).max(low_close)
        };
        total += tr;
    }
    Ok(total / high.len() as f64)
}

fn garman_klass_impl(
    high: &[f64],
    low: &[f64],
    open: &[f64],
    close: &[f64],
) -> CorrResult<f64> {
    if high.len() != low.len() || high.len() != open.len() || high.len() != close.len() {
        return Err(CorrError::LengthMismatch {
            left: high.len(),
            right: low.len().max(open.len()).max(close.len()),
        });
    }
    if high.is_empty() {
        return Err(CorrError::EmptyInput("high"));
    }
    ensure_finite(high, "high")?;
    ensure_finite(low, "low")?;
    ensure_finite(open, "open")?;
    ensure_finite(close, "close")?;

    let coeff = 2.0 * (2.0_f64.ln()) - 1.0;
    let mut sum = 0.0;
    for i in 0..high.len() {
        if low[i] <= 0.0 || high[i] <= 0.0 || open[i] <= 0.0 || close[i] <= 0.0 {
            return Err(CorrError::InvalidParameter(
                "prices must be positive for log calculations",
            ));
        }
        let log_hl = (high[i] / low[i]).ln();
        let log_co = (close[i] / open[i]).ln();
        let term = 0.5 * log_hl * log_hl - coeff * log_co * log_co;
        sum += term;
    }
    let variance = sum / high.len() as f64;
    Ok(variance.max(0.0).sqrt())
}

#[pyfunction]
pub fn std_dev(values: Vec<f64>) -> PyResult<f64> {
    std_dev_impl(&values).map_err(|err| err.to_py_err())
}

#[pyfunction]
pub fn volume_spike(values: Vec<f64>) -> PyResult<Option<f64>> {
    volume_spike_impl(&values).map_err(|err| err.to_py_err())
}

#[pyfunction]
pub fn average_true_range(
    high: Vec<f64>,
    low: Vec<f64>,
    close: Vec<f64>,
) -> PyResult<f64> {
    average_true_range_impl(&high, &low, &close).map_err(|err| err.to_py_err())
}

#[pyfunction]
pub fn garman_klass(
    high: Vec<f64>,
    low: Vec<f64>,
    open: Vec<f64>,
    close: Vec<f64>,
) -> PyResult<f64> {
    garman_klass_impl(&high, &low, &open, &close)
        .map_err(|err| err.to_py_err())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn std_dev_zero() {
        let values = vec![5.0, 5.0, 5.0];
        let value = std_dev_impl(&values).unwrap();
        assert!(value.abs() < 1e-12);
    }

    #[test]
    fn atr_basic() {
        let high = vec![10.0, 12.0];
        let low = vec![8.0, 9.0];
        let close = vec![9.0, 11.0];
        let atr = average_true_range_impl(&high, &low, &close).unwrap();
        assert!(atr > 0.0);
    }

    #[test]
    fn volume_spike_basic() {
        let values = vec![100.0, 110.0, 90.0, 150.0];
        let spike = volume_spike_impl(&values).unwrap().unwrap();
        assert!((spike - (150.0 / 112.5)).abs() < 1e-12);
    }
}
