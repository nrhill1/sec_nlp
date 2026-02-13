use pyo3::prelude::*;

use crate::error::{CorrError, CorrResult};
use crate::util::{covariance, rank, variance};

fn pearson_impl(x: &[f64], y: &[f64]) -> CorrResult<f64> {
    let cov = covariance(x, y)?;
    let var_x = variance(x, true, "x")?;
    let var_y = variance(y, true, "y")?;
    if var_x == 0.0 {
        return Err(CorrError::ZeroVariance("x"));
    }
    if var_y == 0.0 {
        return Err(CorrError::ZeroVariance("y"));
    }
    Ok(cov / (var_x.sqrt() * var_y.sqrt()))
}

fn spearman_impl(x: &[f64], y: &[f64]) -> CorrResult<f64> {
    let ranked_x = rank(x)?;
    let ranked_y = rank(y)?;
    pearson_impl(&ranked_x, &ranked_y)
}

#[pyfunction]
pub fn pearson(x: Vec<f64>, y: Vec<f64>) -> PyResult<f64> {
    pearson_impl(&x, &y).map_err(|err| err.to_py_err())
}

#[pyfunction]
pub fn spearman(x: Vec<f64>, y: Vec<f64>) -> PyResult<f64> {
    spearman_impl(&x, &y).map_err(|err| err.to_py_err())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pearson_perfect() {
        let x = vec![1.0, 2.0, 3.0, 4.0];
        let y = vec![2.0, 4.0, 6.0, 8.0];
        let corr = pearson_impl(&x, &y).unwrap();
        assert!((corr - 1.0).abs() < 1e-12);
    }

    #[test]
    fn spearman_inverse() {
        let x = vec![1.0, 2.0, 3.0, 4.0];
        let y = vec![4.0, 3.0, 2.0, 1.0];
        let corr = spearman_impl(&x, &y).unwrap();
        assert!((corr + 1.0).abs() < 1e-12);
    }
}
