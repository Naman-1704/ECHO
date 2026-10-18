def source_url(source: str, source_id: str) -> str | None:
    """
    Deep link back to the original item, so every citation can be verified in one click.
    Gmail accepts a message id after '#all/'; Drive's open?id= redirects any file type to
    its proper viewer. Both rely on the viewer being signed in to the same Google account.
    """
    if not source_id:
        return None
    if source == "gmail":
        return f"https://mail.google.com/mail/u/0/#all/{source_id}"
    if source == "drive":
        return f"https://drive.google.com/open?id={source_id}"
    return None
