# Distractor Submission API Documentation

## Overview

This API endpoint allows automated systems (like n8n workflows) to submit distractors (incorrect answer options) for existing questions in the flashcards database.

## Endpoint

**`POST /api/submit_distractors`**

## Authentication

The endpoint supports two authentication methods:

1. **Bearer Token** (recommended):
   ```
   Authorization: Bearer YOUR_N8N_INGEST_TOKEN
   ```

2. **API Key Header**:
   ```
   X-API-Key: YOUR_N8N_INGEST_TOKEN
   ```

The token must match the `N8N_INGEST_TOKEN` environment variable configured on the server.

## Request Format

### Single Submission

Submit distractors for a single question:

```json
{
  "question_id": "abc123...",
  "distractors": [
    "Incorrect answer option 1",
    "Incorrect answer option 2",
    "Incorrect answer option 3"
  ],
  "user_id": "optional-user-id",
  "username": "optional-username"
}
```

### Batch Submission

Submit distractors for multiple questions in one request:

```json
{
  "submissions": [
    {
      "question_id": "abc123...",
      "distractors": ["distractor 1", "distractor 2"]
    },
    {
      "question_id": "def456...",
      "distractors": ["distractor 3", "distractor 4"]
    }
  ]
}
```

## Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question_id` | string | Yes | ID of existing question in the database (must already exist) |
| `distractors` | array[string] | Yes | Array of 1-4 distractor texts (incorrect answers) |
| `user_id` | string | No | User ID for attribution (defaults to `N8N_DEFAULT_USER_ID`) |
| `username` | string | No | Username for attribution (defaults to `N8N_DEFAULT_USERNAME`) |

## Response Format

### Success Response (201 Created)

All submissions accepted:

```json
{
  "accepted": [
    {
      "index": 0,
      "question_id": "abc123...",
      "count": 3
    }
  ],
  "errors": []
}
```

### Partial Success Response (207 Multi-Status)

Some submissions failed:

```json
{
  "accepted": [
    {
      "index": 0,
      "question_id": "abc123...",
      "count": 2
    }
  ],
  "errors": [
    {
      "index": 1,
      "error": "Question with id \"invalid-id\" does not exist"
    }
  ]
}
```

### Error Response (400 Bad Request)

Invalid request format:

```json
{
  "error": "Invalid JSON payload"
}
```

### Error Response (401 Unauthorized)

Authentication failed:

```json
{
  "error": "Unauthorized"
}
```

## Response Fields

### Success Object (in `accepted` array)

| Field | Type | Description |
|-------|------|-------------|
| `index` | integer | Index of submission in request array |
| `question_id` | string | ID of question that received distractors |
| `count` | integer | Number of distractors successfully submitted |

### Error Object (in `errors` array)

| Field | Type | Description |
|-------|------|-------------|
| `index` | integer | Index of submission in request array |
| `error` | string | Error message describing why submission failed |

## Validation Rules

1. **Question Existence**: The `question_id` must reference an existing question in the `questions` table
2. **Distractor Count**: Minimum 1, maximum 4 distractors per submission (limited by `NUMBER_OF_DISTRACTORS` config)
3. **Non-Empty**: Distractor text cannot be empty after trimming whitespace
4. **Data Type**: `distractors` must be an array

## Common Error Messages

| Error Message | Cause | Solution |
|--------------|-------|----------|
| `Invalid JSON payload` | Malformed JSON in request body | Check JSON syntax |
| `Unauthorized` | Invalid or missing token | Verify N8N_INGEST_TOKEN is correct |
| `question_id is required` | Missing question_id field | Add question_id to request |
| `distractors must be a non-empty array` | Missing or empty distractors array | Provide at least one distractor |
| `Question with id "..." does not exist` | Invalid question_id | Verify question exists in database |
| `At least one non-empty distractor is required` | All distractors are empty strings | Provide valid distractor text |

## Workflow Integration

### Submission Flow

1. **Submit distractors** via `POST /api/submit_distractors`
   - Distractors inserted into `submitted_distractors` table (pending approval)

2. **Admin Review** via web UI at `/admin_review_distractor`
   - Admin can approve or reject each distractor

3. **Approval** via `POST /api/approve_distractor`
   - Moves distractor to `manual_distractors` table (live in application)
   - Increments user's `approved_cards` counter

4. **Rejection** via `POST /api/reject_distractor`
   - Removes distractor from `submitted_distractors` table

### Related Endpoints

- `POST /api/approve_distractor` - Approve pending distractor
- `POST /api/reject_distractor` - Reject pending distractor
- `POST /api/ingest_flashcards` - Submit new flashcards (can include distractors)
- `POST /api/check_duplicates` - Check for duplicate questions

## Usage Examples

