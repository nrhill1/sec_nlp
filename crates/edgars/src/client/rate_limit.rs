//! Optimized rate limiting for SEC EDGAR requests.
//!
//! The SEC allows at most **10 requests per second** per client.  
//! This module wraps the [`governor`](https://docs.rs/governor) crate to provide
//! async rate limiting with an optional "unlimited" mode for testing.
//!
//! # Examples
//! ```rust,no_run
//! use sec_nlp::client::rate_limit::SecRateLimiter;
//!
//! #[tokio::main]
//! async fn main() {
//!     let limiter = SecRateLimiter::new(); // Default 10 req/s
//!     limiter.wait().await; // Wait until allowed
//!     assert!(limiter.check()); // Check if a request can be made immediately
//! }
//! ```

use governor::{clock::DefaultClock, state::InMemoryState, state::NotKeyed, Quota, RateLimiter};
use std::num::NonZeroU32;

/// Default SEC request rate limit (10 requests per second).
const SEC_RATE_LIMIT: u32 = 10;

/// A lightweight asynchronous rate limiter for SEC EDGAR requests.
///
/// Wraps [`governor::RateLimiter`] with convenience constructors for
/// the SEC default rate and an unlimited (disabled) mode.
///
/// When created with [`SecRateLimiter::unlimited`], all calls are no-ops.
///
/// # Example
/// ```rust,no_run
/// # use sec_nlp::client::rate_limit::SecRateLimiter;
/// # #[tokio::main]
/// # async fn main() {
/// let limiter = SecRateLimiter::with_rate(5); // 5 req/s
/// limiter.wait().await; // Throttles to 5 requests per second
/// # }
/// ```
#[derive(Debug)]
pub struct SecRateLimiter {
    /// Optional internal [`RateLimiter`]. `None` = unlimited mode.
    limiter: Option<RateLimiter<NotKeyed, InMemoryState, DefaultClock>>,
}

impl SecRateLimiter {
    /// Creates a rate limiter with the **SEC default rate** of 10 requests per second.
    ///
    /// Equivalent to `SecRateLimiter::with_rate(10)`.
    #[must_use]
    pub fn new() -> Self {
        Self::with_rate(SEC_RATE_LIMIT)
    }

    /// Creates a rate limiter with a **custom request rate** (per second).
    ///
    /// # Arguments
    /// * `requests_per_second` - Maximum number of requests allowed per second.
    ///
    /// # Panics
    /// Panics if `requests_per_second` is zero (since it cannot be `NonZeroU32`).
    #[must_use]
    pub fn with_rate(requests_per_second: u32) -> Self {
        let quota = Quota::per_second(NonZeroU32::new(requests_per_second).unwrap());
        Self {
            limiter: Some(RateLimiter::direct(quota)),
        }
    }

    /// Creates an **unlimited** rate limiter that does not throttle requests.
    ///
    /// Useful for testing or for offline/local modes.
    #[must_use]
    pub fn unlimited() -> Self {
        Self { limiter: None }
    }

    /// Waits asynchronously until a request is permitted under the rate limit.
    ///
    /// Does nothing if the limiter is unlimited.
    ///
    /// # Example
    /// ```rust,no_run
    /// # use sec_nlp::client::rate_limit::SecRateLimiter;
    /// # #[tokio::main] async fn main() {
    /// let limiter = SecRateLimiter::new();
    /// limiter.wait().await; // Wait until allowed
    /// # }
    /// ```
    pub async fn wait(&self) {
        if let Some(limiter) = &self.limiter {
            limiter.until_ready().await;
        }
    }

    /// Checks synchronously whether a request can be made **immediately**.
    ///
    /// Returns `true` if no throttling is in effect or if the limiter
    /// currently allows a request.
    #[must_use]
    pub fn check(&self) -> bool {
        self.limiter.as_ref().is_none_or(|l| l.check().is_ok())
    }
}

impl Default for SecRateLimiter {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;

    #[tokio::test]
    async fn test_rate_limiter_allows_first_request() {
        let limiter = SecRateLimiter::new();
        assert!(limiter.check());
    }

    #[tokio::test]
    async fn test_rate_limiter_wait() {
        let limiter = SecRateLimiter::with_rate(100); // High rate for testing

        // Should not block significantly
        let start = Instant::now();
        limiter.wait().await;
        let elapsed = start.elapsed();

        assert!(elapsed.as_millis() < 100);
    }

    #[tokio::test]
    async fn test_unlimited_rate_limiter() {
        let limiter = SecRateLimiter::unlimited();

        // Should always allow requests
        for _ in 0..100 {
            assert!(limiter.check());
            limiter.wait().await;
        }
    }

    #[tokio::test]
    async fn test_rate_limiter_enforcement() {
        let limiter = SecRateLimiter::with_rate(2); // 2 req/s

        // First two should be fast
        limiter.wait().await;
        limiter.wait().await;

        // Third should be delayed
        let start = Instant::now();
        limiter.wait().await;
        let elapsed = start.elapsed();

        // Should wait approximately 500ms (1s / 2 req)
        assert!(
            elapsed.as_millis() >= 400,
            "Expected throttling delay, got {:?}",
            elapsed
        );
    }
}
