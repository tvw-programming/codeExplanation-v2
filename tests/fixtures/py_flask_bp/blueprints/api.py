from flask import Blueprint

bp = Blueprint("api", __name__)


@bp.route("/health", methods=["GET"])
def health():
    return "ok"


@bp.route("/items/<int:item_id>", methods=["GET", "POST"])
def items(item_id: int):
    return {"id": item_id}
