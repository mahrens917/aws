# Complete Roo Setup with Local Embedding Server + Qdrant

## 🎯 Current Status
- ✅ **Qdrant Vector Database**: Running on port 6333 (v1.14.1)
- ✅ **Embedding Server**: Running on port 8080 (OpenAI-compatible)

## 🚀 Complete Roo Configuration

### **Embedding Server Settings:**
- **URL:** `http://localhost:8080/v1`
- **API Key:** `dummy-key`
- **Model:** `text-embedding-ada-002`
- **Dimensions:** `384`

### **Qdrant Vector Database Settings:**
- **URL:** `http://localhost:6333`
- **Collection Name:** `roo-code-index` (or whatever Roo uses)
- **Vector Size:** `384` (matches embedding dimensions)

## 📋 Environment Variables Setup

```bash
# Embedding Server (OpenAI-compatible)
export LOCAL_EMBEDDING_API_BASE="http://localhost:8080/v1"
export LOCAL_EMBEDDING_API_KEY="dummy-key"
export LOCAL_EMBEDDING_MODEL="text-embedding-ada-002"

# Qdrant Vector Database
export QDRANT_URL="http://localhost:6333"
export QDRANT_COLLECTION="roo-code-index"
export VECTOR_DIMENSIONS="384"
```

## 🔧 Configuration File Example

### YAML Configuration:
```yaml
# roo-config.yaml
embeddings:
  provider: "local"
  api_base: "http://localhost:8080/v1"
  api_key: "dummy-key"
  model: "text-embedding-ada-002"
  dimensions: 384

vector_store:
  provider: "qdrant"
  url: "http://localhost:6333"
  collection: "roo-code-index"
  vector_size: 384
```

### JSON Configuration:
```json
{
  "embeddings": {
    "provider": "local",
    "api_base": "http://localhost:8080/v1",
    "api_key": "dummy-key",
    "model": "text-embedding-ada-002",
    "dimensions": 384
  },
  "vector_store": {
    "provider": "qdrant",
    "url": "http://localhost:6333",
    "collection": "roo-code-index",
    "vector_size": 384
  }
}
```

## 🏃‍♂️ Quick Start Commands

1. **Verify both services are running:**
   ```bash
   # Check embedding server
   curl http://localhost:8080/health
   
   # Check Qdrant
   curl http://localhost:6333
   ```

2. **Set environment variables:**
   ```bash
   export LOCAL_EMBEDDING_API_BASE="http://localhost:8080/v1"
   export LOCAL_EMBEDDING_API_KEY="dummy-key"
   export QDRANT_URL="http://localhost:6333"
   ```

3. **Run Roo with local services:**
   ```bash
   roo index /path/to/your/code
   ```

## 🔍 Testing the Complete Setup

### Test Embedding Generation:
```bash
curl -X POST http://localhost:8080/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "input": ["def hello():\n    print(\"Hello World\")"],
    "model": "text-embedding-ada-002"
  }'
```

### Test Qdrant Connection:
```bash
curl -X GET http://localhost:6333/collections
```

### Create a Test Collection in Qdrant:
```bash
curl -X PUT http://localhost:6333/collections/roo-code-index \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 384,
      "distance": "Cosine"
    }
  }'
```

## 📊 Service Status Summary

| Service | Port | Status | Purpose |
|---------|------|--------|---------|
| Embedding Server | 8080 | ✅ Running | Generate code embeddings |
| Qdrant | 6333 | ✅ Running | Store and search vectors |

## 🎉 Benefits of This Setup

- **🔒 Private**: All data stays on your machine
- **⚡ Fast**: Local processing, no API latency
- **💰 Free**: No OpenAI API costs
- **🔧 Compatible**: Drop-in replacement for OpenAI + Qdrant cloud

## 🚨 Troubleshooting

### If Roo can't connect to embeddings:
```bash
# Check if embedding server is running
curl http://localhost:8080/health

# Restart if needed
python3 embedding_server.py --port 8080 &
```

### If Roo can't connect to Qdrant:
```bash
# Check if Qdrant is running
curl http://localhost:6333

# Check collections
curl http://localhost:6333/collections
```

### If embeddings have wrong dimensions:
- Ensure both services use `384` dimensions
- Check Qdrant collection vector size matches embedding dimensions

## 🔄 Restart Services

```bash
# Restart embedding server
pkill -f embedding_server.py
python3 embedding_server.py --port 8080 &

# Qdrant should already be running as a service
# If needed, check your system's service manager
```

Your local Roo setup is now complete with both embedding generation and vector storage running locally!