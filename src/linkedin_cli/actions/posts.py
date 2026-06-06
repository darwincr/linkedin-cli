import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlencode, urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from linkedin_cli.browser.nav import goto_page
from linkedin_cli.url_utils import public_id_to_url, url_to_public_id


ACTIVITY_RE = re.compile(r"urn:li:(?:activity|share):(\d+)|activity-(\d+)")
COMMENT_RE = re.compile(r"(?:fsd_)?comment:\((\d+),urn:li:activity:\d+\)|comment:\(activity:\d+,(\d+)\)")
REACTIONS = {"like", "celebrate", "support", "love", "insightful", "funny"}

SELECTORS = {
    "post": (
        'div.feed-shared-update-v2, '
        'div[data-urn*="urn:li:activity"], '
        'div[data-id*="urn:li:activity"]'
    ),
    "comment": (
        'article.comments-comment-item, '
        'div.comments-comment-item, '
        'div[data-test-id*="comment"]'
    ),
    "start_post": (
        'button:has-text("Start a post"), '
        'button[aria-label*="Start a post" i], '
        'button.share-box-feed-entry__trigger'
    ),
    "composer": 'div[role="dialog"], div[role="alertdialog"], div.artdeco-modal-overlay',
    "editor": (
        'div[role="dialog"] .ql-editor[role="textbox"], '
        'div[role="dialog"] div[role="textbox"][contenteditable="true"], '
        'div[role="dialog"] div[contenteditable="true"]'
    ),
    "post_button": (
        'div[role="dialog"] button:has-text("Post"), '
        'div[role="dialog"] button[aria-label*="Post" i]'
    ),
    "close_composer": (
        'div[role="dialog"] button[aria-label*="Dismiss" i], '
        'div[role="dialog"] button[aria-label*="Close" i]'
    ),
    "save_draft": (
        'button:has-text("Save draft"), '
        'button[aria-label*="Save draft" i]'
    ),
    "media_button": (
        'div[role="dialog"] button[aria-label*="Add media" i], '
        'div[role="dialog"] button:has-text("Media")'
    ),
    "document_button": (
        'div[role="dialog"] button[aria-label*="Add a document" i], '
        'div[role="dialog"] button:has-text("Document"), '
        'div[role="dialog"] [role="menuitem"]:has-text("Document")'
    ),
    "poll_button": (
        'div[role="dialog"] button[aria-label*="Create a poll" i], '
        'div[role="dialog"] button:has-text("Create a poll"), '
        'div[role="dialog"] button:has-text("Poll"), '
        'div[role="dialog"] [role="menuitem"]:has-text("Poll")'
    ),
    "more_button": (
        'div[role="dialog"] button[aria-label*="More" i], '
        'div[role="dialog"] button:has-text("More")'
    ),
    "schedule_button": (
        'div[role="dialog"] button[aria-label*="Schedule" i], '
        'div[role="dialog"] button:has-text("Schedule")'
    ),
    "confirm_schedule": (
        'div[role="dialog"] button:has-text("Next"), '
        'div[role="dialog"] button:has-text("Done"), '
        'div[role="dialog"] button:has-text("Schedule")'
    ),
    "attachment_next": (
        'div[role="dialog"] button:has-text("Next"), '
        'div[role="dialog"] button:has-text("Done")'
    ),
    "overflow": (
        'button[aria-label*="More" i], '
        'button[aria-label*="Open control menu" i]'
    ),
    "delete_menu": (
        '[role="menuitem"]:has-text("Delete post"), '
        'div[role="menu"] span:has-text("Delete"), '
        'div[role="menu"] button:has-text("Delete")'
    ),
    "confirm_delete": (
        'button:has-text("Delete"), '
        'button[aria-label*="Delete" i]'
    ),
    "comment_editor": (
        'div.ProseMirror[contenteditable="true"][role="textbox"], '
        '.ql-editor[role="textbox"], '
        'div[contenteditable="true"][role="textbox"], '
        'div.comments-comment-texteditor div[contenteditable="true"]'
    ),
    "comment_submit": (
        'button:has-text("Reply"), '
        'button:has-text("Post"), '
        'button[aria-label*="Reply" i], '
        'button[aria-label*="Post" i]'
    ),
}


