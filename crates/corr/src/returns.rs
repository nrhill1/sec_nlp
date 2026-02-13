use pyo3::prelude::*;

use crate::error::{CorrError, CorrResult};
use crate::util::ensure_finite;

pub(crate) fn simple_returns_impl(prices: &[f64]) -> CorrResult<Vec<f64>> {
    if prices.len() < 2 {
        return Ok(Vec::new());
    }
    ensure_finite(prices, "prices")?;
    let mut returns = Vec::with_capacity(prices.len() - 1);
    for (prev, curr) in prices.iter().zip(prices.iter().skip(1)) {
        if *prev == 0.0 {
            continue;
        }
        returns.push((curr / prev) - 1.0);
    }
    Ok(returns)
}

pub(crate) fn cumulative_return_impl(prices: &[f64]) -> CorrResult<Option<f64>> {
    if prices.len() < 2 {
        return Ok(None);
    }
    ensure_finite(prices, "prices")?;
    let first = prices[0];
    if first == 0.0 {
        return Ok(None);
    }
    let last = prices[prices.len() - 1];
    Ok(Some((last / first) - 1.0))
}

fn rolling_returns_impl(prices: &[f64], window: usize) -> CorrResult<Vec<f64>> {
    if window < 2 {
        return Err(CorrError::InvalidWindow("window must be >= 2"));
    }
    if prices.len() < window {
        return Ok(Vec::new());
    }
    ensure_finite(prices, "prices")?;
    let mut output = Vec::with_capacity(prices.len() - window + 1);
    for start in 0..=prices.len() - window {
        let first = prices[start];
        let last = prices[start + window - 1];
        if first == 0.0 {
            continue;
        }
        output.push((last / first) - 1.0);
    }
    Ok(output)
}

#[pyfunction]
pub fn simple_returns(prices: Vec<f64>) -> PyResult<Vec<f64>> {
    simple_returns_impl(&prices).map_err(|err| err.to_py_err())
}

#[pyfunction]
pub fn cumulative_return(prices: Vec<f64>) -> PyResult<Option<f64>> {
    cumulative_return_impl(&prices).map_err(|err| err.to_py_err())
}

#[pyfunction]
pub fn car(asset_prices: Vec<f64>, benchmark_prices: Vec<f64>) -> PyResult<Option<f64>> {
    let asset = cumulative_return_impl(&asset_prices).map_err(|err| err.to_py_err())?;
    let benchmark =
        cumulative_return_impl(&benchmark_prices).map_err(|err| err.to_py_err())?;
    match (asset, benchmark) {
        (Some(a), Some(b)) => Ok(Some(a - b)),
        _ => Ok(None),
    }
}

#[pyfunction]
pub fn rolling_returns(prices: Vec<f64>, window: usize) -> PyResult<Vec<f64>> {
    rolling_returns_impl(&prices, window).map_err(|err| err.to_py_err())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cumulative_return_basic() {
        let prices = vec![100.0, 110.0, 121.0];
        let value = cumulative_return_impl(&prices).unwrap().unwrap();
        assert!((value - 0.21).abs() < 1e-12);
    }

    #[test]
    fn simple_returns_basic() {
        let prices = vec![100.0, 110.0, 121.0];
        let returns = simple_returns_impl(&prices).unwrap();
        assert_eq!(returns.len(), 2);
        assert!((returns[0] - 0.1).abs() < 1e-12);
    }
}
