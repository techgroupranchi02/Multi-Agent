"""
Aikyam Multi-Agent Pipeline — Google Docs Integration
Creates and shares Google Docs for artifacts (PRD, PDD, open_questions, etc.)
Uses a Service Account for authentication.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)


class GoogleDocsClient:
    """
    Creates Google Docs from artifact content and shares them.
    Uses Google Service Account (JSON key) for auth.
    """

    def __init__(self):
        self._docs_service: Any = None
        self._drive_service: Any = None
        self._initialized: bool = False
        self._settings: Any = None
        self._auth_mode: Optional[str] = None  # "oauth" or "service_account"

    def initialize(self) -> bool:
        """
        Initialize Google APIs.
        Tries OAuth2 user credentials first (has Drive storage),
        falls back to service account credentials.
        """
        try:
            from src.config import get_settings
            self._settings = get_settings()
            backend_dir = Path(__file__).resolve().parent.parent.parent

            # ── Try OAuth2 user credentials first ──
            oauth_token_path = backend_dir / "google_oauth_token.json"
            if oauth_token_path.is_file():
                if self._init_oauth(oauth_token_path, backend_dir):
                    return True
                logger.warning("OAuth2 token expired/invalid — falling back to service account")

            # ── Fall back to service account ──
            key_path = self._settings.google_service_account_key_path
            if not key_path:
                logger.warning("Google service account key path not configured")
                return False

            abs_key_path = (backend_dir / key_path).resolve()
            if not abs_key_path.is_file():
                logger.warning("Google service account key not found: %s", abs_key_path)
                return False

            return self._init_service_account(abs_key_path)

        except ImportError:
            logger.warning(
                "google-api-python-client not installed — run: pip install google-api-python-client google-auth"
            )
            return False
        except Exception as e:
            logger.error("Failed to initialize Google Docs client: %s", e)
            return False

    def _init_oauth(self, token_path: Path, backend_dir: Path) -> bool:
        """Initialize using OAuth2 user credentials (preferred — has Drive storage)."""
        try:
            import json
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            with open(token_path, "r") as f:
                token_data = json.load(f)

            credentials = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes"),
            )

            # Test if credentials are valid by refreshing
            if credentials.expired or not credentials.valid:
                from google.auth.transport.requests import Request
                credentials.refresh(Request())

                # Save refreshed token back
                token_data["token"] = credentials.token
                with open(token_path, "w") as f:
                    json.dump(token_data, f, indent=2)

            self._docs_service = build("docs", "v1", credentials=credentials, cache_discovery=False)
            self._drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            self._initialized = True
            self._auth_mode = "oauth"
            logger.info("✓ Google Docs client initialized (OAuth2 user credentials)")
            return True

        except Exception as e:
            logger.warning("OAuth2 initialization failed: %s", e)
            return False

    def _init_service_account(self, abs_key_path: Path) -> bool:
        """Initialize using service account credentials (fallback)."""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        scopes = [
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/drive.file",
        ]

        credentials = service_account.Credentials.from_service_account_file(
            str(abs_key_path), scopes=scopes
        )

        self._docs_service = build("docs", "v1", credentials=credentials, cache_discovery=False)
        self._drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self._initialized = True
        self._auth_mode = "service_account"
        logger.info("✓ Google Docs client initialized (service account: %s)", abs_key_path.name)
        logger.warning(
            "⚠ Using service account — may fail to create docs due to storage quota. "
            "Run 'python setup_google_oauth.py' for OAuth2 setup."
        )
        return True

    def create_doc(
        self,
        title: str,
        content: str,
        project_name: str = "",
        artifact_type: str = "",
    ) -> Optional[str]:
        """
        Create a Google Doc with the given title and markdown content.
        Returns the Google Doc URL, or None on failure.

        Strategy:
        1. Try Docs API documents().create() — Google-native docs don't count against
           Drive storage quota for service accounts.
        2. Fall back to Drive API files().create() with configured folder.
        3. Fall back to Drive API files().create() without folder.
        """
        if not self._initialized or self._docs_service is None or self._drive_service is None:
            if not self.initialize():
                return None

        doc_title = f"[Aikyam] {project_name} — {title}" if project_name else f"[Aikyam] {title}"
        doc_id = None
        doc_url = None

        # ── Strategy 1: Docs API (preferred — no storage quota issues) ──
        try:
            logger.info("Creating Google Doc via Docs API: %s", doc_title)
            doc = self._docs_service.documents().create(
                body={"title": doc_title}
            ).execute()
            doc_id = doc["documentId"]
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            logger.info("✓ Created via Docs API: %s (id: %s)", doc_title, doc_id)

            # Move to target folder if configured
            if self._settings and self._settings.google_docs_folder_id:
                try:
                    self._drive_service.files().update(
                        fileId=doc_id,
                        addParents=self._settings.google_docs_folder_id,
                        fields="id,parents",
                        supportsAllDrives=True,
                    ).execute()
                    logger.info("Moved doc to folder: %s", self._settings.google_docs_folder_id)
                except Exception as move_err:
                    logger.warning("Could not move doc to folder (doc still accessible): %s", move_err)

        except Exception as docs_api_err:
            err_str = str(docs_api_err)
            logger.warning("Docs API create failed: %s — trying Drive API fallback", err_str)

            # ── Strategy 2: Drive API with folder ──
            if self._settings and self._settings.google_docs_folder_id:
                try:
                    file = self._drive_service.files().create(
                        body={
                            "name": doc_title,
                            "mimeType": "application/vnd.google-apps.document",
                            "parents": [self._settings.google_docs_folder_id],
                        },
                        fields="id",
                        supportsAllDrives=True,
                    ).execute()
                    doc_id = file["id"]
                    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
                    logger.info("✓ Created via Drive API (with folder): %s", doc_id)
                except Exception as drive_err:
                    logger.warning("Drive API (with folder) failed: %s", drive_err)

            # ── Strategy 3: Drive API without folder ──
            if not doc_id:
                try:
                    file = self._drive_service.files().create(
                        body={
                            "name": doc_title,
                            "mimeType": "application/vnd.google-apps.document",
                        },
                        fields="id",
                        supportsAllDrives=True,
                    ).execute()
                    doc_id = file["id"]
                    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
                    logger.info("✓ Created via Drive API (no folder): %s", doc_id)
                except Exception as final_err:
                    # All strategies failed — log comprehensive error
                    self._log_creation_failure(docs_api_err, final_err)
                    return None

        # ── Insert content ──
        if doc_id:
            try:
                requests = self._markdown_to_docs_requests(content)
                if requests:
                    self._docs_service.documents().batchUpdate(
                        documentId=doc_id,
                        body={"requests": requests},
                    ).execute()
                    logger.info("Inserted content into doc %s", doc_id)
            except Exception as content_err:
                logger.warning(
                    "Could not insert formatted content (doc exists but may be empty): %s",
                    content_err,
                )

            # Share with configured email
            if self._settings and self._settings.google_docs_share_email:
                self._share_doc(doc_id, self._settings.google_docs_share_email)

        return doc_url

    def _log_creation_failure(self, docs_err: Exception, drive_err: Exception) -> None:
        """Log a comprehensive error message when all doc creation strategies fail."""
        docs_msg = str(docs_err)
        drive_msg = str(drive_err)

        # Extract project ID for actionable links
        proj_id = "your-project"
        try:
            import json
            backend_dir = Path(__file__).resolve().parent.parent.parent
            key_path = (backend_dir / self._settings.google_service_account_key_path).resolve()
            with open(key_path, "r") as f:
                proj_id = json.load(f).get("project_id", proj_id)
        except Exception:
            pass

        if "does not have permission" in docs_msg or ("403" in docs_msg and "permission" in docs_msg.lower()):
            logger.error(
                "ALL Google Doc creation methods failed.\n"
                "━━━ Docs API Error: 'The caller does not have permission' ━━━\n"
                "This means the Google Docs API is NOT ENABLED for your project.\n"
                "FIX: Enable it at:\n"
                "  https://console.cloud.google.com/apis/library/docs.googleapis.com?project=%s\n",
                proj_id,
            )
        
        if "storageQuotaExceeded" in drive_msg or "storage quota" in drive_msg.lower():
            logger.error(
                "━━━ Drive API Error: 'Storage quota exceeded' ━━━\n"
                "Service accounts have NO Drive storage. You MUST either:\n"
                "  1. Enable the Google Docs API (preferred fix — see link above)\n"
                "  2. Use a Shared Drive (Team Drive) for the folder ID\n"
                "  3. Set up domain-wide delegation to impersonate a real user\n"
                "More info: https://developers.google.com/drive/api/guides/about-shareddrives"
            )
        elif "403" in drive_msg:
            logger.error(
                "━━━ Drive API Error: Permission denied (403) ━━━\n"
                "Enable Drive API at:\n"
                "  https://console.cloud.google.com/apis/library/drive.googleapis.com?project=%s",
                proj_id,
            )
        else:
            logger.error(
                "ALL Google Doc creation methods failed.\n"
                "  Docs API: %s\n  Drive API: %s",
                docs_msg[:200], drive_msg[:200],
            )

    def create_or_update_tab(
        self,
        project_id: str,
        project_name: str,
        tab_title: str,
        content: str,
        workspace_path: str,
    ) -> Optional[str]:
        """
        Creates or updates a tab in the project's single Google Doc.
        Returns the specific tab URL: https://docs.google.com/document/d/[DOC_ID]/edit#tab=[TAB_ID]
        """
        if not self._initialized or self._docs_service is None or self._drive_service is None:
            if not self.initialize():
                return None

        # Step 1: Find or create the project's Google Doc
        doc_id = None
        doc_id_file = os.path.join(workspace_path, ".state", "project_doc_id.txt")
        if os.path.exists(doc_id_file):
            try:
                with open(doc_id_file, "r") as f:
                    doc_id = f.read().strip()
                # Verify doc still exists
                self._drive_service.files().get(fileId=doc_id, fields="id").execute()
            except Exception as e:
                from googleapiclient.errors import HttpError
                if isinstance(e, HttpError) and e.resp.status == 404:
                    logger.warning("Project Google Doc %s was deleted or not found. Creating a new one.", doc_id)
                    doc_id = None
                else:
                    logger.warning("Google Drive API error verifying doc %s: %s. Keeping existing doc ID.", doc_id, e)

        is_new_doc = False
        if not doc_id:
            # Create a new document
            try:
                doc_title = f"[Aikyam] {project_name}"
                doc = self._docs_service.documents().create(body={"title": doc_title}).execute()
                doc_id = doc["documentId"]
                is_new_doc = True
                logger.info("Created new project Google Doc: %s (id: %s)", doc_title, doc_id)
                
                # Move to target folder if configured
                if self._settings and self._settings.google_docs_folder_id:
                    try:
                        self._drive_service.files().update(
                            fileId=doc_id,
                            addParents=self._settings.google_docs_folder_id,
                            fields="id,parents",
                            supportsAllDrives=True,
                        ).execute()
                        logger.info("Moved project doc to folder: %s", self._settings.google_docs_folder_id)
                    except Exception as move_err:
                        logger.warning("Could not move doc to folder: %s", move_err)

                # Share with user
                if self._settings and self._settings.google_docs_share_email:
                    self._share_doc(doc_id, self._settings.google_docs_share_email)

                # Save doc_id to workspace
                os.makedirs(os.path.dirname(doc_id_file), exist_ok=True)
                with open(doc_id_file, "w") as f:
                    f.write(doc_id)

            except Exception as e:
                logger.error("Failed to create new project doc: %s", e)
                return None

        # Step 2: Ensure the target tab exists and get its tabId
        tab_id = None
        try:
            doc_data = self._docs_service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
            tabs = doc_data.get("tabs", [])
            
            # Find if tab already exists
            for tab in tabs:
                props = tab.get("tabProperties", {})
                if props.get("title") == tab_title:
                    tab_id = props.get("tabId")
                    break

            if not tab_id:
                if is_new_doc and (tab_title == "PRD" or tab_title == "PRD v1") and tabs:
                    # Rename the default first tab to the target title
                    first_tab_id = tabs[0].get("tabProperties", {}).get("tabId")
                    self._docs_service.documents().batchUpdate(
                        documentId=doc_id,
                        body={
                            "requests": [
                                {
                                    "updateDocumentTabProperties": {
                                        "tabProperties": {
                                            "tabId": first_tab_id,
                                            "title": tab_title
                                        },
                                        "fields": "title"
                                    }
                                }
                            ]
                        }
                    ).execute()
                    tab_id = first_tab_id
                    logger.info("Renamed default tab to %s", tab_title)
                else:
                    # Add a new tab at the first position (index 0) so it becomes the default tab
                    reply = self._docs_service.documents().batchUpdate(
                        documentId=doc_id,
                        body={
                            "requests": [
                                {
                                    "addDocumentTab": {
                                        "tabProperties": {
                                            "title": tab_title
                                        },
                                        "insertIndex": 0
                                    }
                                }
                            ]
                        }
                    ).execute()
                    tab_id = reply["replies"][0]["addDocumentTab"]["tabProperties"]["tabId"]
                    logger.info("Created new tab at index 0: %s (%s)", tab_title, tab_id)
        except Exception as e:
            logger.error("Failed to manage tabs in doc %s: %s", doc_id, e)
            return None

        # Step 3: Populate tab content
        try:
            doc_data = self._docs_service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
            # Find the tab's body content to check its length
            tab_body = None
            for t in doc_data.get("tabs", []):
                if t.get("tabProperties", {}).get("tabId") == tab_id:
                    tab_body = t.get("documentTab", {}).get("body", {})
                    break
            
            if tab_body:
                content_elements = tab_body.get("content", [])
                if len(content_elements) > 2: # More than just structural markers
                    end_index = content_elements[-1].get("endIndex")
                    if end_index and end_index > 2:
                        self._docs_service.documents().batchUpdate(
                            documentId=doc_id,
                            body={
                                "requests": [
                                    {
                                        "deleteContentRange": {
                                            "range": {
                                                "tabId": tab_id,
                                                "startIndex": 1,
                                                "endIndex": end_index - 1
                                            }
                                        }
                                    }
                                ]
                            }
                        ).execute()
                        logger.info("Cleared existing content in tab %s", tab_title)

            # Insert new content
            requests = self._markdown_to_docs_requests(content, tab_id)
            if requests:
                self._docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": requests},
                ).execute()
                logger.info("Populated content in tab %s", tab_title)

        except Exception as content_err:
            logger.warning("Could not populate content in tab %s: %s", tab_title, content_err)

        # Return the specific tab URL
        return f"https://docs.google.com/document/d/{doc_id}/edit#tab={tab_id}"

    def _share_doc(self, doc_id: str, email: str) -> None:
        """Share a Google Doc with the specified email address."""
        try:
            self._drive_service.permissions().create(
                fileId=doc_id,
                body={
                    "type": "user",
                    "role": "writer",
                    "emailAddress": email,
                },
                sendNotificationEmail=False,
                supportsAllDrives=True,
            ).execute()
            logger.info("Shared Google Doc %s with %s", doc_id, email)
        except Exception as e:
            logger.warning("Failed to share doc with %s: %s", email, e)

    # ── PRD Versioning Methods ──

    def create_versioned_tab(
        self,
        project_id: str,
        project_name: str,
        version: int,
        content: str,
        workspace_path: str,
    ) -> Optional[dict[str, str]]:
        """
        Create a versioned PRD tab in the project's Google Doc.
        Tab name format: "PRD v1", "PRD v2", etc.
        
        Returns dict with {url, tab_id, doc_id} or None on failure.
        """
        tab_title = f"PRD v{version}"
        doc_url = self.create_or_update_tab(
            project_id=project_id,
            project_name=project_name,
            tab_title=tab_title,
            content=content,
            workspace_path=workspace_path,
        )
        if not doc_url:
            return None

        # Extract tab_id from URL fragment
        tab_id = None
        if "#tab=" in doc_url:
            tab_id = doc_url.split("#tab=")[-1]

        # Extract doc_id from URL
        doc_id = None
        import re as _re
        match = _re.search(r"/d/([^/]+)/", doc_url)
        if match:
            doc_id = match.group(1)

        return {
            "url": doc_url,
            "tab_id": tab_id or "",
            "doc_id": doc_id or "",
        }

    def archive_tab(self, doc_id: str, tab_id: str, version: int) -> bool:
        """
        Archive a PRD version tab by prepending '[Archived]' to its title.
        This marks it as read-only in the version history.
        """
        if not self._initialized or not self._docs_service:
            return False

        try:
            archived_title = f"[Archived] PRD v{version}"
            self._docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [
                        {
                            "updateDocumentTabProperties": {
                                "tabProperties": {
                                    "tabId": tab_id,
                                    "title": archived_title,
                                },
                                "fields": "title",
                            }
                        }
                    ]
                },
            ).execute()
            logger.info("Archived tab: %s (doc: %s)", archived_title, doc_id)
            return True
        except Exception as e:
            logger.warning("Failed to archive tab %s: %s", tab_id, e)
            return False

    def get_version_history(self, workspace_path: str) -> list[dict[str, Any]]:
        """
        List all PRD version tabs in the project's Google Doc.
        Returns list of {version, title, tab_id, url, archived}.
        """
        if not self._initialized or not self._docs_service:
            return []

        doc_id = self._get_project_doc_id(workspace_path)
        if not doc_id:
            return []

        try:
            doc_data = self._docs_service.documents().get(
                documentId=doc_id, includeTabsContent=False
            ).execute()
            tabs = doc_data.get("tabs", [])

            versions = []
            for tab in tabs:
                props = tab.get("tabProperties", {})
                title = props.get("title", "")
                tab_id = props.get("tabId", "")

                # Check if this is a PRD version tab
                import re as _re
                match = _re.search(r"PRD v(\d+)", title)
                if match:
                    version_num = int(match.group(1))
                    is_archived = title.startswith("[Archived]")
                    url = f"https://docs.google.com/document/d/{doc_id}/edit#tab={tab_id}"
                    versions.append({
                        "version": version_num,
                        "title": title,
                        "tab_id": tab_id,
                        "url": url,
                        "archived": is_archived,
                    })

            versions.sort(key=lambda x: x["version"])
            return versions

        except Exception as e:
            logger.error("Failed to get version history: %s", e)
            return []

    def get_heading_ids(self, doc_id: str, tab_id: str) -> dict[str, str]:
        """
        Scan a document tab's structure to extract heading IDs for each heading.
        Returns a dict mapping heading text -> headingId.
        """
        heading_ids = {}
        if not self._initialized or not self._docs_service:
            return heading_ids
        try:
            doc_data = self._docs_service.documents().get(
                documentId=doc_id, includeTabsContent=True
            ).execute()
            
            # Find the correct tab
            tab_body = None
            for tab in doc_data.get("tabs", []):
                if tab.get("tabProperties", {}).get("tabId") == tab_id:
                    tab_body = tab.get("documentTab", {}).get("body", {})
                    break
                    
            if not tab_body:
                return heading_ids
                
            content_elements = tab_body.get("content", [])
            for element in content_elements:
                paragraph = element.get("paragraph")
                if not paragraph:
                    continue
                    
                style = paragraph.get("paragraphStyle", {})
                named_style = style.get("namedStyleType", "")
                if named_style in ("HEADING_1", "HEADING_2", "HEADING_3"):
                    heading_id = style.get("headingId")
                    if heading_id:
                        # Extract the text content of the paragraph
                        text_runs = []
                        for run in paragraph.get("elements", []):
                            text_run = run.get("textRun", {})
                            if text_run and text_run.get("content"):
                                text_runs.append(text_run.get("content"))
                        text = "".join(text_runs).strip()
                        if text:
                            heading_ids[text] = heading_id
        except Exception as e:
            logger.warning("Failed to extract heading IDs from doc %s tab %s: %s", doc_id, tab_id, e)
        return heading_ids

    def upload_feedback_to_drive(
        self,
        filename: str,
        filepath: str,
        mime_type: str,
        project_name: str,
    ) -> Optional[str]:
        """
        Upload a feedback file to Google Drive alongside the PRD.
        Returns the Drive file URL or None on failure.
        """
        if not self._initialized or not self._drive_service:
            return None

        try:
            from googleapiclient.http import MediaFileUpload

            file_metadata: dict[str, Any] = {
                "name": f"[Aikyam Feedback] {project_name} — {filename}",
            }

            # Place in the configured folder if available
            if self._settings and self._settings.google_docs_folder_id:
                file_metadata["parents"] = [self._settings.google_docs_folder_id]

            media = MediaFileUpload(filepath, mimetype=mime_type, resumable=True)
            file = self._drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id,webViewLink",
                supportsAllDrives=True,
            ).execute()

            drive_url = file.get("webViewLink", "")
            file_id = file.get("id", "")

            # Share with configured email
            if self._settings and self._settings.google_docs_share_email:
                self._share_doc(file_id, self._settings.google_docs_share_email)

            logger.info("Uploaded feedback file to Drive: %s (%s)", filename, drive_url)
            return drive_url

        except Exception as e:
            logger.error("Failed to upload feedback file to Drive: %s", e)
            return None

    def _get_project_doc_id(self, workspace_path: str) -> Optional[str]:
        """Read the project doc ID from workspace state."""
        doc_id_file = os.path.join(workspace_path, ".state", "project_doc_id.txt")
        if os.path.exists(doc_id_file):
            try:
                with open(doc_id_file, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        return None

    def _markdown_to_docs_requests(self, markdown: str, tab_id: Optional[str] = None) -> list[dict]:
        """
        Convert markdown content to Google Docs API requests for a specific tab.
        Handles:
        - Headings (# HEADING_1, ## HEADING_2, ### HEADING_3)
        - Bullet lists (- or * converted to •)
        - Bold text (**text**)
        - Plain text
        """
        requests: list[dict] = []
        lines = markdown.split("\n")

        full_text = ""
        bold_ranges = []
        heading_ranges = []  # tuple of (startIndex, endIndex, style)

        for line in lines:
            stripped = line.rstrip()
            
            # Start index of the line in python full_text
            # Google Docs API index is 1-based, and we will insert full_text at index 1.
            # So string index i corresponds to document index i + 1.
            start_offset = len(full_text) + 1
            
            style = None
            prefix = ""
            line_content = ""
            
            if stripped.startswith("# "):
                prefix = ""
                line_content = stripped[2:]
                style = "HEADING_1"
            elif stripped.startswith("## "):
                prefix = ""
                line_content = stripped[3:]
                style = "HEADING_2"
            elif stripped.startswith("### "):
                prefix = ""
                line_content = stripped[4:]
                style = "HEADING_3"
            elif stripped.startswith("- ") or stripped.startswith("* "):
                prefix = "• "
                line_content = stripped[2:]
            elif match := re.match(r"^(\d+\.\s)(.*)", stripped):
                prefix = match.group(1)
                line_content = match.group(2)
            elif stripped == "---" or stripped == "***":
                prefix = "─" * 50
                line_content = ""
            else:
                prefix = ""
                line_content = stripped

            # Process inline formatting like **bold**
            clean_content = ""
            parts = line_content.split("**")
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    start_idx = start_offset + len(prefix) + len(clean_content)
                    clean_content += part
                    end_idx = start_offset + len(prefix) + len(clean_content)
                    bold_ranges.append({
                        "startIndex": start_idx,
                        "endIndex": end_idx
                    })
                else:
                    clean_content += part
            
            line_text = prefix + clean_content + "\n"
            full_text += line_text
            
            # Record heading range
            if style:
                end_offset = start_offset + len(prefix) + len(clean_content)
                heading_ranges.append((start_offset, end_offset, style))

        if not full_text:
            return []

        # Request 1: Insert all text
        location: dict[str, Any] = {"index": 1}
        if tab_id:
            location["tabId"] = tab_id
            
        requests.append({
            "insertText": {
                "location": location,
                "text": full_text
            }
        })

        # Request 2: Apply Heading Styles
        for start, end, style_name in heading_ranges:
            range_obj: dict[str, Any] = {"startIndex": start, "endIndex": end}
            if tab_id:
                range_obj["tabId"] = tab_id
            requests.append({
                "updateParagraphStyle": {
                    "range": range_obj,
                    "paragraphStyle": {
                        "namedStyleType": style_name
                    },
                    "fields": "namedStyleType"
                }
            })

        # Request 3: Apply Bold Styles
        for bold_range in bold_ranges:
            range_obj: dict[str, Any] = {"startIndex": bold_range["startIndex"], "endIndex": bold_range["endIndex"]}
            if tab_id:
                range_obj["tabId"] = tab_id
            requests.append({
                "updateTextStyle": {
                    "range": range_obj,
                    "textStyle": {
                        "bold": True
                    },
                    "fields": "bold"
                }
            })

        return requests


# ── Singleton ──
_google_docs_client: Optional[GoogleDocsClient] = None


def get_google_docs_client() -> GoogleDocsClient:
    """Get or create the singleton Google Docs client."""
    global _google_docs_client
    if _google_docs_client is None:
        _google_docs_client = GoogleDocsClient()
    return _google_docs_client


