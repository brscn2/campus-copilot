"""TUMonline integration — student profile, grades, and lectures.

Uses the TUMonline wbservicesbasic XML API (same as TUM Campus App).
Auth is via a user-activated token from Token-Verwaltung.
Thesis opportunity search remains mock data for the hackathon demo.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import httpx

from src.config import get_settings
from src.exceptions import TUMAuthenticationError, TUMSystemUnavailableError
from src.lib.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT = 15.0


def _api_url(endpoint: str) -> str:
    settings = get_settings()
    token = settings.tumonline_token
    return f"{settings.tumonline_base_url}/{endpoint}?pToken={token}"


def _parse_rows(xml_text: str) -> list[dict[str, str | None]]:
    """Parse TUMonline XML rowset into a list of dicts."""
    root = ET.fromstring(xml_text)

    if root.tag == "error":
        msg = root.findtext("message", "Unknown TUMonline error")
        if "nicht bestätigt" in msg or "not confirmed" in msg.lower():
            raise TUMAuthenticationError(f"TUMonline token not activated: {msg}")
        raise TUMSystemUnavailableError(f"TUMonline error: {msg}")

    rows: list[dict[str, str | None]] = []
    for row_el in root.findall("row"):
        row: dict[str, str | None] = {}
        for child in row_el:
            if child.get("isnull") == "true":
                row[child.tag] = None
            else:
                row[child.tag] = (child.text or "").strip()
        rows.append(row)
    return rows


async def _fetch(endpoint: str) -> list[dict[str, str | None]]:
    """Fetch and parse a TUMonline wbservicesbasic endpoint."""
    url = _api_url(endpoint)
    logger.info("tumonline_fetch", endpoint=endpoint)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise TUMSystemUnavailableError(
                f"TUMonline returned {resp.status_code} for {endpoint}"
            )
        return _parse_rows(resp.text)


# ---------------------------------------------------------------------------
# Public API — real TUMonline data
# ---------------------------------------------------------------------------


async def get_identity() -> dict[str, Any]:
    """Get the authenticated student's identity."""
    rows = await _fetch("wbservicesbasic.id")
    if not rows:
        raise TUMSystemUnavailableError("TUMonline identity returned no data")
    row = rows[0]
    return {
        "username": row.get("kennung"),
        "first_name": row.get("vorname"),
        "last_name": row.get("familienname"),
        "obfuscated_id": row.get("obfuscated_id"),
    }


async def get_grades() -> list[dict[str, Any]]:
    """Get the student's exam grades.

    Returns:
        List of grade dicts with course_code, title, grade, credits, etc.
    """
    rows = await _fetch("wbservicesbasic.noten")
    grades: list[dict[str, Any]] = []
    for row in rows:
        grade_str = row.get("uninotenamekurz", "")
        grade_float: float | None = None
        if grade_str:
            try:
                grade_float = float(grade_str.replace(",", "."))
            except ValueError:
                pass

        credits_str = row.get("lv_credits", "0")
        try:
            credits = int(credits_str)
        except ValueError:
            credits = 0

        grades.append({
            "course_code": row.get("lv_nummer", ""),
            "title": row.get("lv_titel", ""),
            "grade": grade_str,
            "grade_float": grade_float,
            "credits": credits,
            "semester": row.get("lv_semester", ""),
            "examiner": row.get("pruefer_nachname", ""),
            "exam_type": row.get("exam_typ_name", ""),
            "exam_mode": row.get("modus", ""),
            "program": row.get("studienbezeichnung", ""),
            "degree": row.get("abschluss_name_kurz", ""),
        })
    return grades


async def get_lectures() -> list[dict[str, Any]]:
    """Get the student's currently enrolled lectures.

    Returns:
        List of lecture dicts with title, code, type, semester, professor.
    """
    rows = await _fetch("wbservicesbasic.veranstaltungenEigene")
    lectures: list[dict[str, Any]] = []
    for row in rows:
        title = row.get("stp_sp_titel", "")
        code = ""
        if "(" in title and title.endswith(")"):
            code = title.rsplit("(", 1)[-1].rstrip(")")
            display_title = title.rsplit("(", 1)[0].strip()
        else:
            display_title = title

        lectures.append({
            "title": display_title,
            "code": code,
            "full_title": title,
            "stp_sp_nr": row.get("stp_sp_nr", ""),
            "type": row.get("stp_lv_art_name", ""),
            "type_short": row.get("stp_lv_art_kurz", ""),
            "semester": row.get("semester_name", ""),
            "semester_id": row.get("semester_id", ""),
            "hours_per_week": row.get("stp_sp_sst", ""),
            "chair": row.get("org_name_betreut", ""),
            "lecturers": row.get("vortragende_mitwirkende", ""),
        })
    return lectures


async def get_course_description(course_id: int | str) -> dict[str, Any] | None:
    """Fetch course details from the NAT Course Catalog API.

    Args:
        course_id: The TUMonline course_id (stp_sp_nr from lectures).

    Returns:
        Dict with course_name, description_en, org, etc. or None if not found.
    """
    settings = get_settings()
    url = f"https://api.srv.nat.tum.de/api/v1/course/{course_id}"
    logger.info("tumonline_fetch_course_description", course_id=course_id)

    try:
        token_resp = await _fetch_nat_token()
        if not token_resp:
            return None

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {token_resp}", "accept": "application/json"}
            )
            if resp.status_code != 200:
                logger.warning("tumonline_course_not_found", course_id=course_id, status=resp.status_code)
                return None
            return resp.json()
    except Exception:
        logger.warning("tumonline_course_fetch_failed", course_id=course_id, exc_info=True)
        return None


async def _fetch_nat_token() -> str | None:
    """Get a NAT API Bearer token via Keycloak password grant."""
    settings = get_settings()
    if not settings.tum_username or not settings.tum_password:
        return None

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            "https://sso.srv.nat.tum.de/realms/dssnat/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "frontend",
                "username": settings.tum_username,
                "password": settings.tum_password,
            },
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("access_token")


async def get_tuition_status() -> dict[str, Any]:
    """Get tuition fee status."""
    rows = await _fetch("wbservicesbasic.studienbeitragsstatus")
    if not rows:
        return {"status": "unknown"}
    return dict(rows[0])


# ---------------------------------------------------------------------------
# Thesis opportunities — mock data (chair websites have no API)
# ---------------------------------------------------------------------------


MOCK_THESIS_OPPORTUNITIES: list[dict[str, Any]] = [
    {
        "id": "thesis-001",
        "chair": "Chair of Robotics, Artificial Intelligence and Real-time Systems",
        "professor_name": "Prof. Dr.-Ing. Alois Knoll",
        "professor_email": "knoll@in.tum.de",
        "topic": "Multi-Agent Reinforcement Learning for Autonomous Drone Swarms",
        "description": (
            "Develop and evaluate multi-agent RL algorithms for coordinating "
            "autonomous drone swarms in search-and-rescue scenarios."
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
            "database systems running on cloud infrastructure."
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
            "GPU acceleration with JAX or PyTorch."
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
            "privacy guarantees."
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
            "communication for autonomous driving scenarios in Munich."
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
            "robots. Integrate with ROS 2 and evaluate on the TUM kitchen benchmark."
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
    """Search for thesis opportunities from TUM chairs (mock data)."""
    logger.info("tumonline_search_thesis", keywords=keywords, chair=chair, tags=tags)

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
    """Look up professor contact details (mock data)."""
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
