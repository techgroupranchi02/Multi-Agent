"""
Aikyam Multi-Agent Pipeline — GitHub Integration
Branch management, commits, and PR creation via PyGithub.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from src.config import get_settings

logger = logging.getLogger(__name__)


class GitHubClient:
    """Wrapper around PyGithub for repo operations."""

    def __init__(self):
        self.settings = get_settings()
        self._github = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize GitHub client."""
        if not self.settings.github_token:
            logger.warning("GitHub token not configured — GitHub integration disabled")
            return False

        try:
            from github import Github
            self._github = Github(self.settings.github_token)
            # Test connection
            self._github.get_user().login
            self._initialized = True
            logger.info("✓ GitHub client initialized (org: %s)", self.settings.github_org)
            return True
        except ImportError:
            logger.warning("PyGithub not installed — run: pip install PyGithub")
            return False
        except Exception as e:
            logger.error("Failed to initialize GitHub: %s", e)
            return False

    def create_repo(self, name: str, description: str = "", private: bool = True) -> Optional[dict[str, Any]]:
        """Create a new GitHub repository under the configured org."""
        if not self._initialized:
            return None

        try:
            org = self._github.get_organization(self.settings.github_org)
            repo = org.create_repo(
                name=name,
                description=description,
                private=private,
                auto_init=True,
            )
            logger.info("Created GitHub repo: %s/%s", self.settings.github_org, name)
            return {
                "full_name": repo.full_name,
                "html_url": repo.html_url,
                "clone_url": repo.clone_url,
                "ssh_url": repo.ssh_url,
            }
        except Exception as e:
            logger.error("Failed to create GitHub repo: %s", e)
            return None

    def create_branch(self, repo_name: str, branch_name: str, from_branch: Optional[str] = None) -> bool:
        """Create a new branch in the repository."""
        if not self._initialized:
            return False

        try:
            repo = self._github.get_repo(f"{self.settings.github_org}/{repo_name}")
            source_branch = from_branch or self.settings.github_default_branch
            source_ref = repo.get_branch(source_branch)
            repo.create_git_ref(
                ref=f"refs/heads/{branch_name}",
                sha=source_ref.commit.sha,
            )
            logger.info("Created branch '%s' in %s", branch_name, repo_name)
            return True
        except Exception as e:
            logger.error("Failed to create branch '%s': %s", branch_name, e)
            return False

    def commit_file(
        self,
        repo_name: str,
        branch: str,
        file_path: str,
        content: str,
        commit_message: str,
    ) -> bool:
        """Create or update a file in the repo."""
        if not self._initialized:
            return False

        try:
            repo = self._github.get_repo(f"{self.settings.github_org}/{repo_name}")
            try:
                existing = repo.get_contents(file_path, ref=branch)
                repo.update_file(
                    path=file_path,
                    message=commit_message,
                    content=content,
                    sha=existing.sha,
                    branch=branch,
                )
            except Exception:
                repo.create_file(
                    path=file_path,
                    message=commit_message,
                    content=content,
                    branch=branch,
                )
            logger.info("Committed %s to %s/%s", file_path, repo_name, branch)
            return True
        except Exception as e:
            logger.error("Failed to commit %s: %s", file_path, e)
            return False

    def create_pull_request(
        self,
        repo_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Create a pull request."""
        if not self._initialized:
            return None

        try:
            repo = self._github.get_repo(f"{self.settings.github_org}/{repo_name}")
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch or self.settings.github_default_branch,
            )
            logger.info("Created PR #%d: %s", pr.number, title)
            return {
                "number": pr.number,
                "html_url": pr.html_url,
                "title": pr.title,
            }
        except Exception as e:
            logger.error("Failed to create PR: %s", e)
            return None

    @staticmethod
    def slugify(text: str) -> str:
        """Convert text to a branch-name-safe slug."""
        slug = text.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s]+", "-", slug)
        return slug[:60]


# ── Singleton ──
_github_client: Optional[GitHubClient] = None


def get_github_client() -> GitHubClient:
    global _github_client
    if _github_client is None:
        _github_client = GitHubClient()
    return _github_client
