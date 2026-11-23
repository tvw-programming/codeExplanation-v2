use axum::Router;
use axum::routing::{get, post};

pub fn router() -> Router {
    Router::new()
        .route("/items", get(list_items))
        .route("/items", post(create_item))
}

async fn list_items() {}
async fn create_item() {}
