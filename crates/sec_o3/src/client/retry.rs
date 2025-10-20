/// Retry logic with exponential backoff.
///
/// This module provides a simple asynchronous retry policy that can be used to
/// automatically retry fallible async operations with exponential backoff.
///
/// Built for use in SEC EDGAR clients or other network-bound code where
/// transient errors (like rate limits or timeouts) are expected.
///
/// # Example
/// ```rust,no_run
/// use sec_nlp::client::retry::RetryPolicy;
/// use futures::FutureExt;
///
/// #[tokio::main]
/// async fn main() {
///     let policy = RetryPolicy::new(3);
///
///     // Simulated network call with retries
///     let result = policy
///         .execute(|| async {
///             // Replace with your actual operation (e.g., reqwest call)
///             if rand::random::<f32>() > 0.7 {
///                 Ok::<_, String>("success")
///             } else {
///                 Err::<&str, String>("temporary failure".to_string())
///             }
///         }
///         .boxed())
///         .await;
///
///     println!("Result: {:?}", result);
/// }
/// ```
use std::time::Duration;
use tokio::time::sleep;

/// Configuration for retrying operations with exponential backoff.
///
/// `RetryPolicy` defines the maximum number of attempts, the initial delay,
/// the maximum delay, and the backoff multiplier applied after each failure.
///
/// # Example
/// ```rust,no_run
/// use sec_nlp::client::retry::RetryPolicy;
///
/// let policy = RetryPolicy {
///     max_attempts: 5,
///     initial_delay: std::time::Duration::from_millis(200),
///     max_delay: std::time::Duration::from_secs(10),
///     multiplier: 1.5,
/// };
/// ```
#[derive(Debug, Clone)]
pub struct RetryPolicy {
    /// Maximum number of attempts before giving up.
    pub max_attempts: u32,
    /// Initial delay before the first retry attempt.
    pub initial_delay: Duration,
    /// Maximum delay between attempts.
    pub max_delay: Duration,
    /// Multiplier applied to the delay after each failed attempt.
    pub multiplier: f64,
}

#[allow(dead_code)]
impl RetryPolicy {
    /// Creates a retry policy with a custom maximum number of attempts and other defaults.
    ///
    /// # Arguments
    /// * `max_attempts` - Number of attempts before giving up.
    #[must_use]
    pub fn new(max_attempts: u32) -> Self {
        Self {
            max_attempts,
            ..Default::default()
        }
    }

    /// Executes an asynchronous operation with retry and exponential backoff.
    ///
    /// # Type Parameters
    /// * `F` — A closure returning a boxed future that resolves to `Result<T, E>`.
    /// * `T` — The success type.
    /// * `E` — The error type, which must implement [`Display`](std::fmt::Display).
    ///
    /// # Arguments
    /// * `operation` — The operation to execute. It must be a closure that returns
    ///   a boxed future each time it’s called.
    ///
    /// # Returns
    /// * `Ok(T)` on success.
    /// * `Err(E)` if all retry attempts fail.
    ///
    /// # Example
    /// ```rust,no_run
    /// use sec_nlp::client::retry::RetryPolicy;
    ///
    /// #[tokio::main]
    /// async fn main() {
    ///     let policy = RetryPolicy::new(3);
    ///     let mut count = 0;
    ///
    ///     let result = policy
    ///         .execute(|| {
    ///             count += 1;
    ///             Box::pin(async move {
    ///                 if count < 3 {
    ///                     Err::<i32, String>("temporary failure".into())
    ///                 } else {
    ///                     Ok::<i32, String>(42)
    ///                 }
    ///             })
    ///         })
    ///         .await;
    ///
    ///     assert_eq!(result, Ok(42));
    /// }
    /// ```
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

impl Default for RetryPolicy {
    /// Returns the default retry policy:
    /// - `max_attempts = 3`
    /// - `initial_delay = 100 ms`
    /// - `max_delay = 30 s`
    /// - `multiplier = 2.0`
    fn default() -> Self {
        Self {
            max_attempts: 3,
            initial_delay: Duration::from_millis(100),
            max_delay: Duration::from_secs(30),
            multiplier: 2.0,
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