def _clean_url(base_url: str, href: str) -> str:
    full_url = urljoin(base_url, href.strip())
    parsed = urlparse(full_url)
    return parsed._replace(query="", fragment="").geturl()


def _activity_id(value: str | None) -> str | None:
    if not value:
        return None
    match = ACTIVITY_RE.search(unquote(value))
    if not match:
        return None
    return next(group for group in match.groups() if group)


def _comment_id(value: str | None) -> str | None:
    if not value:
        return None
    match = COMMENT_RE.search(unquote(value))
    if not match:
        return None
    return next(group for group in match.groups() if group)


def _post_url(post_id_or_url: str) -> str:
    if post_id_or_url.startswith("http://") or post_id_or_url.startswith("https://"):
        return post_id_or_url
    if post_id_or_url.isdigit():
        urn = f"urn:li:activity:{post_id_or_url}"
        return f"https://www.linkedin.com/feed/update/{urn}/"
    if post_id_or_url.startswith("urn:li:"):
        return f"https://www.linkedin.com/feed/update/{post_id_or_url}/"
    raise ValueError(f"Expected a LinkedIn post/activity id, URN, or URL, got {post_id_or_url!r}")


def _comment_url(post_id_or_url: str, comment_id: str | None = None) -> str:
    if post_id_or_url.startswith("http://") or post_id_or_url.startswith("https://"):
        return post_id_or_url
    activity_id = _activity_id(_post_url(post_id_or_url))
    if not activity_id or not comment_id:
        raise ValueError("Expected a post id/URL plus comment id, or a comment URL")
    return (
        f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}/"
        f"?dashCommentUrn=urn%3Ali%3Afsd_comment%3A%28{comment_id}%2Curn%3Ali%3Aactivity%3A{activity_id}%29"
    )


def _profile_activity_url(handle: str, *, page: int = 1) -> str:
    public_id = url_to_public_id(handle) if "/" in handle else handle
    if not public_id:
        raise ValueError(f"Could not resolve a public identifier from {handle!r}")
    params = {"page": str(page)} if page > 1 else {}
    suffix = "recent-activity/all/"
    url = public_id_to_url(public_id) + suffix
    return f"{url}?{urlencode(params)}" if params else url


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


def _first_int(patterns: list[str], text: str) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def _engagement_from_text(text: str) -> dict:
    reactions = _first_int([
        r"(\d[\d,]*)\s+reaction",
        r"(\d[\d,]*)\s+(?:like|likes)",
    ], text)
    if reactions is None:
        match = re.search(r"\band\s+(\d[\d,]*)\s+others?\s+reacted", text, flags=re.IGNORECASE)
        reactions = int(match.group(1).replace(",", "")) + 1 if match else None
    if reactions is None:
        lines = _text_lines(text)
        for index, line in enumerate(lines[:-1]):
            if line.replace(",", "").isdigit() and re.search(r"\band\s+\d[\d,]*\s+others?", lines[index + 1], flags=re.IGNORECASE):
                reactions = int(line.replace(",", ""))
                break
    return {
        "reactions": reactions,
        "comments": _first_int([r"(\d[\d,]*)\s+comment"], text),
        "reposts": _first_int([r"(\d[\d,]*)\s+repost", r"(\d[\d,]*)\s+share"], text),
    }


def _author_from_lines(lines: list[str]) -> str | None:
    skip = {"Follow", "Following", "Connect", "1st", "2nd", "3rd"}
    for line in lines[:8]:
        if line in skip or line.startswith(("Follow ", "Connect ", "Feed post number")):
            continue
        if len(line) <= 120:
            return line
    return None


