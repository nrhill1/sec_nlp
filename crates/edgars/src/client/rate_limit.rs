// src/client/rate_limit.rs - Optimized rate limiting
use governor::{clock::DefaultClock, state::InMemoryState, state::NotKeyed, Quota, RateLimiter};
use std::num::NonZeroU32;

/// SEC allows 10 requests per second
const SEC_RATE_LIMIT: u32 = 10;

pub struct SecRateLimiter {
    limiter: Option<RateLimiter<NotKeyed, InMemoryState, DefaultClock>>,
}

impl SecRateLimiter {
    /// Create rate limiter with SEC's default rate (10 req/s)
    pub fn new() -> Self {
        Self::with_rate(SEC_RATE_LIMIT)
    }

    /// Create rate limiter with custom rate
    pub fn with_rate(requests_per_second: u32) -> Self {
        let quota = Quota::per_second(NonZeroU32::new(requests_per_second).unwrap());
        Self {
            limiter: Some(RateLimiter::direct(quota)),
        }
    }

    /// Create unlimited rate limiter (no throttling)
    pub fn unlimited() -> Self {
        Self { limiter: None }
    }

    /// Wait until a request can be made
    pub async fn wait(&self) {
        if let Some(limiter) = &self.limiter {
            limiter.until_ready().await;
        }
    }

    /// Check if a request can be made immediately
    pub fn check(&self) -> bool {
        self.limiter.as_ref().map(|l| l.check().is_ok()).unwrap_or(true)
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
        assert!(elapsed.as_millis() >= 400);
    }
}
