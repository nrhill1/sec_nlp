// src/client/retry.rs - Retry logic with exponential backoff
use std::time::Duration;
use tokio::time::sleep;

#[derive(Debug, Clone)]
pub struct RetryPolicy {
    pub max_attempts: u32,
    pub initial_delay: Duration,
    pub max_delay: Duration,
    pub multiplier: f64,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self {
            max_attempts: 3,
            initial_delay: Duration::from_millis(100),
            max_delay: Duration::from_secs(30),
            multiplier: 2.0,
        }
    }
}

impl RetryPolicy {
    pub fn new(max_attempts: u32) -> Self {
        Self {
            max_attempts,
            ..Default::default()
        }
    }

    pub async fn execute<F, T, E>(&self, mut operation: F) -> Result<T, E>
    where
        F: FnMut() -> futures::future::BoxFuture<'static, Result<T, E>>,
        E: std::fmt::Display,
    {
        let mut attempt = 0;
        let mut delay = self.initial_delay;

        loop {
            attempt += 1;

            match operation().await {
                Ok(result) => return Ok(result),
                Err(e) if attempt >= self.max_attempts => return Err(e),
                Err(e) => {
                    tracing::warn!(
                        "Attempt {}/{} failed: {}. Retrying in {:?}",
                        attempt,
                        self.max_attempts,
                        e,
                        delay
                    );

                    sleep(delay).await;
                    delay = std::cmp::min(
                        Duration::from_secs_f64(delay.as_secs_f64() * self.multiplier),
                        self.max_delay,
                    );
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_retry_success_first_attempt() {
        let policy = RetryPolicy::new(3);
        let mut call_count = 0;

        let result = policy
            .execute(|| {
                call_count += 1;
                Box::pin(async move { Ok::<_, String>(42) })
            })
            .await;

        assert_eq!(result, Ok(42));
        assert_eq!(call_count, 1);
    }

    #[tokio::test]
    async fn test_retry_eventual_success() {
        let policy = RetryPolicy::new(3);
        let mut call_count = 0;

        let result = policy
            .execute(|| {
                call_count += 1;
                Box::pin(async move {
                    if call_count < 3 {
                        Err("temporary error".to_string())
                    } else {
                        Ok(42)
                    }
                })
            })
            .await;

        assert_eq!(result, Ok(42));
        assert_eq!(call_count, 3);
    }
}
