use std::time::Duration;

use tokio::time::sleep;

use crate::error::NewswatchError;

#[derive(Debug, Clone)]
pub struct HttpClient {
    client: reqwest::Client,
    user_agent: String,
    rate_limit_secs: f64,
    max_retries: u32,
    retry_delay_secs: f64,
}

impl HttpClient {
    pub fn new(
        user_agent: String,
        rate_limit_secs: f64,
        max_retries: u32,
        retry_delay_secs: f64,
    ) -> Result<Self, NewswatchError> {
        let client = reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(5))
            .timeout(Duration::from_secs(20))
            .build()?;
        Ok(Self {
            client,
            user_agent,
            rate_limit_secs,
            max_retries,
            retry_delay_secs,
        })
    }

    pub async fn fetch_text(&self, url: &str) -> Result<String, NewswatchError> {
        tokio::time::timeout(Duration::from_secs(20), self.fetch_with_retry(url))
            .await
            .map_err(|_| NewswatchError::new("news request exceeded 20 seconds"))?
    }

    async fn fetch_with_retry(&self, url: &str) -> Result<String, NewswatchError> {
        let mut attempt: u32 = 0;
        loop {
            if self.rate_limit_secs > 0.0 {
                sleep(Duration::from_secs_f64(self.rate_limit_secs)).await;
            }

            match self
                .client
                .get(url)
                .header(reqwest::header::USER_AGENT, self.user_agent.clone())
                .send()
                .await
            {
                Ok(response) => {
                    if response.status().is_success() {
                        match response.text().await {
                            Ok(body) => return Ok(body),
                            Err(err) => {
                                if attempt >= self.max_retries
                                    || !(err.is_timeout() || err.is_body())
                                {
                                    return Err(err.into());
                                }
                            }
                        }
                    } else {
                        let status = response.status();
                        let message = format!("news fetch failed (status {})", status);
                        if attempt >= self.max_retries
                            || !(status.as_u16() == 429 || status.is_server_error())
                        {
                            return Err(NewswatchError::new(message));
                        }
                    }
                }
                Err(err) => {
                    if attempt >= self.max_retries
                        || !(err.is_connect() || err.is_timeout() || err.is_body())
                    {
                        return Err(NewswatchError::new(err.to_string()));
                    }
                }
            }

            attempt += 1;
            if self.retry_delay_secs > 0.0 {
                sleep(Duration::from_secs_f64(self.retry_delay_secs)).await;
            }
        }
    }
}
