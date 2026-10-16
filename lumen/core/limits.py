"""Fixed limits: not user settings, but in one place so they are easy to find and tune."""

DEFAULT_PORT = 8765  # where `lumen serve` listens and the app looks for it

SKIP_DIRS = {  # dependency and build folders: never personal files
    "node_modules",
    "__pycache__",
    "venv",
    "site-packages",
    "dist",
    "build",
    "target",
    "vendor",
    "bower_components",
}
MAX_TEXT_CHARS = 10_000_000  # text kept per file (about 5,000 pages); read in pieces up to this
MAX_ZIPPED_BYTES = 100 * 1024 * 1024  # office documents and e-books bigger than this are not unpacked
MAX_UNPACKED_BYTES = 500 * 1024 * 1024  # read at most this much from any one part of a zipped document
MAX_RENDER_BYTES = 25 * 1024 * 1024  # images and scans bigger than this are not described
INDEX_KEEP_ALIVE = "2m"  # let Ollama free the GPU soon after indexing instead of holding it 30 min
