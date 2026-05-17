# IBM Cloud Object Storage Setup Guide

This guide will help you set up IBM Cloud Object Storage (COS) for the SynapseForge project.

## Prerequisites

1. IBM Cloud account with COS service provisioned
2. Python virtual environment activated

## Step 1: Install Required Dependencies

The `ibm-cos-sdk` package is required but may not be installed. Install it using:

```bash
cd backend
pip install ibm-cos-sdk
```

Or install all dependencies:

```bash
cd backend
pip install -r requirements.txt
```

## Step 2: Configure COS Credentials

### Option A: Using HMAC Credentials (Recommended for Development)

1. Go to your IBM Cloud Object Storage instance
2. Navigate to **Service Credentials**
3. Create a new credential with HMAC enabled
4. Copy the credentials and add them to `backend/.env`:

```bash
# IBM Cloud Object Storage Configuration
IBM_COS_ENDPOINT=https://s3.us-south.cloud-object-storage.appdomain.cloud
IBM_COS_BUCKET_NAME=synapse-forge
IBM_COS_ACCESS_KEY_ID=your_access_key_id_here
IBM_COS_SECRET_ACCESS_KEY=your_secret_access_key_here
```

### Option B: Using IAM API Key

```bash
# IBM Cloud Object Storage Configuration
IBM_COS_ENDPOINT=https://s3.us-south.cloud-object-storage.appdomain.cloud
IBM_COS_API_KEY_ID=your_api_key_here
IBM_COS_SERVICE_INSTANCE_ID=crn:v1:bluemix:public:cloud-object-storage:global:a/...
IBM_COS_BUCKET_NAME=synapse-forge
```

## Step 3: Create the COS Bucket

You can either:

1. **Let the system create it automatically** - The system will attempt to create the bucket on first use
2. **Create it manually** in the IBM Cloud console:
   - Go to your COS instance
   - Click "Create bucket"
   - Choose "Custom bucket"
   - Name it `synapse-forge` (or match your `IBM_COS_BUCKET_NAME`)
   - Select your preferred region
   - Click "Create"

## Step 4: Restart the Backend

After configuring the credentials:

```bash
cd backend
python main.py
```

You should see:
```
INFO: Initializing S3-compatible COS client using HMAC Access Keys.
```

Instead of:
```
WARNING: IBM Cloud Object Storage credentials not fully configured in .env.
Running in MOCK storage mode...
```

## Step 5: Verify COS Integration

1. Go to the Generate page in the UI
2. Generate a new dataset
3. Check the backend logs - you should see:
   ```
   INFO: Uploading file '...' to 'synapse-forge/workspaces/...'
   INFO: ✓ Uploaded successfully
   ```

4. Verify in IBM Cloud console that files appear in your bucket under `workspaces/`

## Troubleshooting

### Error: "name 'ibm_boto3' is not defined"

**Solution**: Install the IBM COS SDK:
```bash
pip install ibm-cos-sdk
```

### Error: "Failed to initialize IBM COS client"

**Possible causes**:
1. Invalid credentials - double-check your `.env` file
2. Wrong endpoint URL - ensure it matches your COS region
3. Network connectivity issues

**Solution**: Verify your credentials in IBM Cloud console and ensure the endpoint URL is correct for your region.

### Error: "Object not found in bucket"

**Possible causes**:
1. Bucket doesn't exist
2. Wrong bucket name in configuration

**Solution**: 
- Create the bucket manually in IBM Cloud console
- Verify `IBM_COS_BUCKET_NAME` matches the actual bucket name

### Mock Mode (Development)

If you don't have COS credentials configured, the system will run in **MOCK mode**:
- Files are stored locally in `backend/data/cos_mock/`
- This is useful for development and testing
- No IBM Cloud account required

To use MOCK mode, simply don't configure any COS credentials in `.env`.

## COS Bucket Structure

The system organizes artifacts in COS using this structure:

```
synapse-forge/
└── workspaces/
    └── {workspace_id}/
        ├── generate/
        │   ├── dataset/
        │   │   ├── synthetic_queries.jsonl
        │   │   └── archived_dataset_v1.0.jsonl
        │   └── tool_cache/
        │       └── tool_cache.json
        └── train/
            ├── model/
            │   └── fine_tuned_model/
            ├── faiss_index/
            │   └── index.faiss
            └── bm25_index/
                └── bm25_index.pkl
```

## Security Best Practices

1. **Never commit `.env` files** to version control
2. **Use IAM policies** to restrict bucket access
3. **Enable encryption** at rest and in transit
4. **Rotate credentials** regularly
5. **Use separate buckets** for development and production

## Additional Resources

- [IBM Cloud Object Storage Documentation](https://cloud.ibm.com/docs/cloud-object-storage)
- [IBM COS SDK for Python](https://github.com/IBM/ibm-cos-sdk-python)
- [Creating Service Credentials](https://cloud.ibm.com/docs/cloud-object-storage?topic=cloud-object-storage-service-credentials)