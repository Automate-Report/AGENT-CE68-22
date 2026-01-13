
def load_file(file_path, logger) -> list:
    context_list = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            context_list = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"[!] Warning: File not found: {file_path}")

    return context_list