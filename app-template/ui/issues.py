"""Issues nav screen - a thin wrapper around the reusable issue board
(ui/issue_board.py). Reuse build_issue_board() directly elsewhere for a
narrower scope rather than forking this file."""

import issues as iss
from ui.issue_board import build_issue_board


def build(ctx, **kwargs) -> None:
    build_issue_board(ctx.content, ctx, scope=iss.DEFAULT_SCOPE, title="Issues")