### cURL Example (Single Submission)

```bash
curl -X POST https://your-domain.com/api/submit_distractors \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "question_id": "abc123def456",
    "distractors": [
      "Paris",
      "Berlin",
      "Madrid"
    ]
  }'
```

### cURL Example (Batch Submission)

```bash
curl -X POST https://your-domain.com/api/submit_distractors \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{
    "submissions": [
      {
        "question_id": "abc123",
        "distractors": ["Wrong answer 1", "Wrong answer 2"]
      },
      {
        "question_id": "def456",
        "distractors": ["Incorrect 1", "Incorrect 2", "Incorrect 3"]
      }
    ]
  }'
```

### Python Example

```python
import requests

url = "https://your-domain.com/api/submit_distractors"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer YOUR_TOKEN_HERE"
}

payload = {
    "question_id": "abc123def456",
    "distractors": [
        "Distractor 1",
        "Distractor 2",
        "Distractor 3"
    ],
    "user_id": "ai-generator-001",
    "username": "AI Generator Bot"
}

response = requests.post(url, json=payload, headers=headers)
result = response.json()

if response.status_code == 201:
    print(f"Success! {result['accepted'][0]['count']} distractors submitted")
elif response.status_code == 207:
    print(f"Partial success: {len(result['accepted'])} accepted, {len(result['errors'])} errors")
else:
    print(f"Error: {result.get('error')}")
```

### n8n Workflow Node (HTTP Request)

**Configuration:**
- **Method**: POST
- **URL**: `https://your-domain.com/api/submit_distractors`
- **Authentication**: Generic Credential Type
  - **Header Auth Name**: `Authorization`
  - **Header Auth Value**: `Bearer {{$credentials.n8nIngestToken}}`
- **Body Content Type**: JSON
- **Body Parameters**:
```json
{
  "question_id": "{{ $json.question_id }}",
  "distractors": "{{ $json.distractors }}",
  "user_id": "n8n-workflow",
  "username": "AI Distractor Generator"
}
```

## Database Schema

### submitted_distractors Table

Distractors are inserted into this table pending admin approval:

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `user_id` | TEXT | User ID of submitter |
| `username` | TEXT | Username of submitter |
| `question_id` | TEXT | ID of question (FK to questions.id) |
| `distractor_text` | TEXT | The incorrect answer text |
| `created_at` | TIMESTAMPTZ | Submission timestamp |

### manual_distractors Table

After approval, distractors are moved to this table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `question_id` | TEXT | ID of question (FK to questions.id) |
| `distractor_text` | TEXT | The incorrect answer text |
| `created_by` | TEXT | User ID of creator |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

## Best Practices

1. **Validate Question Exists First**: Use `GET /api/questions/{id}` or query database to verify question exists before submitting
2. **Quality Over Quantity**: Submit 3-4 high-quality distractors rather than many low-quality ones
3. **Plausible Distractors**: Ensure distractors are plausible incorrect answers (common misconceptions)
4. **Batch When Possible**: Use batch submission format for multiple questions to reduce API calls
5. **Handle Partial Failures**: Check `errors` array and retry failed submissions
6. **User Attribution**: Provide meaningful `user_id` and `username` for tracking and statistics

## Rate Limiting

Currently, no rate limiting is implemented. If needed in the future, standard Flask-Limiter patterns will be applied.

## Security Considerations

- **Token Security**: Store `N8N_INGEST_TOKEN` securely (environment variable, secrets manager)
- **HTTPS Only**: Always use HTTPS in production to protect token in transit
- **Token Rotation**: Periodically rotate the ingest token
- **Logging**: All submissions are logged with user attribution for audit purposes

## Troubleshooting

### "Question with id ... does not exist"

**Problem**: The question_id doesn't match any record in the questions table

**Solutions**:
1. Query the questions table to get valid question IDs
2. If submitting for a newly created flashcard, wait for it to be approved first
3. Check if you're using the temporary `flashcard_{id}` format (not supported by this endpoint)

### "Unauthorized"

**Problem**: Token authentication failed

**Solutions**:
1. Verify `N8N_INGEST_TOKEN` environment variable is set on server
2. Check token is included in request header correctly
3. Ensure token matches exactly (no extra spaces or characters)

### All distractors rejected with "At least one non-empty distractor is required"

**Problem**: All distractors are empty strings or whitespace

**Solutions**:
1. Check data source provides non-empty distractor text
2. Verify string encoding is correct (no invisible characters)
3. Test with hardcoded distractor text to isolate issue

## Changelog

### Version 1.0 (2026-01-26)
- Initial release of `/api/submit_distractors` endpoint
- Support for single and batch submission formats
- Token-based authentication
- Validation of question existence
- Distractor count limiting (1-4 per question)