def _content_from_lines(lines: list[str]) -> str | None:
    stop_words = {
        "Like",
        "Comment",
        "Repost",
        "Send",
        "Share",
        "Follow",
        "Connect",
        "Show more",
        "Show less",
    }
    start = 1
    for index, line in enumerate(lines):
        if "Visible to" in line or line == "Feed post" or re.search(r"\b\d+[smhdwoyr]o\b", line):
            start = index + 1
            break

    body = []
    footer = {
        "About",
        "Accessibility",
        "Help Center",
        "Privacy & Terms",
        "Ad Choices",
        "Advertising",
        "Business Services",
        "Get the LinkedIn app",
        "More",
    }
    visible_lines = lines[start:]
    for index, line in enumerate(visible_lines):
        lower = line.lower()
        if line in footer or line.endswith("© 2026"):
            break
        if line == "View analytics" or line.endswith(" impressions"):
            break
        if " reacted" in lower or re.search(r"\band\s+\d[\d,]*\s+others?", line, flags=re.IGNORECASE):
            break
        if line.replace(",", "").isdigit() and index + 1 < len(visible_lines):
            if re.search(r"\band\s+\d[\d,]*\s+others?", visible_lines[index + 1], flags=re.IGNORECASE):
                break
        if line.startswith("•") or re.fullmatch(r"\d+[smhdwoyr]o\s*•?", line):
            continue
        if line in stop_words or lower.endswith("reactions") or lower.endswith("comments") or lower.endswith("reposts"):
            continue
        if line.startswith("Profile viewers") or line.startswith("Post impressions"):
            continue
        if re.search(r"^\d[\d,]*\s+(reaction|comment|repost|share|like)", line, flags=re.IGNORECASE):
            continue
        body.append(line)
    return "\n".join(body).strip() or None


def _post_from_locator(page, locator) -> dict:
    text = locator.inner_text().strip()
    lines = _text_lines(text)
    attrs = [locator.get_attribute(name) for name in ("data-urn", "data-id", "id")]
    hrefs = [link.get_attribute("href") for link in locator.locator('a[href*="/feed/update/"]').all()]
    activity_id = next((_activity_id(value) for value in attrs + hrefs if _activity_id(value)), None)
    url = None
    if hrefs:
        url = _clean_url(page.url, hrefs[0])
    elif activity_id:
        url = f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}/"

    return {
        "activity_id": activity_id,
        "url": url,
        "author": _author_from_lines(lines),
        "content": _content_from_lines(lines),
        "engagement": _engagement_from_text(text),
    }


def _visible_posts(page, *, limit: int) -> list[dict]:
    posts, seen = [], set()
    for locator in page.locator(SELECTORS["post"]).all():
        post = _post_from_locator(page, locator)
        if not post.get("activity_id"):
            continue
        key = post.get("activity_id") or post.get("url") or post.get("content")
        if not key or key in seen:
            continue
        seen.add(key)
        posts.append(post)
        if len(posts) >= limit:
            break
    return posts


def profile_posts(session: "LinkedInSession", handle: str, *, page: int = 1, limit: int = 10) -> dict:
    """Return visible recent posts/activity for a member profile without engaging."""
    session.ensure_browser()
    url = _profile_activity_url(handle, page=page)
    goto_page(
        session,
        action=lambda: session.page.goto(url, wait_until="domcontentloaded"),
        expected_url_pattern="/recent-activity/",
        error_message="Failed to open profile activity",
    )
    public_id = url_to_public_id(handle) if "/" in handle else handle
    return {"public_identifier": public_id, "page": page, "posts": _visible_posts(session.page, limit=limit)}


