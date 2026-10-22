from transformers import AutoTokenizer


class HFTokenizer:
    """Tokenizer of the embedding model, loaded without the model weights."""

    def __init__(self, model_name: str):
        # the Rust backend directly: ~10x less overhead per call than the transformers wrapper
        self._tok = AutoTokenizer.from_pretrained(model_name).backend_tokenizer

    def count(self, text: str) -> int:
        return len(self._tok.encode(text, add_special_tokens=False).ids)

    def offsets(self, text: str) -> list[tuple[int, int]]:
        return list(self._tok.encode(text, add_special_tokens=False).offsets)
