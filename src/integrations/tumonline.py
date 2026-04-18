"""Mock TUMonline integration — thesis opportunity scraping.

In live mode this would scrape TUM chair websites for thesis listings.
For the hackathon demo, returns curated fake data.
"""

from __future__ import annotations

from typing import Any

from src.lib.logging import get_logger

logger = get_logger(__name__)

MOCK_THESIS_OPPORTUNITIES: list[dict[str, Any]] = [
    {
        "id": "thesis-001",
        "chair": "Chair of Robotics, Artificial Intelligence and Real-time Systems",
        "professor_name": "Prof. Dr.-Ing. Alois Knoll",
        "professor_email": "knoll@in.tum.de",
        "topic": "Multi-Agent Reinforcement Learning for Autonomous Drone Swarms",
        "description": (
            "Develop and evaluate multi-agent RL algorithms for coordinating "
            "autonomous drone swarms in search-and-rescue scenarios. The work involves "
            "simulation in AirSim and real-world validation on TUM's drone testbed."
        ),
        "tags": ["reinforcement-learning", "multi-agent", "robotics", "drones"],
        "source_url": "https://www.ce.cit.tum.de/air/theses/",
    },
    {
        "id": "thesis-002",
        "chair": "Chair of Data Engineering",
        "professor_name": "Prof. Dr. Alfons Kemper",
        "professor_email": "kemper@in.tum.de",
        "topic": "Adaptive Query Optimization in Cloud-Native Database Systems",
        "description": (
            "Investigate learned query optimization techniques for Umbra/HyPer-style "
            "database systems running on cloud infrastructure. Focus on workload-adaptive "
            "cardinality estimation using lightweight neural models."
        ),
        "tags": ["databases", "query-optimization", "machine-learning", "cloud"],
        "source_url": "https://db.in.tum.de/teaching/theses/",
    },
    {
        "id": "thesis-003",
        "chair": "Chair of Scientific Computing",
        "professor_name": "Prof. Dr. Hans-Joachim Bungartz",
        "professor_email": "bungartz@in.tum.de",
        "topic": "Physics-Informed Neural Networks for Fluid Dynamics Simulation",
        "description": (
            "Apply PINNs to accelerate computational fluid dynamics simulations. "
            "Compare against classical FEM solvers on benchmark problems from the "
            "ExaHyPE framework. GPU acceleration with JAX or PyTorch."
        ),
        "tags": ["scientific-computing", "neural-networks", "simulation", "HPC"],
        "source_url": "https://www5.in.tum.de/wiki/index.php/Thesis_Topics",
    },
    {
        "id": "thesis-004",
        "chair": "Chair of Cyber Trust",
        "professor_name": "Prof. Dr. Jens Grossklags",
        "professor_email": "grossklags@in.tum.de",
        "topic": "Privacy-Preserving Federated Learning with Differential Privacy Guarantees",
        "description": (
            "Design and implement a federated learning framework with formal differential "
            "privacy guarantees. Evaluate trade-offs between model accuracy and privacy "
            "budget on healthcare and financial datasets."
        ),
        "tags": ["privacy", "federated-learning", "security", "machine-learning"],
        "source_url": "https://www.cybertrust.cit.tum.de/theses/",
    },
    {
        "id": "thesis-005",
        "chair": "Chair of Connected Mobility",
        "professor_name": "Prof. Dr.-Ing. Jörg Ott",
        "professor_email": "ott@in.tum.de",
        "topic": "Edge Computing for Real-Time V2X Communication in Urban Environments",
        "description": (
            "Design an edge computing architecture for Vehicle-to-Everything (V2X) "
            "communication. Implement and evaluate latency-optimized message routing "
            "protocols for autonomous driving scenarios in Munich."
        ),
        "tags": ["edge-computing", "V2X", "networking", "autonomous-driving"],
        "source_url": "https://www.2.2.2.2/theses/",
    },
    {
        "id": "thesis-006",
        "chair": "Chair of Robotics, Artificial Intelligence and Real-time Systems",
        "professor_name": "Prof. Dr.-Ing. Alois Knoll",
        "professor_email": "knoll@in.tum.de",
        "topic": "LLM-Powered Task Planning for Household Service Robots",
        "description": (
            "Leverage large language models for high-level task planning in household "
            "robots. Integrate with ROS 2 and evaluate on the TUM kitchen benchmark. "
            "Focus on grounding language instructions in robot capabilities."
        ),
        "tags": ["LLM", "robotics", "task-planning", "ROS"],
        "source_url": "https://www.ce.cit.tum.de/air/theses/",
    },
]


async def search_thesis_opportunities(
    *,
    keywords: list[str] | None = None,
    chair: str | None = None,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search for thesis opportunities from TUM chairs.

    Args:
        keywords: Optional keywords to filter by topic/description.
        chair: Optional chair name filter substring.
        tags: Optional tag filter — matches if any tag overlaps.

    Returns:
        List of matching thesis opportunity dicts.
    """
    logger.info(
        "tumonline_search_thesis",
        keywords=keywords,
        chair=chair,
        tags=tags,
    )

    results: list[dict[str, Any]] = []
    for opp in MOCK_THESIS_OPPORTUNITIES:
        if chair and chair.lower() not in opp["chair"].lower():
            continue

        if tags:
            opp_tags: list[str] = opp["tags"]
            if not any(t.lower() in [ot.lower() for ot in opp_tags] for t in tags):
                continue

        if keywords:
            text = f"{opp['topic']} {opp['description']}".lower()
            if not any(kw.lower() in text for kw in keywords):
                continue

        results.append(opp)

    return results


async def get_professor_info(professor_email: str) -> dict[str, Any] | None:
    """Look up professor contact details.

    Args:
        professor_email: The professor's email address.

    Returns:
        Professor info dict or None if not found.
    """
    logger.info("tumonline_get_professor", email=professor_email)

    for opp in MOCK_THESIS_OPPORTUNITIES:
        if opp["professor_email"] == professor_email:
            return {
                "name": opp["professor_name"],
                "email": opp["professor_email"],
                "chair": opp["chair"],
                "office_hours": "Wednesday 14:00-16:00 (by appointment)",
            }
    return None
