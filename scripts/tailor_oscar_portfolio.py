import sys
sys.path.insert(0, "/app")
import logging
import re
from aura.config import get_validated_config
from aura.database import PaperDatabase
from aura.recommender import RecommendationEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tailor")

db_path = "/app/data/papers.db"
db = PaperDatabase(db_path)

# 1. Tracked Collaborators from Oscar Hickman's Research Portfolio Index
collaborators = [
    ("Carlton Baugh", "Durham University"),
    ("Shaun Cole", "Durham University"),
    ("S. Cole", "Durham University"),
    ("Baojiu Li", "Durham University"),
    ("Sownak Bose", "Durham University"),
    ("Carolina Cuesta-Lazaro", "Durham / Harvard / MIT"),
    ("Francisco Villaescusa-Navarro", "Flatiron CCA"),
    ("F. Villaescusa-Navarro", "Flatiron CCA"),
    ("Idit Zehavi", "Case Western Reserve"),
    ("Harry Desmond", "Portsmouth"),
    ("H. Desmond", "Portsmouth"),
    ("Owen Jessop", "Durham University"),
    ("Suttikoon Koonkor", "Durham University"),
    ("Sergio Contreras", "DIPC"),
    ("Christian Arnold", "Durham University"),
    ("Kai Wang", "Durham University"),
]

logger.info("Adding tracked collaborators...")
for name, affil in collaborators:
    try:
        db.conn.execute(
            "INSERT OR IGNORE INTO tracked_authors (name, affiliation, relationship) VALUES (?, ?, ?)",
            (name, affil, "collaborator"),
        )
    except Exception as e:
        logger.warning(f"Error adding {name}: {e}")
db.conn.commit()

logger.info("Auto-tagging existing papers with collaborator and author tags...")
db.auto_tag_all_existing_papers_by_authors()
db.conn.commit()

# 2. Select prime cosmology papers matching Oscar's 15 projects
core_project_regexes = [
    r"\bsimulation[- ]based inference\b",
    r"\bneural posterior estimation\b",
    r"\bfield[- ]level inference\b",
    r"\bgalaxy clustering\b",
    r"\bhalo occupation\b",
    r"\bassembly bias\b",
    r"\bdynamical friction\b",
    r"\bmerger tree\b",
    r"\bFLAMINGO\b",
    r"\bCAMELS\b",
    r"\bCOLIBRE\b",
    r"\bGALFORM\b",
    r"\bcosmic shear\b",
    r"\bmodified gravity\b",
    r"\bf\(R\)\b",
    r"\bnDGP\b",
    r"\bhalo mass function\b",
    r"\bstrong lensing\b",
    r"\bgalaxy[- ]halo connection\b",
    r"\binitial mass function\b",
    r"\bS_8 tension\b",
    r"\bsigma_8\b",
    r"\bDESI DR1\b",
    r"\bDESI BGS\b"
]

rows = db.conn.execute("SELECT arxiv_id, title, abstract, authors FROM papers").fetchall()

seed_papers = []
for r in rows:
    title = r["title"]
    abstract = r["abstract"] or ""
    auths = r["authors"] or ""
    text = f"{title} {abstract}"
    
    # Check if co-authored by Oscar's Durham group or collaborators
    is_collab = any(c[0].lower() in auths.lower() for c in collaborators)
    
    # Check if matches core project topics
    matched_topics = [rgx for rgx in core_project_regexes if re.search(rgx, text, re.I)]
    
    # Exclude non-cosmology stellar/exoplanet noise
    is_noise = bool(re.search(r"\b(exoplanet|sunspot|white dwarf|pulsar|coronal|solar wind|hot jupiter)\b", title, re.I))
    
    if (is_collab and not is_noise) or len(matched_topics) >= 1:
        if not is_noise:
            seed_papers.append((r["arxiv_id"], title, is_collab, len(matched_topics)))

logger.info(f"Identified {len(seed_papers)} top-tier portfolio-relevant papers.")

# 3. Apply seed ratings for Oscar's accounts (user_id 1 and 3)
users_to_tailor = [1, 3]

for uid in users_to_tailor:
    logger.info(f"Applying seed ratings for user_id={uid}...")
    rated_count = 0
    for aid, title, is_collab, n_topics in seed_papers[:35]:
        db.rate_paper(aid, rating=5, user_id=uid)
        rated_count += 1
    logger.info(f"User {uid}: primed {rated_count} positive ratings.")

db.close()

# 4. Retrain Preference Models via RecommendationEngine
logger.info("Initializing RecommendationEngine to retrain preference models...")
cfg = get_validated_config("/app/config.yaml")
engine = RecommendationEngine(
    data_dir=cfg.get("data_dir", "data"),
    categories=cfg.get("categories", []),
    embedding_model=cfg.get("embedding_model", "all-MiniLM-L6-v2"),
    simulation_codes=cfg.get("simulation_codes"),
)

for uid in users_to_tailor:
    logger.info(f"Retraining preference model for user_id={uid}...")
    metrics = engine.retrain_full(user_id=uid, epochs=25)
    logger.info(f"User {uid} Retrain metrics: {metrics}")

# 5. Verify Recommendations
for uid in users_to_tailor:
    logger.info(f"\n================ TOP 10 RECOMMENDATIONS FOR USER {uid} ================")
    recs = engine.get_recommendations(limit=10, unrated_only=True, user_id=uid)
    for idx, p in enumerate(recs, 1):
        net_bonus = p.get('network_bonus', 0.0)
        logger.info(f"#{idx:02d} [Score: {p.get('score'):.4f} | NetBonus: {net_bonus:.2f}] {p['arxiv_id']}: {p['title'][:70]}")

print("PORTFOLIO_TAILORING_COMPLETE")
