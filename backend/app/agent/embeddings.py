import voyageai

EMBEDDING_MODEL = "voyage-4"

client = voyageai.AsyncClient()


async def embed_text(text: str, input_type: str) -> list[float]:
    """input_type is "document" when embedding text being stored (Development
    rows), or "query" when embedding a search query — Voyage tailors the
    vector differently for each, which matters for retrieval quality.
    """
    result = await client.embed([text], model=EMBEDDING_MODEL, input_type=input_type)
    return result.embeddings[0]
