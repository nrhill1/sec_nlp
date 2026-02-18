use pyo3::prelude::*;
use statrs::distribution::{ContinuousCDF, StudentsT};

use crate::error::{CorrError, CorrResult};
use crate::returns::{cumulative_return_impl, simple_returns_impl};
use crate::util::{ensure_finite, mean, variance};

const SECONDS_PER_DAY: i64 = 86_400;

#[pyclass(name = "EventStudyResult", frozen, module = "corr")]
#[derive(Debug, Clone)]
pub struct EventStudyResult {
    #[pyo3(get)]
    pub car_pre: Option<f64>,
    #[pyo3(get)]
    pub car_post: Option<f64>,
    #[pyo3(get)]
    pub t_stat: Option<f64>,
    #[pyo3(get)]
    pub p_value: Option<f64>,
}

fn window_prices(
    data: &[(i64, f64)],
    start: i64,
    end: i64,
) -> Vec<f64> {
    data.iter()
        .filter(|(ts, _)| *ts >= start && *ts <= end)
        .map(|(_, price)| *price)
        .collect()
}

fn t_test(pre: &[f64], post: &[f64]) -> CorrResult<(f64, f64)> {
    if pre.len() < 2 || post.len() < 2 {
        return Err(CorrError::InsufficientData {
            needed: 2,
            got: pre.len().min(post.len()),
        });
    }
    let mean_pre = mean(pre, "pre_returns")?;
    let mean_post = mean(post, "post_returns")?;
    let var_pre = variance(pre, true, "pre_returns")?;
    let var_post = variance(post, true, "post_returns")?;

    let n1 = pre.len() as f64;
    let n2 = post.len() as f64;
    let denom = (var_pre / n1 + var_post / n2).sqrt();
    if denom == 0.0 {
        return Err(CorrError::ZeroVariance("returns"));
    }
    let t_stat = (mean_post - mean_pre) / denom;

    let numerator = (var_pre / n1 + var_post / n2).powi(2);
    let denom_df = (var_pre / n1).powi(2) / (n1 - 1.0)
        + (var_post / n2).powi(2) / (n2 - 1.0);
    let df = if denom_df == 0.0 { 1.0 } else { numerator / denom_df };

    let dist = StudentsT::new(0.0, 1.0, df)
        .map_err(|_| CorrError::InvalidParameter("invalid t distribution"))?;
    let p_value = 2.0 * (1.0 - dist.cdf(t_stat.abs()));
    Ok((t_stat, p_value))
}

#[pyfunction]
pub fn event_study(
    prices: Vec<f64>,
    timestamps: Vec<i64>,
    event_timestamp: i64,
    pre_window: i64,
    post_window: i64,
) -> PyResult<EventStudyResult> {
    if prices.len() != timestamps.len() {
        return Err(CorrError::LengthMismatch {
            left: prices.len(),
            right: timestamps.len(),
        }
        .to_py_err());
    }
    if prices.len() < 2 {
        return Err(CorrError::InsufficientData {
            needed: 2,
            got: prices.len(),
        }
        .to_py_err());
    }
    if pre_window < 0 || post_window < 0 {
        return Err(CorrError::InvalidParameter("windows must be >= 0").to_py_err());
    }
    ensure_finite(&prices, "prices").map_err(|err| err.to_py_err())?;

    let mut data: Vec<(i64, f64)> = timestamps
        .into_iter()
        .zip(prices.into_iter())
        .collect();
    data.sort_by_key(|(ts, _)| *ts);

    let pre_start = event_timestamp - pre_window * SECONDS_PER_DAY;
    let pre_end = event_timestamp - 1;
    let post_start = event_timestamp;
    let post_end = event_timestamp + post_window * SECONDS_PER_DAY;

    let pre_prices = if pre_window == 0 {
        Vec::new()
    } else {
        window_prices(&data, pre_start, pre_end)
    };
    let post_prices = window_prices(&data, post_start, post_end);

    let car_pre = cumulative_return_impl(&pre_prices).map_err(|err| err.to_py_err())?;
    let car_post = cumulative_return_impl(&post_prices).map_err(|err| err.to_py_err())?;

    let pre_returns = simple_returns_impl(&pre_prices).map_err(|err| err.to_py_err())?;
    let post_returns = simple_returns_impl(&post_prices).map_err(|err| err.to_py_err())?;

    let (t_stat, p_value) = match t_test(&pre_returns, &post_returns) {
        Ok((t, p)) => (Some(t), Some(p)),
        Err(_) => (None, None),
    };

    Ok(EventStudyResult {
        car_pre,
        car_post,
        t_stat,
        p_value,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn event_study_basic() {
        let prices = vec![100.0, 101.0, 102.0, 103.0, 104.0];
        let timestamps = vec![0, 86400, 2 * 86400, 3 * 86400, 4 * 86400];
        let result = event_study(prices, timestamps, 2 * 86400, 2, 2).unwrap();
        assert!(result.car_post.unwrap() > 0.0);
    }
}
