import argparse
import requests
import sys
import os
import time

API_BASE = "http://localhost:8000/api"
WORKSPACE_NAME = "Default Workspace"

session = requests.Session()
session.headers.update({"X-System-Override": "true"})


MASTER_SERVERS = [
    {
        "name": "Mediclaim MCP Server",
        "description": "Medical claims processing and policy retrieval server.",
        "type": "MCP_SERVER",
        "transport": "stdio",
        "command": "python",
        "args": ["../examples/beeai_mediclaim_processing/mock_fastmcp_server.py"],
        "is_enabled": True
    },
    {
        "name": "UHNW Banking MCP Server",
        "description": "Ultra High Net Worth banking operations and wealth management.",
        "type": "MCP_SERVER",
        "transport": "stdio",
        "command": "python",
        "args": ["../examples/langgraph_UHNW_banking/mock_fastmcp_server.py"],
        "is_enabled": True
    },
    {
        "name": "Local File System",
        "description": "Provides secure access to the local file system.",
        "type": "MCP_SERVER",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/gurvindersingh/Documents"],
        "is_enabled": False
    },
    {
        "name": "SQLite Database",
        "description": "Allows interacting with SQLite databases.",
        "type": "MCP_SERVER",
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-sqlite", "--db", "/tmp/mcp-test.db"],
        "is_enabled": False
    },
    {
        "name": "Web Fetch Server",
        "description": "Fetches content from the internet safely.",
        "type": "MCP_SERVER",
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
        "is_enabled": False
    },
    {
        "name": "Firecrawl MCP",
        "description": "Web scraping and crawling using Firecrawl.",
        "type": "MCP_SERVER",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "firecrawl-mcp"],
        "env": {"FIRECRAWL_API_KEY": "REPLACE_WITH_YOUR_KEY"},
        "is_enabled": False
    },
    {
        "name": "Brave Search MCP",
        "description": "Search the web using Brave Search.",
        "type": "MCP_SERVER",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": "REPLACE_WITH_YOUR_KEY"},
        "is_enabled": False
    },
    {
        "name": "Perplexity MCP",
        "description": "Search and research using Perplexity AI.",
        "type": "MCP_SERVER",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@perplexity-ai/mcp-server"],
        "env": {"PERPLEXITY_API_KEY": "REPLACE_WITH_YOUR_KEY"},
        "is_enabled": False
    }
]

def get_workspace():
    resp = session.get(f"{API_BASE}/workspaces")
    if resp.status_code == 200:
        workspaces = resp.json()
        for ws in workspaces:
            if ws["name"] == WORKSPACE_NAME:
                return ws
    return None

def create_workspace():
    resp = session.post(f"{API_BASE}/workspaces", json={
        "name": WORKSPACE_NAME,
        "description": "Auto-created workspace for master data",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_dim": 384
    })
    if resp.status_code == 201:
        return resp.json()
    raise Exception(f"Failed to create workspace: {resp.text}")

def get_tools(workspace_id):
    resp = session.get(f"{API_BASE}/workspaces/{workspace_id}/tools")
    if resp.status_code == 200:
        return resp.json()
    return []

def delete_all_master_data():
    ws = get_workspace()
    if not ws:
        print("No master workspace found.")
        return
    tools = get_tools(ws["id"])
    for t in tools:
        print(f"Deleting tool {t['name']}...")
        session.delete(f"{API_BASE}/workspaces/{ws['id']}/tools/{t['id']}")
    print(f"Deleting workspace {ws['name']}...")
    session.delete(f"{API_BASE}/workspaces/{ws['id']}")
    print("Master data cleared.")

def create_master_data():
    ws = get_workspace()
    if not ws:
        print(f"Creating workspace '{WORKSPACE_NAME}'...")
        ws = create_workspace()
    
    workspace_id = ws["id"]
    existing_tools = get_tools(workspace_id)
    existing_names = [t["name"] for t in existing_tools]

    for srv in MASTER_SERVERS:
        if srv["name"] in existing_names:
            print(f"Server '{srv['name']}' already exists, skipping...")
            continue
        
        print(f"Registering '{srv['name']}'...")
        resp = session.post(f"{API_BASE}/workspaces/{workspace_id}/tools", json=srv)
        if resp.status_code == 201:
            print(f"  Success: {resp.json().get('id')}")
        else:
            print(f"  Failed: {resp.status_code} {resp.text}")

def update_master_data():
    print("Updating master data (Clearing and Recreating)...")
    delete_all_master_data()
    # Wait for DB to settle
    time.sleep(2)
    create_master_data()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Master Data for SynapseForge")
    parser.add_argument("action", choices=["create", "update", "delete"], help="Action to perform on master data")
    
    try:
        args = parser.parse_args()
    except SystemExit:
        parser.print_help()
        sys.exit(1)
        
    try:
        # Check if API is running
        session.get(f"{API_BASE}/workspaces")
    except requests.ConnectionError:
        print("ERROR: Backend API is not reachable at http://localhost:8000. Please start the backend server first.")
        sys.exit(1)
        
        
    if args.action == "create":
        create_master_data()
    elif args.action == "update":
        update_master_data()
    elif args.action == "delete":
        delete_all_master_data()
