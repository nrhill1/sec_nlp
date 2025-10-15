// src/cache/disk.rs - Disk-based caching implementation
use crate::errors::IoError;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::time::{Duration, SystemTime};

type Result<T> = std::result::Result<T, IoError>;

#[derive(Debug)]
pub struct DiskCache {
    cache_dir: PathBuf,
    ttl: Duration,
}

#[derive(Serialize, Deserialize)]
struct CacheEntry<T> {
    data: T,
    timestamp: SystemTime,
}

impl DiskCache {
    pub fn new(cache_dir: PathBuf, ttl: Duration) -> Result<Self> {
        std::fs::create_dir_all(&cache_dir)?;
        Ok(Self { cache_dir, ttl })
    }

    pub fn with_default_ttl(cache_dir: PathBuf) -> Result<Self> {
        Self::new(cache_dir, Duration::from_secs(3600)) // 1 hour default
    }

    fn cache_path(&self, key: &str) -> PathBuf {
        let safe_key = key.replace(['/', '\\', ':'], "_");
        self.cache_dir.join(format!("{}.json", safe_key))
    }

    pub fn get<T: for<'de> Deserialize<'de>>(&self, key: &str) -> Result<Option<T>> {
        let path = self.cache_path(key);

        if !path.exists() {
            return Ok(None);
        }

        let contents = std::fs::read_to_string(&path)?;
        let entry: CacheEntry<T> =
            serde_json::from_str(&contents).map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;

        // Check if expired
        if let Ok(elapsed) = entry.timestamp.elapsed() {
            if elapsed > self.ttl {
                std::fs::remove_file(&path).ok();
                return Ok(None);
            }
        }

        Ok(Some(entry.data))
    }

    pub fn set<T: Serialize>(&self, key: &str, value: &T) -> Result<()> {
        let entry = CacheEntry {
            data: value,
            timestamp: SystemTime::now(),
        };

        let path = self.cache_path(key);
        let json = serde_json::to_string_pretty(&entry)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;

        std::fs::write(path, json)?;
        Ok(())
    }

    pub fn invalidate(&self, key: &str) -> Result<()> {
        let path = self.cache_path(key);
        if path.exists() {
            std::fs::remove_file(path)?;
        }
        Ok(())
    }

    pub fn clear(&self) -> Result<()> {
        for entry in std::fs::read_dir(&self.cache_dir)? {
            let entry = entry?;
            if entry.path().extension().and_then(|s| s.to_str()) == Some("json") {
                std::fs::remove_file(entry.path())?;
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn test_cache_set_get() {
        let dir = tempdir().unwrap();
        let cache = DiskCache::with_default_ttl(dir.path().to_path_buf()).unwrap();

        cache.set("test_key", &"test_value".to_string()).unwrap();
        let result: Option<String> = cache.get("test_key").unwrap();

        assert_eq!(result, Some("test_value".to_string()));
    }

    #[test]
    fn test_cache_miss() {
        let dir = tempdir().unwrap();
        let cache = DiskCache::with_default_ttl(dir.path().to_path_buf()).unwrap();

        let result: Option<String> = cache.get("nonexistent").unwrap();
        assert_eq!(result, None);
    }

    #[test]
    fn test_cache_invalidate() {
        let dir = tempdir().unwrap();
        let cache = DiskCache::with_default_ttl(dir.path().to_path_buf()).unwrap();

        cache.set("test", &42).unwrap();
        cache.invalidate("test").unwrap();

        let result: Option<i32> = cache.get("test").unwrap();
        assert_eq!(result, None);
    }
}
