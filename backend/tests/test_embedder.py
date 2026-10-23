"""The real embedding model (Qwen3-Embedding-0.6B): shapes, normalisation, query prefix, ranking."""
import numpy as np
import pytest

import config
from embedder import get_embedder

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def emb():
    return get_embedder()


def test_configured_model_and_dim(emb):
    assert emb.model_name == config.EMBED_MODEL
    assert emb.dim == config.EMBED_DIM == 1024


def test_documents_are_normalised_float32(emb):
    v = emb.embed_documents(["Berlin is the capital of Germany.", "Water boils at 100 degrees Celsius."])
    assert v.shape == (2, 1024)
    assert v.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-2)


def test_queries_get_the_instruction_prefix(emb):
    text = "What is the capital of Germany?"
    [q] = emb.embed_queries([text])
    [d] = emb.embed_documents([text])
    np.testing.assert_allclose(np.linalg.norm(q), 1.0, atol=1e-2)
    assert not np.allclose(q, d, atol=1e-3)


def test_query_is_closest_to_the_relevant_passage(emb):
    [q] = emb.embed_queries(["What is the capital of Germany?"])
    docs = emb.embed_documents([
        "The recipe needs two eggs and a cup of flour.",
        "Berlin is the capital and largest city of Germany.",
        "Photosynthesis turns light into chemical energy.",
    ])
    assert int(np.argmax(docs @ q)) == 1


def test_empty_input(emb):
    assert emb.embed_documents([]).shape == (0, 1024)
    assert emb.embed_queries([]).shape == (0, 1024)
