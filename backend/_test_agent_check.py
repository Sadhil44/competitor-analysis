import asyncio, time
import httpx

async def main():
    questions = [
        "How are we positioned against Epic Gardening on raised beds?",
        "What raised bed products has Vego Garden added recently?",
        "Are there any recent price changes I should know about?",
        "What gaps do we have in our raised bed assortment?",
        "Tell me about Gurney's recent campaigns",
    ]
    async with httpx.AsyncClient(timeout=90.0) as client:
        for q in questions:
            t0 = time.time()
            try:
                r = await client.post("http://localhost:8000/agent/ask", json={"question": q})
                dt = time.time() - t0
                print(f"=== Q: {q}")
                print(f"status={r.status_code} time={dt:.1f}s")
                if r.status_code == 200:
                    body = r.json()
                    ans = body.get("answer", "")
                    print("ANSWER:", ans[:600])
                else:
                    print("BODY:", r.text[:600])
            except Exception as e:
                print(f"=== Q: {q}")
                print("EXCEPTION:", repr(e))
            print()

asyncio.run(main())
