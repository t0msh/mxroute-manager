from flask import Blueprint, current_app, jsonify, render_template, request

from utils.api_catalog import build_openapi_document, collect_api_routes
from utils.auth_helpers import require_admin

api_docs_bp = Blueprint("api_docs", __name__)


@api_docs_bp.route("/api/docs")
@require_admin
def api_docs_page():
    routes = collect_api_routes(current_app)
    tags = sorted({route["tag"] for route in routes})
    grouped = {tag: [route for route in routes if route["tag"] == tag] for tag in tags}
    return render_template(
        "api_docs.html",
        grouped_routes=grouped,
        route_count=len(routes),
    )


@api_docs_bp.route("/api/openapi.json")
@require_admin
def openapi_json():
    base_url = request.url_root.rstrip("/")
    return jsonify(build_openapi_document(current_app, base_url=base_url))
