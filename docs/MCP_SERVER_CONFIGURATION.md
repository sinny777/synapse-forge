# MCP Server Configuration System

## Overview

The NeuralToolRouter platform now supports dynamic MCP (Model Context Protocol) server configuration through a robust, production-ready interface. This system allows users to register and manage both local (stdio) and remote (SSE) MCP servers directly from the Tool Registry UI.

## Features

### 1. Dual-Mode Configuration Interface

The system provides two complementary views for configuring MCP servers:

#### **Form View**
- User-friendly UI with validation
- Transport-specific field visibility (stdio vs SSE)
- Environment variable masking for security
- Real-time validation feedback
- Dynamic field management (add/remove environment variables and arguments)

#### **JSON View**
- Direct JSON editing for advanced users
- Real-time syntax validation
- Bi-directional state synchronization with Form View
- Inline error highlighting
- JSON schema reference

### 2. Transport Protocol Support

#### **Stdio (Local Process)**
Spawns a local subprocess for MCP server communication.

**Configuration:**
- `command`: Executable command (e.g., `node`, `python`, `npx`)
- `args`: Array of command-line arguments
- `env`: Key-value pairs for environment variables (masked in UI)

**Example:**
```json
{
  "server_id": "weather-api",
  "name": "Weather API Server",
  "transport": "stdio",
  "command": "node",
  "args": ["server.js", "--port", "3000"],
  "env": {
    "API_KEY": "your-api-key",
    "DEBUG": "true"
  }
}
```

#### **SSE (Remote Server)**
Connects to a hosted MCP server over HTTP/HTTPS using Server-Sent Events.

**Configuration:**
- `url`: Full HTTP/HTTPS URL to the MCP server

**Example:**
```json
{
  "server_id": "remote-tools",
  "name": "Remote Tool Server",
  "transport": "sse",
  "url": "https://mcp.example.com"
}
```

### 3. Security Features

- **Environment Variable Masking**: Sensitive values in the `env` object are masked with `***` in API responses
- **Password-style Input**: Form View masks environment variable values by default with toggle visibility
- **Validation**: Server-side validation ensures required fields are present based on transport type
- **Unique Server IDs**: Enforced uniqueness within each workspace prevents conflicts

### 4. Server Status Management

Each MCP server has a status indicator:
- **Active**: Server is operational and ready for connections
- **Disabled**: Server is configured but not active
- **Error**: Connection or configuration error (with error message)

### 5. Connection Testing

Built-in connection testing allows users to verify MCP server configurations:
- Tests actual connectivity
- Lists available tools from the server
- Updates server status based on test results
- Provides detailed error messages for troubleshooting

## Architecture

### Backend Components

#### 1. Database Model (`backend/db/models.py`)
```python
class MCPServer(Base):
    """MCP Server configuration for dynamic tool discovery."""
    __tablename__ = "mcp_servers"
    
    id: UUID
    workspace_id: UUID
    server_id: str  # Unique slug identifier
    name: str
    transport: MCPTransportType  # 'stdio' or 'sse'
    
    # Stdio configuration
    command: str | None
    args: list[str] | None
    env: dict | None
    
    # SSE configuration
    url: str | None
    
    # Status
    status: MCPServerStatus  # 'active', 'disabled', 'error'
    last_error: str | None
```

#### 2. Pydantic Schemas (`backend/db/schemas.py`)
- `MCPServerCreate`: Request schema for creating servers
- `MCPServerUpdate`: Request schema for updating servers
- `MCPServerRead`: Response schema with masked environment variables

#### 3. API Endpoints (`backend/api/mcp_servers.py`)
```
GET    /api/workspaces/{workspace_id}/mcp-servers          # List all servers
POST   /api/workspaces/{workspace_id}/mcp-servers          # Create server
GET    /api/workspaces/{workspace_id}/mcp-servers/{id}     # Get server
PUT    /api/workspaces/{workspace_id}/mcp-servers/{id}     # Update server
DELETE /api/workspaces/{workspace_id}/mcp-servers/{id}     # Delete server
POST   /api/workspaces/{workspace_id}/mcp-servers/{id}/test # Test connection
```

### Frontend Components

#### 1. MCP Server Form Component
**Location**: `frontend/src/app/components/tool-registry/mcp-server-form.component.ts`

**Features**:
- Dual-mode interface (Form/JSON)
- Bi-directional state synchronization
- Real-time validation
- Environment variable masking
- Transport-specific field visibility

#### 2. Tool Registry Integration
**Location**: `frontend/src/app/components/tool-registry/tool-registry.component.ts`

