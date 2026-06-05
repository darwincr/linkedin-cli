import re
from urllib.parse import urljoin, urlparse

from linkedin_cli.browser.nav import goto_page

SAVED_JOBS_URL = "https://www.linkedin.com/my-items/saved-jobs/"
JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")
JOB_LINKS_SELECTOR = 'a[href*="/jobs/view/"]'


def _job_id(job_id_or_url: str) -> str:
    if job_id_or_url.isdigit():
        return job_id_or_url
    match = JOB_ID_RE.search(job_id_or_url)
    if match:
        return match.group(1)
    raise ValueError(f"Expected a LinkedIn job id or URL, got {job_id_or_url!r}")


def _clean_url(base_url: str, href: str) -> str:
    full_url = urljoin(base_url, href.strip())
    parsed = urlparse(full_url)
    return parsed._replace(query="", fragment="").geturl()


def _text_lines(text: str) -> list[str]:
    seen = set()
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def _job_from_link(page, link) -> dict | None:
    href = link.get_attribute("href") or ""
    match = JOB_ID_RE.search(href)
    if not match:
        return None

    card = link.locator("xpath=ancestor::li[1]")
    lines = _text_lines(card.inner_text() if card.count() > 0 else link.inner_text())
    title = lines[0] if lines else link.inner_text().strip()
    details = [line for line in lines[1:] if title and not line.startswith(title)]

    return {
        "job_id": match.group(1),
        "url": _clean_url(page.url, href),
        "title": title,
        "company": details[0] if len(details) > 0 else None,
        "location": details[1] if len(details) > 1 else None,
        "listed": details[-1] if len(details) > 2 else None,
    }


def _open(session: "LinkedInSession") -> None:
    session.ensure_browser()
    goto_page(
        session,
        action=lambda: session.page.goto(SAVED_JOBS_URL),
        expected_url_pattern="/my-items/saved-jobs/",
        error_message="Failed to reach saved jobs",
    )


def _card_for_job(session: "LinkedInSession", job_id: str):
    links = session.page.locator(f'a[href*="/jobs/view/{job_id}"]')
    for link in links.all():
        card = link.locator("xpath=ancestor::li[1]")
        if card.count() > 0:
            return card.first
    return None


def _unsave_card(session: "LinkedInSession", card, job_id: str) -> dict:
    link = card.locator(JOB_LINKS_SELECTOR).first
    job = _job_from_link(session.page, link) if link.count() > 0 else None
    job = job or {"job_id": job_id, "url": f"https://www.linkedin.com/jobs/view/{job_id}/"}

    direct_unsave = card.get_by_text("Unsave", exact=True)
    if direct_unsave.count() > 0:
        direct_unsave.first.click()
    else:
        actions = card.locator(
            'button[aria-label*="more actions" i], '
            'button[aria-label*="actions" i]'
        )
        if actions.count() == 0:
            raise RuntimeError(f"Could not find saved-job actions menu for {job_id}")

        actions.first.click()
        unsave = session.page.get_by_text("Unsave", exact=True)
        if unsave.count() == 0:
            raise RuntimeError(f"Could not find Unsave action for {job_id}")
        unsave.first.click()

    session.wait()
    still_saved = _card_for_job(session, job_id) is not None
    return {**job, "saved": still_saved, "changed": not still_saved}


def list_saved_jobs(session: "LinkedInSession", *, page: int = 1) -> dict:
    """Return visible jobs from LinkedIn's saved jobs page."""
    _open(session)

    jobs, seen = [], set()
    for link in session.page.locator(JOB_LINKS_SELECTOR).all():
        job = _job_from_link(session.page, link)
        if not job or job["job_id"] in seen:
            continue
        seen.add(job["job_id"])
        jobs.append(job)

    return {"page": page, "jobs": jobs}


def unsave_saved_job(session: "LinkedInSession", job_id_or_url: str) -> dict:
    """Unsave a visible job from LinkedIn's saved jobs page."""
    return unsave_saved_jobs(session, [job_id_or_url])["jobs"][0]


def unsave_saved_jobs(session: "LinkedInSession", job_ids_or_urls: list[str]) -> dict:
    """Unsave visible jobs from LinkedIn's saved jobs page in one browser pass."""
    job_ids = [_job_id(job) for job in job_ids_or_urls]
    _open(session)

    results = []
    for job_id in job_ids:
        card = _card_for_job(session, job_id)
        if card is None:
            results.append({
                "job_id": job_id,
                "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
                "saved": False,
                "changed": False,
            })
            continue

        results.append(_unsave_card(session, card, job_id))

    return {"jobs": results}
