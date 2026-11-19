mod users;

use axum::Router;

pub async fn main() {
    let app = Router::new().route("/users", axum::routing::get(list_users));
}

async fn list_users() -> &'static str {
    "ok"
}