**Features**:
- Tabbed interface (REST Tools / MCP Servers)
- Server listing with status indicators
- CRUD operations
- Connection testing
- Search and filtering

## Usage Guide

### Adding a New MCP Server

#### Via Form View:

1. Navigate to **Tool Registry** page
2. Click the **MCP Servers** tab
3. Click **Register Tool** button
4. Fill in the form:
   - **Server ID**: Unique identifier (lowercase, alphanumeric, hyphens)
   - **Display Name**: User-friendly name
   - **Transport Protocol**: Choose `stdio` or `sse`
   - **Configuration**: Fill transport-specific fields
5. Click **Add Server**

#### Via JSON View:

1. Follow steps 1-3 above
2. Switch to **JSON View** tab
3. Paste or edit JSON configuration
4. Verify "Valid JSON" indicator appears
5. Click **Add Server**

### Editing an Existing Server

1. Click the **Edit** icon on any server card
2. Modify fields in Form View or JSON View
3. Click **Update Server**

### Testing Server Connection

1. Click the **Test Connection** icon (refresh symbol) on any server card
2. Wait for connection test to complete
3. View results in notification banner
4. Check server status indicator for updated state

### Deleting a Server

1. Click the **Delete** icon (trash can) on any server card
2. Confirm deletion in the dialog
3. Server and its configuration will be permanently removed

## Validation Rules

### Server ID
- Required field
- Must match pattern: `^[a-z0-9-]+$` (lowercase alphanumeric and hyphens only)
- Must be unique within the workspace
- Cannot be changed after creation (for edit mode)

### Transport-Specific Validation

**Stdio Transport:**
- `command` is required
- `args` is optional (array of strings)
- `env` is optional (key-value object)

**SSE Transport:**
- `url` is required
- Must start with `http://` or `https://`

## Database Migration

To add the MCP server table to an existing database:

```bash
psql -U your_user -d neural_tool_router -f backend/db/migrations/001_add_mcp_servers.sql
```

Or use your preferred migration tool to execute the SQL script.

## API Examples

### Create Stdio Server
```bash
curl -X POST http://localhost:8000/api/workspaces/{workspace_id}/mcp-servers \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "weather-api",
    "name": "Weather API Server",
    "transport": "stdio",
    "command": "node",
    "args": ["server.js"],
    "env": {
      "API_KEY": "your-key"
    }
  }'
```

### Create SSE Server
```bash
curl -X POST http://localhost:8000/api/workspaces/{workspace_id}/mcp-servers \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "remote-tools",
    "name": "Remote Tool Server",
    "transport": "sse",
    "url": "https://mcp.example.com"
  }'
```

### Test Connection
```bash
curl -X POST http://localhost:8000/api/workspaces/{workspace_id}/mcp-servers/{server_id}/test
```

## Best Practices

1. **Server IDs**: Use descriptive, kebab-case identifiers (e.g., `weather-api`, `file-system-tools`)
2. **Environment Variables**: Store sensitive data (API keys, tokens) in environment variables, not in command arguments
3. **Connection Testing**: Always test connections after creating or updating server configurations
4. **Status Monitoring**: Regularly check server status indicators for any errors
5. **Error Handling**: Review `last_error` field when servers show error status
6. **Security**: Never commit actual API keys or secrets to version control

## Troubleshooting

### Server Shows "Error" Status

1. Check the error message in the server card details
2. Verify the command/URL is correct
3. Ensure all required environment variables are set
4. Test the server manually outside the platform
5. Check server logs for detailed error information

### Connection Test Fails

1. Verify network connectivity (for SSE servers)
2. Check if the process can be spawned (for stdio servers)
3. Ensure all dependencies are installed
4. Verify environment variables are correctly set
5. Check firewall/security settings

### Environment Variables Not Working

1. Ensure keys don't have leading/trailing whitespace
2. Verify values are properly quoted if they contain special characters
3. Check that the spawned process can access the environment variables
4. Test with a simple echo command to verify environment setup

## Future Enhancements

- [ ] Bulk import/export of server configurations
- [ ] Server health monitoring and auto-restart
- [ ] Connection pooling for improved performance
- [ ] Server groups and tagging
- [ ] Audit logging for configuration changes
- [ ] Integration with secret management systems (Vault, AWS Secrets Manager)

## Support

For issues or questions:
- GitHub Issues: [NeuralToolRouter Issues](https://github.com/sinny777/neural-tool-router/issues)
- Documentation: [Architecture Guide](./ARCHITECTURE.md)

---

**Built with ❤️ for the Agentic AI community**