/**
 * LLM Configuration Models
 * Based on LiteLLM provider documentation: https://docs.litellm.ai/docs/provider_registration/
 *
 * LLM configurations are now workspace-scoped and stored in the database.
 * The Default Workspace ships with 3 pre-seeded Ollama configs:
 *   - Teacher Config
 *   - Expansion Config
 *   - Heavy Config
 */

export type LLMProvider =
  | 'ollama'
  | 'openai'
  | 'anthropic'
  | 'google'
  | 'ibm_watsonx'
  | 'groq'
  | 'azure'
  | 'cohere'
  | 'bedrock'
  | 'vertex_ai';

export interface ProviderCredentials {
  [key: string]: string | undefined;
}

export interface OllamaCredentials extends ProviderCredentials {
  api_base: string; // e.g., http://localhost:11434
}

export interface OpenAICredentials extends ProviderCredentials {
  api_key: string;
  api_base?: string; // Optional for custom endpoints
  organization?: string;
}

export interface AnthropicCredentials extends ProviderCredentials {
  api_key: string;
}

export interface GoogleCredentials extends ProviderCredentials {
  api_key: string;
}

export interface IBMWatsonxCredentials extends ProviderCredentials {
  api_key: string;
  project_id: string;
  region?: string; // e.g., us-south, eu-gb
}

export interface GroqCredentials extends ProviderCredentials {
  api_key: string;
}

export interface AzureCredentials extends ProviderCredentials {
  api_key: string;
  api_base: string;
  api_version: string;
}

export interface CohereCredentials extends ProviderCredentials {
  api_key: string;
}

export interface BedrockCredentials extends ProviderCredentials {
  aws_access_key_id: string;
  aws_secret_access_key: string;
  aws_region_name: string;
}

export interface VertexAICredentials extends ProviderCredentials {
  vertex_project: string;
  vertex_location: string;
  vertex_credentials?: string; // Path to service account JSON
}

/**
 * Workspace-scoped LLM model configuration.
 * Stored in the backend database (llm_configs table).
 */
export interface LLMModelConfig {
  id: string;
  workspace_id: string;
  name: string;
  provider: LLMProvider;
  model_name: string;
  credentials: ProviderCredentials;
  temperature: number;
  max_tokens: number;
  created_at: string;
  updated_at: string;
  created_by?: string;
  updated_by?: string;
}

export interface LLMModelConfigCreate {
  name: string;
  provider: LLMProvider;
  model_name: string;
  credentials?: ProviderCredentials;
  temperature?: number;
  max_tokens?: number;
}

export interface LLMModelConfigUpdate {
  name?: string;
  provider?: LLMProvider;
  model_name?: string;
  credentials?: ProviderCredentials;
  temperature?: number;
  max_tokens?: number;
}

export interface ProviderInfo {
  id: LLMProvider;
  name: string;
  description: string;
  icon: string;
  credentialFields: CredentialField[];
  modelExamples: string[];
  docsUrl: string;
}

export interface CredentialField {
  key: string;
  label: string;
  type: 'text' | 'password' | 'url' | 'select';
  required: boolean;
  placeholder?: string;
  helpText?: string;
  options?: { value: string; label: string }[];
}

