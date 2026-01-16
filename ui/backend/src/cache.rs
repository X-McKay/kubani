use moka::future::Cache;
use once_cell::sync::Lazy;
use std::time::Duration;

// Global cache instance
static CACHE: Lazy<Cache<String, String>> = Lazy::new(|| {
    Cache::builder()
        .max_capacity(1000)
        .time_to_live(Duration::from_secs(5))
        .build()
});

pub fn init_cache() {
    // Force initialization of the lazy static
    Lazy::force(&CACHE);
    tracing::info!("Cache initialized");
}

pub async fn get(key: &str) -> Option<String> {
    CACHE.get(key).await
}

pub async fn set(key: String, value: String) {
    CACHE.insert(key, value).await;
}

pub async fn invalidate(key: &str) {
    CACHE.invalidate(key).await;
}
