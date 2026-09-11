import random

def generate_key() -> str:
    """
    Genera key con el mismo formato que tu panel 8BP:
    ITACHI-XXXX-XXXX
    """
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def segment(length: int = 4) -> str:
        return "".join(random.choice(chars) for _ in range(length))

    return f"ITACHI-{segment()}-{segment()}"
