from app.config import get_settings
from app.services.retrieval_service import RetrievalService
from app.vectorstore.memory_store import KnowledgeMemoryStore

s = get_settings()
store = KnowledgeMemoryStore(s)
rs = RetrievalService(settings=s, vector_store=store)
print("chunks", store.count())
secs = sorted({c.metadata.get("section", "") for c in store.get_all()})
for sec in secs:
    print("-", sec[:90])
print("---")
queries = [
    "What services do you offer?",
    "Tell me about UpgradeVIP",
    "What is your company philosophy?",
    "Do you have Meet and Greet?",
    "What vehicles do you use for transfers?",
    "What are your cancellation terms?",
    "Where are your offices?",
    "What certifications do you have?",
    "Who uses your services?",
    "Tell me about porter service",
    "Do you offer lounge access?",
    "What is included in Airport VIP?",
    "How long have you been operating?",
    "What is the Travel Delight Guarantee?",
    "Do you provide wheelchair assistance?",
    "privacy policy",
    "ABTA ATOL IATA",
    "What is VIP Terminal access?",
    "Do you partner with local operators?",
    "social media links",
]
for q in queries:
    chunks = rs.retrieve(q)
    print("Q:", q)
    print(" intents:", rs.detect_intents(q))
    if not chunks:
        print("  NONE")
    else:
        for c in chunks[:4]:
            section = str(c.metadata.get("section", ""))[:70]
            print(f"  {c.score:.2f} | {section}")
    print()
