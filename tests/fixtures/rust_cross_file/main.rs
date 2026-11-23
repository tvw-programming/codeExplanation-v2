mod api;

use axum::Router;

pub async fn main() {
    let app = Router::new()
        .nest("/api", api::router())
        .route("/health", axum::routing::get(health));
}

async fn health() -> &'static str {
    "ok"
}