def show_post(session: "LinkedInSession", post_id_or_url: str) -> dict:
    """Return visible content and aggregate engagement for one post without engaging."""
    session.ensure_browser()
    url = _post_url(post_id_or_url)
    goto_page(
        session,
        action=lambda: session.page.goto(url, wait_until="domcontentloaded"),
        expected_url_pattern="/feed/update/",
        error_message="Failed to open post",
    )
    posts = _visible_posts(session.page, limit=1)
    if posts:
        return posts[0]
    text = session.page.locator("main").first.inner_text().strip() if session.page.locator("main").count() else session.page.locator("body").inner_text().strip()
    return {
        "activity_id": _activity_id(session.page.url) or _activity_id(post_id_or_url),
        "url": _clean_url(session.page.url, session.page.url),
        "author": _author_from_lines(_text_lines(text)),
        "content": _content_from_lines(_text_lines(text)),
        "engagement": _engagement_from_text(text),
    }


def post_engagement(session: "LinkedInSession", post_id_or_url: str) -> dict:
    """Return read-only engagement counts and visible comments for one post."""
    post = show_post(session, post_id_or_url)
    comments = []
    for locator in session.page.locator(SELECTORS["comment"]).all():
        lines = _text_lines(locator.inner_text())
        if not lines:
            continue
        comments.append({"author": _author_from_lines(lines), "text": "\n".join(lines[1:]).strip() or None})
    return {**post, "comments": comments}


def _comment_from_anchor(anchor, *, known_comment_id: str | None = None) -> dict | None:
    href = anchor.get_attribute("href") or ""
    author = _text_lines(anchor.inner_text())
    author_name = author[0] if author else None
    if not author_name:
        return None

    container = None
    for depth in range(3, 8):
        candidate = anchor.locator("xpath=" + "/.." * depth)
        if candidate.count() == 0 or not candidate.is_visible():
            continue
        text = candidate.inner_text()
        if author_name in text and any(token in text for token in ("Reply", "reaction", "impression", "good article", "Thanks")):
            container = candidate
            break
    if container is None:
        return None

    has_comment_action = False
    for button in container.locator("button").all():
        aria = button.get_attribute("aria-label") or ""
        label = " ".join((button.inner_text() or "").split())
        if aria == "Reply" or label == "Reply" or "comment" in aria.lower():
            has_comment_action = True
            break
    if not has_comment_action:
        return None

    lines = _text_lines(container.inner_text())
    content_lines = []
    start = False
    for line in lines:
        if line == author_name or line.startswith(author_name + " ") or "•" in line or re.fullmatch(r"\d+[smhdwoyr]", line):
            start = True
            continue
        if not start:
            continue
        if line in {"Reply", "Like", "Open reactions menu"} or line.endswith("impressions") or re.fullmatch(r"\d+", line):
            break
        if re.search(r"^\d+\s+reaction", line, flags=re.IGNORECASE):
            break
        content_lines.append(line)

    text = "\n".join(content_lines).strip() or None
    if not text:
        return None
    return {
        "comment_id": known_comment_id or _comment_id(href),
        "author": author_name,
        "profile_url": href or None,
        "text": text,
        "reactions": _first_int([r"(\d[\d,]*)\s+reaction"], container.inner_text()),
    }


def list_post_comments(session: "LinkedInSession", post_id_or_url: str, *, limit: int = 20) -> dict:
    """Return visible comments for a post without engaging."""
    post = show_post(session, post_id_or_url)
    known_comment_id = _comment_id(post_id_or_url)
    comments, seen = [], set()
    for anchor in session.page.locator('a[href*="/in/"]').all():
        comment = _comment_from_anchor(anchor, known_comment_id=known_comment_id)
        if not comment:
            continue
        key = (comment.get("author"), comment.get("text"))
        if key in seen:
            continue
        seen.add(key)
        comments.append(comment)
        if len(comments) >= limit:
            break
    return {"activity_id": post.get("activity_id"), "url": post.get("url"), "comments": comments}


