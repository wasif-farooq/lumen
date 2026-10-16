"""What kind of file something is, by its extension (lowercase, without the dot)."""

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"}
VIDEO_EXTS = {"mp4", "mkv", "mov", "webm", "avi", "m4v", "3gp", "wmv", "flv", "mpg", "mpeg"}
AUDIO_EXTS = {"mp3", "m4a", "wav", "ogg", "opus", "flac", "aac", "wma"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS

# Read as plain text when indexing
TEXT_EXTS = {
    "txt",
    "md",
    "markdown",
    "rst",
    "csv",
    "tsv",
    "json",
    "jsonl",
    "yaml",
    "yml",
    "toml",
    "ini",
    "cfg",
    "conf",
    "log",
    "xml",
    "html",
    "htm",
    "tex",
    "srt",
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "mjs",
    "java",
    "kt",
    "c",
    "h",
    "cpp",
    "hpp",
    "cs",
    "go",
    "rs",
    "rb",
    "php",
    "swift",
    "dart",
    "sh",
    "bash",
    "sql",
    "css",
    "scss",
    "vue",
    "svelte",
    "ipynb",
    "gradle",
    "r",
    "lua",
}

# Opening these could execute them, so their folder is shown instead
RUNNABLE_EXTS = {
    "sh",
    "bash",
    "zsh",
    "py",
    "pl",
    "rb",
    "appimage",
    "desktop",
    "run",
    "bin",
    "exe",
    "msi",
    "bat",
    "cmd",
    "jar",
    "deb",
    "rpm",
    "flatpakref",
    "snap",
}

# Search ranking: personal documents and media first, then files that are sometimes personal
DOC_EXTS = [
    *("pdf", "doc", "docx", "odt", "rtf", "txt", "xls", "xlsx", "ods", "csv", "tsv", "ppt", "pptx", "odp", "epub"),
    *("jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff", "heic"),
    *("mp4", "mkv", "mov", "webm", "avi", "m4v", "3gp", "wmv"),
    *("mp3", "m4a", "wav", "ogg", "opus", "flac", "aac"),
]
MIXED_EXTS = ["md", "html", "htm", "zip", "rar", "7z", "tar", "gz"]  # sometimes personal, often project files


def kind_of(ext: str) -> str:
    """The kind the app shows a badge for: video, audio, image, pdf, doc, sheet, archive or file."""
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in IMAGE_EXTS:
        return "image"
    if ext == "pdf":
        return "pdf"
    if ext in ("doc", "docx", "odt", "rtf"):
        return "doc"
    if ext in ("xls", "xlsx", "ods", "csv", "tsv"):
        return "sheet"
    if ext in ("zip", "tar", "gz", "7z", "rar", "xz"):
        return "archive"
    return "file"
