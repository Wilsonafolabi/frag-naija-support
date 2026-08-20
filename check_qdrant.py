import asyncio

async def main():
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(url="http://localhost:6333")

    # 1. What collections exist and how many points each has
    cols = await client.get_collections()
    names = [c.name for c in cols.collections]
    print("COLLECTIONS:", names)
    for name in names:
        info = await client.get_collection(name)
        print(f"   {name} -> points={info.points_count}")

    if "support_knowledge" not in names:
        print("!! support_knowledge collection is MISSING")
        return

    # 2. What does a stored point actually look like
    points, _ = await client.scroll("support_knowledge", limit=2, with_payload=True)
    for p in points:
        payload = p.payload or {}
        print("PAYLOAD KEYS:", list(payload.keys()))
        meta = payload.get("metadata")
        if isinstance(meta, dict):
            print("METADATA KEYS:", list(meta.keys()))
        print("TEXT SNIPPET:", str(payload.get("text"))[:100])

    # 3. Run the EXACT search the app runs
    from app.config import get_settings
    from app.rag.embeddings import LocalEmbedder

    settings = get_settings()
    embedder = LocalEmbedder(settings.embedding_model)
    vec = await embedder.embed_query("Who are the confirmed sponsors of Frag Naija?")

    hits = await client.search(
        collection_name="support_knowledge",
        query_vector=vec,
        limit=5,
        with_payload=True,
    )
    print("SEARCH HITS:", len(hits))
    for h in hits:
        print(f"   score={h.score:.4f}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"FATAL: {type(e).__name__}: {e}")