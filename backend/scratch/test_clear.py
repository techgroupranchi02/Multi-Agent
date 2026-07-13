"""
Test the delete project endpoint.
"""
import httpx

def test_delete():
    client = httpx.Client(base_url="http://localhost:8000")
    
    # 1. Create a dummy project
    print("Creating project...")
    res = client.post("/api/projects", json={
        "name": "Delete Test Project",
        "raw_requirements": "Test requirements"
    })
    print("Create status:", res.status_code)
    data = res.json()
    project_id = data.get("id")
    print("Project ID:", project_id)
    
    if not project_id:
        print("Failed to create project")
        return
        
    # 2. Delete the project
    print("\nDeleting project...")
    res = client.delete(f"/api/projects/{project_id}")
    print("Delete status:", res.status_code)
    print("Delete response:", res.json())

if __name__ == "__main__":
    test_delete()
