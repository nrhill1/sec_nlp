use crate::error::{CorrError, CorrResult};

pub fn ensure_finite(values: &[f64], label: &'static str) -> CorrResult<()> {
    if values.iter().any(|v| !v.is_finite()) {
        return Err(CorrError::NonFiniteValue(label));
    }
    Ok(())
}

pub fn mean(values: &[f64], label: &'static str) -> CorrResult<f64> {
    if values.is_empty() {
        return Err(CorrError::EmptyInput(label));
    }
    ensure_finite(values, label)?;
    Ok(values.iter().sum::<f64>() / values.len() as f64)
}

pub fn variance(values: &[f64], sample: bool, label: &'static str) -> CorrResult<f64> {
    if values.is_empty() {
        return Err(CorrError::EmptyInput(label));
    }
    ensure_finite(values, label)?;
    if values.len() == 1 {
        return Ok(0.0);
    }
    let avg = mean(values, label)?;
    let mut sum_sq = 0.0;
    for value in values {
        let diff = value - avg;
        sum_sq += diff * diff;
    }
    let denom = if sample {
        (values.len() - 1) as f64
    } else {
        values.len() as f64
    };
    Ok(sum_sq / denom)
}

pub fn covariance(x: &[f64], y: &[f64]) -> CorrResult<f64> {
    if x.len() != y.len() {
        return Err(CorrError::LengthMismatch {
            left: x.len(),
            right: y.len(),
        });
    }
    if x.len() < 2 {
        return Err(CorrError::InsufficientData {
            needed: 2,
            got: x.len(),
        });
    }
    ensure_finite(x, "x")?;
    ensure_finite(y, "y")?;
    let mean_x = mean(x, "x")?;
    let mean_y = mean(y, "y")?;
    let mut sum = 0.0;
    for (xi, yi) in x.iter().zip(y.iter()) {
        sum += (xi - mean_x) * (yi - mean_y);
    }
    Ok(sum / (x.len() - 1) as f64)
}

pub fn rank(values: &[f64]) -> CorrResult<Vec<f64>> {
    if values.is_empty() {
        return Err(CorrError::EmptyInput("values"));
    }
    ensure_finite(values, "values")?;

    let mut indexed: Vec<(usize, f64)> = values
        .iter()
        .enumerate()
        .map(|(idx, value)| (idx, *value))
        .collect();

    indexed.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap());

    let mut ranks = vec![0.0; values.len()];
    let mut i = 0;
    while i < indexed.len() {
        let mut j = i + 1;
        while j < indexed.len() && indexed[j].1 == indexed[i].1 {
            j += 1;
        }
        let rank_start = i as f64 + 1.0;
        let rank_end = j as f64;
        let avg_rank = (rank_start + rank_end) / 2.0;
        for k in i..j {
            ranks[indexed[k].0] = avg_rank;
        }
        i = j;
    }

    Ok(ranks)
}
