"""
Test creating one doc with multiple tabs and formatted rich-text content.
"""
import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")

def test():
    from src.integrations.google_docs_client import get_google_docs_client
    
    gdocs = get_google_docs_client()
    workspace_path = r"c:\Aikyam\Multi-Agent\backend\workspace\test_proj"
    os.makedirs(os.path.join(workspace_path, ".state"), exist_ok=True)
    
    # 1. Clean previous state
    state_file = os.path.join(workspace_path, ".state", "project_doc_id.txt")
    if os.path.exists(state_file):
        os.remove(state_file)
        print("Cleared previous project doc ID")
        
    print("\n--- Creating Tab 1: PRD ---")
    prd_content = """# Product Requirements Document

## 1. Executive Summary
This is a **bold executive summary** description of the Employee Leave Management System.
It has list items:
- First item is **crucial** for success.
- Second item is **highly recommended**.

## 2. Requirements
1. **User Auth**: Users must be able to log in securely.
2. **Leave Application**: Employees can apply for leave.
"""
    prd_url = gdocs.create_or_update_tab(
        project_id="test_proj_id",
        project_name="Leave Manager",
        tab_title="PRD",
        content=prd_content,
        workspace_path=workspace_path
    )
    print(f"PRD URL: {prd_url}")
    
    print("\n--- Creating Tab 2: Open Questions ---")
    oq_content = """# Open Questions

The following questions need **immediate clarification**:
1. **Leave Types**: Which specific leave types do we need to support?
2. **Approval Flow**: Do we need multi-level manager approval or is one level enough?
"""
    oq_url = gdocs.create_or_update_tab(
        project_id="test_proj_id",
        project_name="Leave Manager",
        tab_title="Open Questions",
        content=oq_content,
        workspace_path=workspace_path
    )
    print(f"Open Questions URL: {oq_url}")

    print("\n--- Creating Tab 3: PDD ---")
    pdd_content = """# Product Design Document

## 1. Architecture Specs
We will use a **layered architecture** with FastAPI and React.

## 2. Database Models
- **User Table**: ID, email, hashed_password.
- **LeaveRequest Table**: ID, user_id, start_date, end_date.
"""
    pdd_url = gdocs.create_or_update_tab(
        project_id="test_proj_id",
        project_name="Leave Manager",
        tab_title="PDD",
        content=pdd_content,
        workspace_path=workspace_path
    )
    print(f"PDD URL: {pdd_url}")

if __name__ == "__main__":
    test()
