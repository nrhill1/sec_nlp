// src/client/rate_limit.rs - Rate limiting for SEC API compliance
use governor::{clock::DefaultClock, state::InMemoryState, state::NotKeyed, Quota, RateLimiter};
use std::num::NonZeroU32;

/// SEC allows 10 requests per second
const SEC_RATE_LIMIT: u32 = 10;

pub struct SecRateLimiter {
    limiter: RateLimiter<NotKeyed, InMemoryState, DefaultClock>,
}

impl SecRateLimiter {
    pub fn new() -> Self {
        let quota = Quota::per_second(NonZeroU32::new(SEC_RATE_LIMIT).unwrap());
        Self {
            limiter: RateLimiter::direct(quota),
        }
    }

    pub fn with_custom_rate(requests_per_second: u32) -> Self {
        let quota = Quota::per_second(NonZeroU32::new(requests_per_second).unwrap());
        Self {
            limiter: RateLimiter::direct(quota),
        }
    }

    pub async fn wait(&self) {
        self.limiter.until_ready().await;
    }

    pub fn check(&self) -> bool {
        self.limiter.check().is_ok()
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

    #[tokio::test]
    async fn test_rate_limiter() {
        let limiter = SecRateLimiter::new();

        // Should allow first request immediately
        assert!(limiter.check());

        limiter.wait().await;
        // After waiting, should be allowed again
        assert!(limiter.check());
    }
}
