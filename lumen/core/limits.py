"""Fixed limits: not user settings, but in one place so they are easy to find and tune."""

SKIP_DIRS = {  # dependency and build folders: never personal files
    "node_modules", "__pycache__", "venv", "site-packages", "dist", "build",
    "target", "vendor", "bower_components",
}
MAX_EXTRACT_BYTES = 25 * 1024 * 1024  # don't open files bigger than this for text
MAX_CONTENT_CHARS = 200_000           # text stored per file in the index
MAX_PDF_PAGES = 100
INDEX_KEEP_ALIVE = "2m"  # let Ollama free the GPU soon after indexing instead of holding it 30 min
