//! Rate limiting for SEC API compliance.
//!
//! The SEC enforces a rate limit of 10 requests per second for automated
//! requests. This module provides a token bucket rate limiter to ensure
//! compliance.

use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;
use tokio::time::sleep;

/// Token bucket rate limiter.
///
/// Implements a token bucket algorithm to limit the rate of requests.
/// Tokens are added to the bucket at a fixed rate, and each request
/// consumes one token.
pub struct RateLimiter {
    state: Arc<Mutex<RateLimiterState>>,
    tokens_per_interval: u32,
    interval: Duration,
}

struct RateLimiterState {
    tokens: f64,
    last_update: Instant,
}

impl RateLimiter {
    /// Create a new rate limiter.
    ///
    /// # Arguments
    ///
    /// * `tokens_per_interval` - Number of tokens to add per interval
    /// * `interval` - Duration of each interval
    ///
    /// # Examples
    ///
    /// ```
    /// use sec_o3::client::rate_limit::RateLimiter;
    /// use std::time::Duration;
    ///
    /// // SEC limit: 10 requests per second
    /// let limiter = RateLimiter::new(10, Duration::from_secs(1));
    /// ```
    pub fn new(tokens_per_interval: u32, interval: Duration) -> Self {
        Self {
            state: Arc::new(Mutex::new(RateLimiterState {
                tokens: tokens_per_interval as f64,
                last_update: Instant::now(),
            })),
            tokens_per_interval,
            interval,
        }
    }

    /// Wait until a token is available, then consume it.
    ///
    /// This method blocks until a token becomes available, ensuring that
    /// the rate limit is not exceeded.
    ///
    /// # Examples
    ///
    /// ```no_run
    /// # use sec_o3::client::rate_limit::RateLimiter;
    /// # use std::time::Duration;
    /// # async fn example() {
    /// let limiter = RateLimiter::new(10, Duration::from_secs(1));
    ///
    /// // This will wait if no tokens are available
    /// limiter.wait().await;
    /// // Now safe to make a request
    /// # }
    /// ```
    pub async fn wait(&self) {
        loop {
            let mut state = self.state.lock().await;

            // Add tokens based on time elapsed
            let now = Instant::now();
            let elapsed = now.duration_since(state.last_update);
            let tokens_to_add = elapsed.as_secs_f64() / self.interval.as_secs_f64() * self.tokens_per_interval as f64;

            state.tokens = (state.tokens + tokens_to_add).min(self.tokens_per_interval as f64);
            state.last_update = now;

            // Try to consume a token
            if state.tokens >= 1.0 {
                state.tokens -= 1.0;
                return;
            }

            // Calculate wait time for next token
            let tokens_needed = 1.0 - state.tokens;
            let wait_duration =
                Duration::from_secs_f64(tokens_needed / self.tokens_per_interval as f64 * self.interval.as_secs_f64());

            drop(state); // Release lock before sleeping
            sleep(wait_duration).await;
        }
    }

    /// Try to acquire a token without waiting.
    ///
    /// # Returns
    ///
    /// * `true` - If a token was acquired
    /// * `false` - If no tokens are available
    pub async fn try_acquire(&self) -> bool {
        let mut state = self.state.lock().await;

        // Add tokens based on time elapsed
        let now = Instant::now();
        let elapsed = now.duration_since(state.last_update);
        let tokens_to_add = elapsed.as_secs_f64() / self.interval.as_secs_f64() * self.tokens_per_interval as f64;

        state.tokens = (state.tokens + tokens_to_add).min(self.tokens_per_interval as f64);
        state.last_update = now;

        if state.tokens >= 1.0 {
            state.tokens -= 1.0;
            true
        } else {
            false
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_rate_limiter_basic() {
        let limiter = RateLimiter::new(2, Duration::from_secs(1));

        // Should acquire immediately
        let start = Instant::now();
        limiter.wait().await;
        limiter.wait().await;

        // Third request should wait
        limiter.wait().await;
        let elapsed = start.elapsed();

        assert!(elapsed >= Duration::from_millis(400)); // Some wait occurred
    }

    #[tokio::test]
    async fn test_try_acquire() {
        let limiter = RateLimiter::new(1, Duration::from_secs(1));

        assert!(limiter.try_acquire().await); // First succeeds
        assert!(!limiter.try_acquire().await); // Second fails immediately
    }
}
