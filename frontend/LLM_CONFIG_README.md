# LLM Configuration Feature

## Overview

This feature allows users to configure Language Learning Models (LLMs) for three different roles in the Neural Tool Router system:
- **Teacher Model**: Used for synthetic data generation (Phase 1)
- **Expansion Model**: Fast model for query expansion and decomposition
- **Heavy Model**: Primary model for tool execution and reasoning

## Features

### 1. Multi-Provider Support
The system supports multiple LLM providers with provider-specific credential management:

- **Ollama** 🦙 - Run LLMs locally
- **OpenAI** 🤖 - GPT models (GPT-4, GPT-3.5, etc.)
- **Anthropic** 🧠 - Claude models
- **Google AI** 🔷 - Gemini models
- **IBM Watsonx.ai** 💙 - Enterprise AI models
- **Groq** ⚡ - Ultra-fast LLM inference
- **Azure OpenAI** ☁️ - OpenAI models on Azure
- **Cohere** 🌊 - Command models
- **AWS Bedrock** 🪨 - Foundation models on AWS
- **Vertex AI** 🔺 - Google Cloud AI models

### 2. Provider-Specific Credentials

Each provider has its own set of required and optional credentials:

#### Ollama
- API Base URL (required)

#### OpenAI
- API Key (required)
- API Base URL (optional)
- Organization ID (optional)

#### Anthropic
- API Key (required)

#### Google AI
- API Key (required)

#### IBM Watsonx.ai
- API Key (required)
- Project ID (required)
- Region (optional: us-south, eu-gb, eu-de, jp-tok)

#### Groq
- API Key (required)

#### Azure OpenAI
- API Key (required)
- API Base URL (required)
- API Version (required)

#### Cohere
- API Key (required)

#### AWS Bedrock
- AWS Access Key ID (required)
- AWS Secret Access Key (required)
- AWS Region (required)

#### Vertex AI
- Project ID (required)
- Location (required)
- Service Account JSON Path (optional)

### 3. Configuration Management

- **Add Configuration**: Create new LLM configurations with provider selection and credential input
- **Edit Configuration**: Modify existing configurations
- **Delete Configuration**: Remove configurations with confirmation
- **Export/Import**: Export configurations to JSON and import from JSON files
- **Role Filtering**: Filter configurations by model role
- **Validation**: Comprehensive validation of credentials and configuration parameters

### 4. User Interface

#### Main View
- Role summary cards showing configuration count for each role
- Configuration cards displaying:
  - Role badge
  - Provider badge
  - Model name
  - Temperature setting
  - Max tokens
  - Last updated timestamp
- Filter by role dropdown
- Export/Import buttons
- Add configuration button

#### Configuration Modal
- Role selection dropdown
- Provider selection dropdown with icons
- Model name input with examples
- Temperature slider (0-2)
- Max tokens input
- Dynamic credential form based on selected provider
- Password field visibility toggle
- Inline help text and tooltips
- Links to provider documentation

## File Structure

```
src/app/
├── models/
│   └── llm-config.model.ts          # Data models and interfaces
├── services/
│   └── llm-config.service.ts        # Configuration management service
└── components/
    └── llm-config/
        ├── llm-config.component.ts   # Component logic
        ├── llm-config.component.html # Template
        └── llm-config.component.scss # Styles
```

## Usage

### Accessing the Configuration Page

1. Navigate to the application
2. Click on "Settings" in the sidebar
3. The LLM Configuration page will be displayed

### Adding a Configuration

1. Click "Add Configuration" button
2. Select the model role (Teacher, Expansion, or Heavy)
3. Select the provider from the dropdown
4. Enter the model name (examples are provided)
5. Adjust temperature and max tokens if needed
6. Fill in the required credentials for the selected provider
7. Click "Add Configuration" to save

### Editing a Configuration

1. Click the edit icon on any configuration card
2. Modify the desired fields
3. Click "Update Configuration" to save changes

### Deleting a Configuration

1. Click the delete icon on any configuration card
2. Confirm the deletion in the dialog
3. The configuration will be removed

### Exporting Configurations

1. Click the "Export" button in the header
2. A JSON file will be downloaded with all configurations

### Importing Configurations

1. Click the "Import" button in the header
2. Select a JSON file containing configurations
3. Valid configurations will be imported and added to the system

## Data Storage

Configurations are stored in the browser's localStorage under the key `ntr_llm_configurations`. This allows configurations to persist across browser sessions.

## Validation

The system performs comprehensive validation:

- Required fields must be filled
- Temperature must be between 0 and 2
- Max tokens must be at least 1
- URLs must be valid
- Provider-specific credential requirements are enforced

## Security Considerations

- Credentials are stored in localStorage (browser-based storage)
- Password fields have visibility toggle for user convenience
- For production use, consider implementing:
  - Backend API for secure credential storage
  - Encryption of sensitive data
  - Token-based authentication
  - Credential rotation policies

## Integration with Neural Tool Router

The configured LLMs can be used in the workflow phases:

1. **Generate Phase**: Uses the Teacher Model for synthetic data generation
2. **Train Phase**: Uses embeddings and the configured models
3. **Run Phase**: Uses Expansion Model for query expansion and Heavy Model for tool execution

## Provider Documentation Links

Each provider has a link to its LiteLLM documentation for detailed setup instructions:
- https://docs.litellm.ai/docs/providers/ollama
- https://docs.litellm.ai/docs/providers/openai
- https://docs.litellm.ai/docs/providers/anthropic
- https://docs.litellm.ai/docs/providers/gemini
- https://docs.litellm.ai/docs/providers/watsonx
- https://docs.litellm.ai/docs/providers/groq
- https://docs.litellm.ai/docs/providers/azure
- https://docs.litellm.ai/docs/providers/cohere
- https://docs.litellm.ai/docs/providers/bedrock
- https://docs.litellm.ai/docs/providers/vertex

## Future Enhancements

Potential improvements for future versions:

1. Backend API integration for secure credential storage
2. Credential encryption
3. Configuration templates/presets
4. Bulk operations (delete multiple, duplicate)
5. Configuration versioning
6. Usage statistics and cost tracking
7. Model performance metrics
8. Configuration sharing between users
9. Role-based access control
10. Audit logging for configuration changes

## Troubleshooting

### Configuration not saving
- Check browser console for errors
- Ensure localStorage is not full
- Verify all required fields are filled

### Import failing
- Ensure JSON file is valid
- Check that all required fields are present in the import data
- Verify credential format matches expected structure

### Provider connection issues
- Verify credentials are correct
- Check API base URLs are accessible
- Ensure API keys have proper permissions
- Review provider-specific documentation

## Support

For issues or questions:
1. Check the provider documentation links
2. Review the LiteLLM documentation: https://docs.litellm.ai/
3. Check browser console for error messages
4. Verify network connectivity to provider APIs