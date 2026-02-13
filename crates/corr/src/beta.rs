use pyo3::prelude::*;

use crate::error::{CorrError, CorrResult};
use crate::util::{covariance, variance};

fn beta_impl(asset_returns: &[f64], benchmark_returns: &[f64]) -> CorrResult<f64> {
    if asset_returns.len() != benchmark_returns.len() {
        return Err(CorrError::LengthMismatch {
            left: asset_returns.len(),
            right: benchmark_returns.len(),
        });
    }
    if asset_returns.len() < 2 {
        return Err(CorrError::InsufficientData {
            needed: 2,
            got: asset_returns.len(),
        });
    }
    let cov = covariance(asset_returns, benchmark_returns)?;
    let var_bench = variance(benchmark_returns, true, "benchmark")?;
    if var_bench == 0.0 {
        return Err(CorrError::ZeroVariance("benchmark"));
    }
    Ok(cov / var_bench)
}

#[pyfunction]
pub fn beta(asset_returns: Vec<f64>, benchmark_returns: Vec<f64>) -> PyResult<f64> {
    beta_impl(&asset_returns, &benchmark_returns).map_err(|err| err.to_py_err())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn beta_linear() {
        let asset = vec![0.01, 0.02, 0.03, 0.04];
        let bench = vec![0.01, 0.02, 0.03, 0.04];
        let value = beta_impl(&asset, &bench).unwrap();
        assert!((value - 1.0).abs() < 1e-12);
    }
}
