from app.utils.oss_uploader import ObjectStorageClient
from app.utils.public_file_urls import public_file_url


def test_public_file_url_avoids_overlapping_proxy_prefix() -> None:
    path = "/askai-api/api/files/user/image.png"
    assert public_file_url("/askai-api", path) == path
    assert public_file_url("https://example.com/askai-api", path) == f"https://example.com{path}"
    assert public_file_url("https://example.com", path) == f"https://example.com{path}"
    assert public_file_url("https://cdn.example.com/assets", path) == f"https://cdn.example.com/assets{path}"


def test_historical_double_prefix_is_repaired_and_resigned() -> None:
    storage = ObjectStorageClient.__new__(ObjectStorageClient)
    storage.storage_backend = "local"
    storage.file_public_base_url = "/askai-api"
    storage.file_public_path_prefix = "/askai-api/api/files"
    storage.sign_url = lambda object_path: f"/askai-api/api/files/{object_path}?expires=fresh"

    content = "![cover](/askai-api/askai-api/api/files/user/image.png?expires=old&signature=old)"

    assert storage.refresh_markdown_urls(content) == (
        "![cover](/askai-api/api/files/user/image.png?expires=fresh)"
    )


def test_storage_builds_single_prefix_and_refreshes_canonical_urls_once() -> None:
    storage = ObjectStorageClient.__new__(ObjectStorageClient)
    storage.storage_backend = "local"
    storage.file_public_base_url = "https://example.com/askai-api"
    storage.file_public_path_prefix = "/askai-api/api/files"
    storage.sign_url = lambda object_path: f"https://example.com/askai-api/api/files/{object_path}?expires=fresh"

    assert storage._build_public_url("user/image.png", absolute=False) == (
        "https://example.com/askai-api/api/files/user/image.png"
    )
    content = "![cover](https://example.com/askai-api/api/files/user/image.png?expires=old)"
    assert storage.refresh_markdown_urls(content) == (
        "![cover](https://example.com/askai-api/api/files/user/image.png?expires=fresh)"
    )