def _first_visible(page, selector: str, *, timeout_ms: int = 8_000):
    deadline = time.monotonic() + timeout_ms / 1000
    locator = page.locator(selector)
    while time.monotonic() < deadline:
        for index in range(locator.count()):
            item = locator.nth(index)
            if item.is_visible():
                return item
        time.sleep(0.25)
    locator.first.wait_for(state="visible", timeout=1)
    return locator.first


def _click_first(page, selector: str, *, timeout_ms: int = 8_000) -> bool:
    try:
        _first_visible(page, selector, timeout_ms=timeout_ms).click()
        return True
    except PlaywrightTimeoutError:
        return False


def _click_dialog_button(session, labels: list[str], *, timeout_ms: int = 8_000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        dialogs = session.page.locator(SELECTORS["composer"]).all()
        for dialog in reversed(dialogs):
            if not dialog.is_visible():
                continue
            for button in dialog.locator("button").all():
                text = " ".join((button.inner_text() or "").split())
                aria = button.get_attribute("aria-label") or ""
                if not button.is_visible() or not button.is_enabled():
                    continue
                if text in labels or aria in labels:
                    button.click(force=True)
                    return True
        time.sleep(0.25)
    return False


def _open_composer(session):
    session.ensure_browser()
    goto_page(
        session,
        action=lambda: session.page.goto("https://www.linkedin.com/feed/?shareActive=true", wait_until="domcontentloaded"),
        expected_url_pattern="/feed/",
        error_message="Failed to open feed",
    )
    return _first_visible(session.page, SELECTORS["composer"])


def _visible_composer_text(session) -> str:
    chunks = []
    for dialog in session.page.locator(SELECTORS["composer"]).all():
        if dialog.is_visible():
            chunks.append(dialog.inner_text())
    return "\n".join(chunks)


def _set_text(session, text: str) -> None:
    editor = _first_visible(session.page, SELECTORS["editor"])
    editor.click()
    session.page.keyboard.insert_text(text)
    session.wait(0.5, 1.0)
    if text in _visible_composer_text(session):
        return
    editor.evaluate(
        """(element, value) => {
            element.textContent = value;
            element.dispatchEvent(new InputEvent("input", {
                bubbles: true,
                inputType: "insertText",
                data: value,
            }));
        }""",
        text,
    )
    session.wait(0.5, 1.0)
    if text not in _visible_composer_text(session):
        raise RuntimeError("Could not enter text into LinkedIn post composer")


def _existing_paths(paths: list[str]) -> list[str]:
    resolved = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(str(path))
        resolved.append(str(path))
    return resolved


def _upload_files(session, button_selector: str, files: list[str]) -> bool:
    if not files:
        return False
    paths = _existing_paths(files)
    page = session.page
    if page.locator(button_selector).count() == 0 or not any(item.is_visible() for item in page.locator(button_selector).all()):
        _click_first(page, SELECTORS["more_button"], timeout_ms=4_000)
        session.wait(0.5, 1.0)

    try:
        with page.expect_file_chooser(timeout=5_000) as chooser_info:
            if not _click_first(page, button_selector):
                raise RuntimeError("Could not open LinkedIn upload controls")
        chooser_info.value.set_files(paths)
        session.wait(1.0, 2.0)
        return _finish_upload_dialog(session, paths)
    except PlaywrightTimeoutError:
        pass

    session.wait(0.5, 1.0)
    file_inputs = page.locator('div[role="dialog"] input[type="file"]')
    if file_inputs.count() > 0:
        file_inputs.last.set_input_files(paths)
    else:
        with page.expect_file_chooser() as chooser_info:
            upload = page.locator('div[role="dialog"] button:has-text("Upload from computer"), div[role="dialog"] button:has-text("Choose file")')
            if upload.count() > 0 and any(item.is_visible() for item in upload.all()):
                upload.first.click()
            else:
                raise RuntimeError("Could not find LinkedIn file input")
        chooser_info.value.set_files(paths)
    session.wait(1.0, 2.0)
    return _finish_upload_dialog(session, paths)


def _finish_upload_dialog(session, paths: list[str]) -> bool:
    page = session.page
    title_inputs = page.locator('div[role="dialog"] input[type="text"]')
    if title_inputs.count() > 0 and any(item.is_visible() for item in title_inputs.all()):
        title = Path(paths[0]).stem.replace("-", " ").replace("_", " ")[:100]
        for index in range(title_inputs.count()):
            item = title_inputs.nth(index)
            if item.is_visible():
                item.fill(title)
                break
        session.wait(0.5, 1.0)
    _click_dialog_button(session, ["Next", "Done"], timeout_ms=6_000)
    session.wait(1.0, 2.0)
    return True


def _add_poll(session, question: str | None, options: list[str] | None) -> bool:
    if not options:
        return False
    if len(options) < 2:
        raise ValueError("A poll requires at least two options")
    if session.page.locator(SELECTORS["poll_button"]).count() == 0 or not any(item.is_visible() for item in session.page.locator(SELECTORS["poll_button"]).all()):
        _click_first(session.page, SELECTORS["more_button"], timeout_ms=4_000)
        session.wait(0.5, 1.0)
    if not _click_first(session.page, SELECTORS["poll_button"]):
        raise RuntimeError("Could not open LinkedIn poll composer")

    inputs = session.page.locator('div[role="dialog"] input, div[role="dialog"] textarea')
    values = ([question] if question else []) + options
    if inputs.count() == 0:
        raise RuntimeError("Could not find LinkedIn poll fields")
    for raw_index, value in enumerate(values):
        index = min(raw_index, inputs.count() - 1)
        if index >= 0:
            inputs.nth(index).fill(value)
    session.wait(1.0, 2.0)
    if not _click_dialog_button(session, ["Done"], timeout_ms=6_000):
        raise RuntimeError("Could not confirm LinkedIn poll composer")
    session.wait(1.0, 2.0)
    return True


def _schedule_time(session, scheduled_at: str) -> None:
    when = datetime.fromisoformat(scheduled_at)
    if not _click_first(session.page, SELECTORS["schedule_button"]):
        raise RuntimeError("Could not open LinkedIn schedule controls")

    dialog = _first_visible(session.page, SELECTORS["composer"])
    fields = dialog.locator('input, select')
    values = [when.strftime("%Y-%m-%d"), when.strftime("%I:%M %p")]
    if fields.count() == 0:
        raise RuntimeError("Could not find LinkedIn schedule fields")
    for index, value in enumerate(values):
        if index >= fields.count():
            break
        fields.nth(index).fill(value)
    if not _click_first(session.page, SELECTORS["confirm_schedule"]):
        raise RuntimeError("Could not confirm LinkedIn schedule controls")
    session.wait(1.0, 2.0)


def create_post(
    session: "LinkedInSession",
    text: str,
    *,
    images: list[str] | None = None,
    documents: list[str] | None = None,
    poll_question: str | None = None,
    poll_options: list[str] | None = None,
) -> dict:
    """Create a LinkedIn post with optional images, documents, or poll."""
    if not text.strip():
        raise ValueError("Post text cannot be empty")
    if poll_options and (images or documents):
        raise ValueError("LinkedIn posts cannot combine polls with image/document uploads")

    _open_composer(session)
    _set_text(session, text)
    uploaded_images = _upload_files(session, SELECTORS["media_button"], images or [])
    uploaded_documents = _upload_files(session, SELECTORS["document_button"], documents or [])
    added_poll = _add_poll(session, poll_question or text, poll_options)

    if not _click_dialog_button(session, ["Post"]):
        raise RuntimeError("Could not find LinkedIn post submit button")
    session.wait(2.0, 4.0)
    return {
        "posted": True,
        "text": text,
        "images": images or [],
        "documents": documents or [],
        "poll": {"question": poll_question, "options": poll_options or []} if added_poll else None,
        "uploaded_images": uploaded_images,
        "uploaded_documents": uploaded_documents,
    }


def draft_post(session: "LinkedInSession", text: str) -> dict:
    """Write a post, close the composer, and save LinkedIn's offered draft."""
    if not text.strip():
        raise ValueError("Draft text cannot be empty")
    _open_composer(session)
    _set_text(session, text)
    if not _click_first(session.page, SELECTORS["close_composer"]):
        raise RuntimeError("Could not close LinkedIn post composer")
    saved = _click_first(session.page, SELECTORS["save_draft"], timeout_ms=5_000)
    session.wait(1.0, 2.0)
    return {"drafted": saved, "text": text}


def schedule_post(session: "LinkedInSession", text: str, scheduled_at: str) -> dict:
    """Schedule a text post for an ISO local datetime accepted by LinkedIn's composer."""
    if not text.strip():
        raise ValueError("Post text cannot be empty")
    _open_composer(session)
    _set_text(session, text)
    _schedule_time(session, scheduled_at)
    if not _click_dialog_button(session, ["Post"]):
        raise RuntimeError("Could not find LinkedIn schedule submit button")
    session.wait(2.0, 4.0)
    return {"scheduled": True, "scheduled_at": scheduled_at, "text": text}


def delete_post(session: "LinkedInSession", post_id_or_url: str) -> dict:
    """Delete a LinkedIn post by opening its detail page and confirming delete."""
    post = show_post(session, post_id_or_url)
    if not _click_first(session.page, SELECTORS["overflow"]):
        raise RuntimeError("Could not open LinkedIn post action menu")
    if not _click_first(session.page, SELECTORS["delete_menu"]):
        raise RuntimeError("Could not find LinkedIn post delete action")
    if not _click_first(session.page, SELECTORS["confirm_delete"]):
        raise RuntimeError("Could not confirm LinkedIn post deletion")
    session.wait(2.0, 4.0)
    return {"deleted": True, "activity_id": post.get("activity_id"), "url": post.get("url")}


def _open_comment(session: "LinkedInSession", post_id_or_url: str, comment_id: str | None = None) -> dict:
    session.ensure_browser()
    url = _comment_url(post_id_or_url, comment_id)
    goto_page(
        session,
        action=lambda: session.page.goto(url, wait_until="domcontentloaded"),
        expected_url_pattern="/feed/update/",
        error_message="Failed to open post comment",
    )
    return {
        "activity_id": _activity_id(session.page.url) or _activity_id(url),
        "comment_id": _comment_id(session.page.url) or _comment_id(url) or comment_id,
        "url": _clean_url(session.page.url, session.page.url),
    }


def _buttons(session) -> list:
    return [button for button in session.page.locator("button").all()]


def _comment_action_button(session, *, author: str | None, action_label: str):
    buttons = _buttons(session)
    start = 0
    if author:
        expected = f"for {author}".lower()
        for index, button in enumerate(buttons):
            aria = (button.get_attribute("aria-label") or "").lower()
            if expected in aria and "comment" in aria:
                start = index + 1
                break
        else:
            raise RuntimeError(f"Could not find visible comment actions for {author!r}")

    label = action_label.lower()
    for button in buttons[start:]:
        text = " ".join((button.inner_text() or "").split()).lower()
        aria = (button.get_attribute("aria-label") or "").lower()
        if label in text or label in aria:
            return button
    raise RuntimeError(f"Could not find comment action {action_label!r}")


def _select_reaction(session, reaction: str) -> None:
    if reaction not in REACTIONS:
        raise ValueError(f"Unsupported reaction {reaction!r}; expected one of {sorted(REACTIONS)}")
    label = reaction.capitalize()
    option = session.page.locator(f'button[aria-label="{label}"], button:has-text("{label}")')
    for index in reversed(range(option.count())):
        button = option.nth(index)
        if button.is_visible() and button.is_enabled():
            button.click(force=True)
            session.wait(1.0, 2.0)
            return
    raise RuntimeError(f"Could not select LinkedIn {label} reaction")


def _reaction_option_visible(session) -> bool:
    for reaction in REACTIONS:
        label = reaction.capitalize()
        options = session.page.locator(f'button[aria-label="{label}"], button:has-text("{label}")')
        if any(option.is_visible() for option in options.all()):
            return True
    return False


def _open_reaction_menu(session, button) -> None:
    if button.is_visible():
        try:
            button.hover(force=True)
            session.wait(0.8, 1.2)
            if _reaction_option_visible(session):
                return
        except Exception:
            pass
        try:
            button.click(force=True)
            return
        except Exception:
            pass
    button.evaluate("element => element.click()")


def _fill_visible_editor(session, text: str) -> None:
    editors = [editor for editor in session.page.locator(SELECTORS["comment_editor"]).all() if editor.is_visible()]
    if not editors:
        raise RuntimeError("Could not find LinkedIn comment editor")
    focused = [editor for editor in editors if "focused" in (editor.get_attribute("class") or "").lower()]
    editor = (focused or editors)[-1]
    editor.click(force=True)
    session.page.keyboard.insert_text(text)
    session.wait(0.5, 1.0)
    if text in session.page.locator("body").inner_text():
        return
    if text in _visible_composer_text(session):
        return
    raise RuntimeError("Could not enter text into LinkedIn comment editor")


def reply_to_comment(
    session: "LinkedInSession",
    post_id_or_url: str,
    *,
    text: str,
    comment_id: str | None = None,
    author: str | None = None,
) -> dict:
    """Reply to a visible comment on a post."""
    if not text.strip():
        raise ValueError("Reply text cannot be empty")
    target = _open_comment(session, post_id_or_url, comment_id)
    reply = _comment_action_button(session, author=author, action_label="Reply")
    reply.click(force=True)
    session.wait(0.5, 1.0)
    _fill_visible_editor(session, text)
    submit = session.page.locator('button:has-text("Reply"), button[aria-label*="Reply" i], button:has-text("Post"), button[aria-label*="Post" i]')
    for index in reversed(range(submit.count())):
        button = submit.nth(index)
        button_text = " ".join((button.inner_text() or "").split())
        if button.is_visible() and button.is_enabled() and button_text in {"Reply", "Post"}:
            button.click(force=True)
            break
    else:
        raise RuntimeError("Could not submit LinkedIn comment reply")
    session.wait(2.0, 4.0)
    return {**target, "author": author, "replied": True, "text": text}


def react_to_post(session: "LinkedInSession", post_id_or_url: str, *, reaction: str = "like") -> dict:
    """React to a post."""
    post = show_post(session, post_id_or_url)
    like = session.page.locator('button[aria-label*="Reaction button state" i], button:has-text("Like")')
    for index in range(like.count()):
        button = like.nth(index)
        if button.is_visible() and button.is_enabled():
            _open_reaction_menu(session, button)
            session.wait(0.5, 1.0)
            _select_reaction(session, reaction)
            return {"activity_id": post.get("activity_id"), "url": post.get("url"), "reaction": reaction, "reacted": True}
    raise RuntimeError("Could not find LinkedIn post reaction button")


def react_to_comment(
    session: "LinkedInSession",
    post_id_or_url: str,
    *,
    comment_id: str | None = None,
    author: str | None = None,
    reaction: str = "like",
) -> dict:
    """React to a visible comment."""
    target = _open_comment(session, post_id_or_url, comment_id)
    button = _comment_action_button(session, author=author, action_label="Open reactions menu")
    _open_reaction_menu(session, button)
    session.wait(1.0, 2.0)
    _select_reaction(session, reaction)
    return {**target, "author": author, "reaction": reaction, "reacted": True}
