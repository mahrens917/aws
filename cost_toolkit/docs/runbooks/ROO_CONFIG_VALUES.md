# Roo Configuration Values for Local Embedding Server

## Quick Setup Values

Here are the exact values to configure Roo to use your local embedding server:

### **URL/Base URL:**
```
http://localhost:8080/v1
```

### **API Key:**
```
dummy-key
```
*(Any value works - the local server doesn't validate API keys)*

### **Model:**
```
text-embedding-ada-002
```

### **Model Dimensions:**
```
384
```

## Configuration Methods

### Method 1: Environment Variables (Recommended)
```bash
export LOCAL_EMBEDDING_API_BASE="http://localhost:8080/v1"
export LOCAL_EMBEDDING_API_KEY="dummy-key"
export LOCAL_EMBEDDING_MODEL="text-embedding-ada-002"
export LOCAL_EMBEDDING_DIMENSIONS="384"
```

### Method 2: Roo Configuration File
If Roo uses a config file (`.roo-config`, `roo.yaml`, etc.), add:

```yaml
embeddings:
  provider: "local"
  api_base: "http://localhost:8080/v1"
  api_key: "dummy-key"
  model: "text-embedding-ada-002"
  dimensions: 384
```

Or in JSON format:
```json
{
  "embeddings": {
    "provider": "local",
    "api_base": "http://localhost:8080/v1",
    "api_key": "dummy-key",
    "model": "text-embedding-ada-002",
    "dimensions": 384
  }
}
```

### Method 3: Command Line Arguments
```bash
roo --embedding-api-base "http://localhost:8080/v1" \
    --embedding-api-key "dummy-key" \
    --embedding-model "text-embedding-ada-002" \
    --embedding-dimensions 384
```

## Step-by-Step Setup

1. **Start the embedding server:**
   ```bash
   python3 embedding_server.py --port 8080
   ```

2. **Verify it's running:**
   ```bash
   curl http://localhost:8080/health
   # Should return: {"status": "healthy", "model_loaded": true}
   ```

3. **Configure Roo with the values above**

4. **Test Roo's embedding functionality**

## Verification

To verify Roo is using your local server, check the server logs. You should see requests like:
```
INFO:werkzeug:127.0.0.1 - - [20/Jul/2025 15:49:21] "POST /v1/embeddings HTTP/1.1" 200 -
```

## Troubleshooting

- **If Roo can't connect:** Make sure the server is running on port 8080
- **If embeddings fail:** Check that the dimensions match (384)
- **If authentication fails:** Try different API key values or check Roo's auth requirements

## Alternative Port

If port 8080 is in use, start the server on a different port:
```bash
python3 embedding_server.py --port 8081
```

Then update the URL to:
```
http://localhost:8081/v1