export const PROVIDER_INFO: Record<LLMProvider, ProviderInfo> = {
  ollama: {
    id: 'ollama',
    name: 'Ollama',
    description: 'Run LLMs locally with Ollama',
    icon: '🦙',
    credentialFields: [
      {
        key: 'api_base',
        label: 'API Base URL',
        type: 'url',
        required: true,
        placeholder: 'http://localhost:11434',
        helpText: 'Base URL for your Ollama server'
      }
    ],
    modelExamples: ['llama2', 'mistral', 'codellama', 'granite4.1:8b'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/ollama'
  },
  openai: {
    id: 'openai',
    name: 'OpenAI',
    description: 'GPT models from OpenAI',
    icon: '🤖',
    credentialFields: [
      {
        key: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'sk-...',
        helpText: 'Your OpenAI API key'
      },
      {
        key: 'api_base',
        label: 'API Base URL (Optional)',
        type: 'url',
        required: false,
        placeholder: 'https://api.openai.com/v1',
        helpText: 'Custom API endpoint (leave empty for default)'
      },
      {
        key: 'organization',
        label: 'Organization ID (Optional)',
        type: 'text',
        required: false,
        placeholder: 'org-...',
        helpText: 'Your OpenAI organization ID'
      }
    ],
    modelExamples: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/openai'
  },
  anthropic: {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Claude models from Anthropic',
    icon: '🧠',
    credentialFields: [
      {
        key: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'sk-ant-...',
        helpText: 'Your Anthropic API key'
      }
    ],
    modelExamples: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/anthropic'
  },
  google: {
    id: 'google',
    name: 'Google AI',
    description: 'Gemini models from Google',
    icon: '🔷',
    credentialFields: [
      {
        key: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'AIza...',
        helpText: 'Your Google AI API key'
      }
    ],
    modelExamples: ['gemini-pro', 'gemini-1.5-pro', 'gemini-1.5-flash'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/gemini'
  },
  ibm_watsonx: {
    id: 'ibm_watsonx',
    name: 'IBM Watsonx.ai',
    description: 'Enterprise AI from IBM',
    icon: '💙',
    credentialFields: [
      {
        key: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'Your IBM Cloud API key',
        helpText: 'IBM Cloud API key for Watsonx.ai'
      },
      {
        key: 'project_id',
        label: 'Project ID',
        type: 'text',
        required: true,
        placeholder: 'Your Watsonx.ai project ID',
        helpText: 'The project ID from your Watsonx.ai workspace'
      },
      {
        key: 'region',
        label: 'Region',
        type: 'select',
        required: false,
        helpText: 'IBM Cloud region (default: us-south)',
        options: [
          { value: 'us-south', label: 'US South (Dallas)' },
          { value: 'eu-gb', label: 'EU GB (London)' },
          { value: 'eu-de', label: 'EU DE (Frankfurt)' },
          { value: 'jp-tok', label: 'JP TOK (Tokyo)' }
        ]
      }
    ],
    modelExamples: ['ibm/granite-13b-chat-v2', 'meta-llama/llama-3-70b-instruct', 'mistralai/mixtral-8x7b-instruct-v01'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/watsonx'
  },
  groq: {
    id: 'groq',
    name: 'Groq',
    description: 'Ultra-fast LLM inference',
    icon: '⚡',
    credentialFields: [
      {
        key: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'gsk_...',
        helpText: 'Your Groq API key'
      }
    ],
    modelExamples: ['llama-3.1-70b-versatile', 'mixtral-8x7b-32768', 'gemma-7b-it'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/groq'
  },
  azure: {
    id: 'azure',
    name: 'Azure OpenAI',
    description: 'OpenAI models on Azure',
    icon: '☁️',
    credentialFields: [
      {
        key: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'Your Azure OpenAI key',
        helpText: 'Azure OpenAI API key'
      },
      {
        key: 'api_base',
        label: 'API Base URL',
        type: 'url',
        required: true,
        placeholder: 'https://your-resource.openai.azure.com',
        helpText: 'Your Azure OpenAI endpoint'
      },
      {
        key: 'api_version',
        label: 'API Version',
        type: 'text',
        required: true,
        placeholder: '2024-02-15-preview',
        helpText: 'Azure OpenAI API version'
      }
    ],
    modelExamples: ['gpt-4', 'gpt-35-turbo', 'gpt-4-turbo'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/azure'
  },
  cohere: {
    id: 'cohere',
    name: 'Cohere',
    description: 'Command models from Cohere',
    icon: '🌊',
    credentialFields: [
      {
        key: 'api_key',
        label: 'API Key',
        type: 'password',
        required: true,
        placeholder: 'Your Cohere API key',
        helpText: 'Cohere API key'
      }
    ],
    modelExamples: ['command-r-plus', 'command-r', 'command'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/cohere'
  },
  bedrock: {
    id: 'bedrock',
    name: 'AWS Bedrock',
    description: 'Foundation models on AWS',
    icon: '🪨',
    credentialFields: [
      {
        key: 'aws_access_key_id',
        label: 'AWS Access Key ID',
        type: 'text',
        required: true,
        placeholder: 'AKIA...',
        helpText: 'Your AWS access key ID'
      },
      {
        key: 'aws_secret_access_key',
        label: 'AWS Secret Access Key',
        type: 'password',
        required: true,
        placeholder: 'Your AWS secret key',
        helpText: 'Your AWS secret access key'
      },
      {
        key: 'aws_region_name',
        label: 'AWS Region',
        type: 'text',
        required: true,
        placeholder: 'us-east-1',
        helpText: 'AWS region for Bedrock'
      }
    ],
    modelExamples: ['anthropic.claude-3-sonnet', 'amazon.titan-text-express-v1', 'meta.llama3-70b-instruct-v1'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/bedrock'
  },
  vertex_ai: {
    id: 'vertex_ai',
    name: 'Vertex AI',
    description: 'Google Cloud AI models',
    icon: '🔺',
    credentialFields: [
      {
        key: 'vertex_project',
        label: 'Project ID',
        type: 'text',
        required: true,
        placeholder: 'your-gcp-project',
        helpText: 'Your Google Cloud project ID'
      },
      {
        key: 'vertex_location',
        label: 'Location',
        type: 'text',
        required: true,
        placeholder: 'us-central1',
        helpText: 'GCP region for Vertex AI'
      },
      {
        key: 'vertex_credentials',
        label: 'Service Account JSON Path (Optional)',
        type: 'text',
        required: false,
        placeholder: '/path/to/service-account.json',
        helpText: 'Path to service account credentials file'
      }
    ],
    modelExamples: ['gemini-pro', 'chat-bison', 'text-bison'],
    docsUrl: 'https://docs.litellm.ai/docs/providers/vertex'
  }
};

// Made with Bob
