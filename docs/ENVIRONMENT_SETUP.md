# Environment Variable Configuration

This document describes all environment variables required for the LangGraph AI Voice Calling Platform.

## Quick Start

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your actual configuration values
3. Never commit `.env` to version control

## Required Environment Variables

### Database Configuration

```bash
# PostgreSQL Database Connection
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/voice_calling_db
```

**Description**: Connection string for PostgreSQL database using asyncpg driver.

**Required**: Yes

**Format**: `postgresql+asyncpg://[user]:[password]@[host]:[port]/[database]`

**Example**: `postgresql+asyncpg://postgres:securepassword@localhost:5432/voice_platform`

**Notes**:
- Use a strong password in production
- Ensure the database exists before starting the application
- For Docker deployments, use the container hostname

---

### Security Configuration

```bash
# JWT Secret Key
SECRET_KEY=your-secret-key-here-change-in-production

# JWT Algorithm
ALGORITHM=HS256

# Token Expiration (minutes)
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

**Description**: Configuration for JWT token generation and validation.

**Required**: Yes

**SECRET_KEY**: Cryptographic secret for signing JWT tokens. Generate a secure random key in production.

**ALGORITHM**: Hashing algorithm for JWT (typically HS256 or RS256).

**ACCESS_TOKEN_EXPIRE_MINUTES**: How long access tokens remain valid.

**Notes**:
- Use `openssl rand -hex 32` to generate a secure SECRET_KEY
- Never use the default secret in production
- Rotate keys periodically in production

---

### Frontend Configuration

```bash
# Frontend Origin (CORS)
FRONTEND_ORIGIN=http://localhost:3000
```

**Description**: Allowed origin for CORS requests from the frontend.

**Required**: Yes

**Example**: `http://localhost:3000` (development) or `https://your-frontend-domain.com` (production)

**Notes**:
- Must match your frontend URL exactly
- Include protocol (http/https) and port if non-standard

---

### AI Provider Configuration

#### Gemini (Google Generative AI)

```bash
# Gemini API Key
GEMINI_API_KEY=your-gemini-api-key-here
```

**Description**: API key for Google's Gemini LLM model.

**Required**: Yes (for production voice calls)

**How to obtain**:
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Copy and paste into `.env`

**Notes**:
- If not provided, the system will use a mock model for testing
- The mock model simulates tool calling but doesn't use real AI
- Required for actual voice conversations with customers

**Model Options**:
- `gemini-1.5-flash` (default, faster, cheaper)
- `gemini-1.5-pro` (higher quality, slower)
- `gemini-1.0-pro` (legacy)

---

#### Deepgram (Speech-to-Text)

```bash
# Deepgram API Key
DEEPGRAM_API_KEY=your-deepgram-api-key-here
```

**Description**: API key for Deepgram speech-to-text transcription.

**Required**: Yes (for production voice calls)

**How to obtain**:
1. Go to [Deepgram Console](https://console.deepgram.com/)
2. Sign up and create an API key
3. Copy and paste into `.env`

**Notes**:
- Used for real-time speech transcription
- Required for converting customer audio to text
- Deepgram offers a free tier for testing

---

### Telephony Provider Configuration (Twilio)

```bash
# Twilio Account SID
TWILIO_ACCOUNT_SID=your-twilio-account-sid

# Twilio Auth Token
TWILIO_AUTH_TOKEN=your-twilio-auth-token

# Twilio Phone Number
TWILIO_PHONE_NUMBER=+1234567890

# Twilio API Key (optional, for enhanced security)
TWILIO_API_KEY=your-twilio-api-key

# Twilio API Secret (optional)
TWILIO_API_SECRET=your-twilio-api-secret

# Public Webhook URL (for development with ngrok)
PUBLIC_WEBHOOK_URL=https://your-ngrok-url.ngrok-free.app
```

**Description**: Configuration for Twilio telephony integration.

**Required**: Yes (for making/receiving phone calls)

**How to obtain**:
1. Go to [Twilio Console](https://console.twilio.com/)
2. Sign up for a Twilio account
3. Navigate to Account Settings to find Account SID and Auth Token
4. Purchase or verify a phone number in Phone Numbers section
5. Optionally create API Key/Secret for enhanced security

**TWILIO_ACCOUNT_SID**: Your Twilio account identifier (starts with AC)

**TWILIO_AUTH_TOKEN**: Your Twilio authentication token (keep secret)

**TWILIO_PHONE_NUMBER**: The Twilio phone number to use for outbound calls (E.164 format)

**TWILIO_API_KEY/SECRET**: Optional enhanced credentials (recommended for production)

**PUBLIC_WEBHOOK_URL**: Required for development when using ngrok to expose localhost to Twilio webhooks

**Notes**:
- Keep TWILIO_AUTH_TOKEN and TWILIO_API_SECRET secure
- Use E.164 format for phone numbers: +[country code][number]
- For production, use a dedicated Twilio API Key instead of Auth Token
- PUBLIC_WEBHOOK_URL is only needed when running locally with ngrok

---

### Redis Configuration

```bash
# Redis Connection URL
REDIS_URL=redis://localhost:6379/0
```

**Description**: Connection string for Redis (used for caching and job queues).

**Required**: Yes

**Format**: `redis://[host]:[port]/[database]`

**Example**: `redis://localhost:6379/0` or `redis://user:password@redis.example.com:6379/0`

**Notes**:
- Used for Celery task queue and caching
- Database 0 is default, can use different numbers for different environments
- For Docker, use the Redis container hostname
- If using Redis with authentication, include password in URL

---

### Application Settings

```bash
# Maximum Call Duration (seconds)
MAX_CALL_DURATION=300

# Maximum Retry Attempts
MAX_RETRIES=3

# Campaign Concurrency Limit
CAMPAIGN_CONCURRENCY_LIMIT=5

# Default Phone Region (for normalization)
DEFAULT_PHONE_REGION=IN
```

**Description**: Application-level configuration settings.

**Required**: No (defaults provided)

**MAX_CALL_DURATION**: Maximum allowed call duration in seconds (default: 300 = 5 minutes)

**MAX_RETRIES**: Maximum retry attempts for failed operations (default: 3)

**CAMPAIGN_CONCURRENCY_LIMIT**: Maximum number of concurrent calls per campaign (default: 5)

**DEFAULT_PHONE_REGION**: ISO country code for phone number normalization (default: IN for India)

**Notes**:
- Adjust MAX_CALL_DURATION based on your use case and compliance requirements
- Lower CAMPAIGN_CONCURRENCY_LIMIT if you have limited telephony resources
- DEFAULT_PHONE_REGION affects phone number validation and formatting

---

### Optional: Clerk Authentication

```bash
# Clerk Secret Key
CLERK_SECRET_KEY=your-clerk-secret-key

# Clerk Publishable Key
CLERK_PUBLISHABLE_KEY=your-clerk-publishable-key
```

**Description**: Configuration for Clerk authentication (optional alternative to JWT).

**Required**: No (only if using Clerk for authentication)

**How to obtain**:
1. Go to [Clerk Dashboard](https://dashboard.clerk.com/)
2. Create an application
3. Copy API Keys from the dashboard

**Notes**:
- If not provided, the system uses built-in JWT authentication
- Clerk provides enhanced user management features
- Only needed if you choose to use Clerk instead of custom JWT

---

## Development vs Production

### Development Environment (.env.development)

```bash
DATABASE_URL=postgresql+asyncpg://postgres:devpassword@localhost:5432/voice_calling_dev
SECRET_KEY=dev-secret-key-for-testing-only
FRONTEND_ORIGIN=http://localhost:3000
GEMINI_API_KEY=your-gemini-key
DEEPGRAM_API_KEY=your-deepgram-key
TWILIO_ACCOUNT_SID=ACxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=+1234567890
PUBLIC_WEBHOOK_URL=https://abc123.ngrok-free.app
REDIS_URL=redis://localhost:6379/0
MAX_CALL_DURATION=300
DEFAULT_PHONE_REGION=US
```

### Production Environment (.env.production)

```bash
DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@$DB_HOST:5432/$DB_NAME
SECRET_KEY=${SECURE_GENERATED_SECRET}
FRONTEND_ORIGIN=https://your-production-frontend.com
GEMINI_API_KEY=${GEMINI_API_KEY}
DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
TWILIO_ACCOUNT_SID=${TWILIO_ACCOUNT_SID}
TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN}
TWILIO_API_KEY=${TWILIO_API_KEY}
TWILIO_API_SECRET=${TWILIO_API_SECRET}
TWILIO_PHONE_NUMBER=${TWILIO_PHONE_NUMBER}
REDIS_URL=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:6379/0
MAX_CALL_DURATION=600
DEFAULT_PHONE_REGION=US
CLERK_SECRET_KEY=${CLERK_SECRET_KEY}
CLERK_PUBLISHABLE_KEY=${CLERK_PUBLISHABLE_KEY}
```

**Production Best Practices**:
1. Use environment variable substitution (e.g., `${VARIABLE_NAME}`)
2. Set secrets through your cloud provider's secret management (AWS Secrets Manager, Azure Key Vault, etc.)
3. Use strong, randomly generated secrets
4. Enable HTTPS for all endpoints
5. Use dedicated API keys instead of account-level tokens
6. Rotate secrets regularly
7. Monitor API usage and costs

---

## Security Best Practices

1. **Never commit `.env` to version control**
   - Add `.env` to `.gitignore`
   - Use `.env.example` as a template

2. **Use strong secrets**
   ```bash
   # Generate secure secret key
   openssl rand -hex 32
   ```

3. **Separate environments**
   - Use different databases for dev/staging/production
   - Use different API keys for each environment
   - Never use production keys in development

4. **Limit API key permissions**
   - Use Twilio API Keys instead of Auth Token
   - Use scoped API keys when possible
   - Regularly rotate keys

5. **Monitor usage**
   - Set up alerts for unusual API usage
   - Monitor costs for AI providers (Gemini, Deepgram)
   - Track Twilio usage to prevent unexpected charges

---

## Troubleshooting

### Database Connection Issues

**Error**: `sqlalchemy.exc.DBAPIError: could not connect to server`

**Solutions**:
- Verify PostgreSQL is running: `pg_isready`
- Check DATABASE_URL format
- Ensure database exists: `createdb voice_calling_db`
- Check firewall/network access

### Gemini API Errors

**Error**: `Error calling Gemini API: 401 Unauthorized`

**Solutions**:
- Verify GEMINI_API_KEY is correct
- Check API key is active in Google AI Studio
- Ensure billing is enabled on your Google Cloud project

### Deepgram Connection Issues

**Error**: `Deepgram API connection failed`

**Solutions**:
- Verify DEEPGRAM_API_KEY is valid
- Check Deepgram account status
- Ensure you have credits available

### Twilio Webhook Failures

**Error**: `Webhook delivery failed: Unable to reach URL`

**Solutions**:
- Verify PUBLIC_WEBHOOK_URL is accessible from internet
- Use ngrok for local development: `ngrok http 8000`
- Check firewall rules
- Verify webhook path in Twilio console

### Redis Connection Issues

**Error**: `Error connecting to Redis`

**Solutions**:
- Verify Redis is running: `redis-cli ping`
- Check REDIS_URL format
- Ensure Redis port (6379) is accessible
- Check Redis authentication if password is set

---

## Docker Deployment

When using Docker Compose, environment variables can be passed through:

```yaml
# docker-compose.yml
services:
  backend:
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:${DB_PASSWORD}@db:5432/voice_db
      - REDIS_URL=redis://redis:6379/0
```

**Notes**:
- Use service names instead of localhost for inter-container communication
- Override specific variables in docker-compose.yml if needed
- Use Docker secrets for sensitive data in production

---

## Environment-Specific Loading

The application uses `python-dotenv` to load environment variables:

```python
from dotenv import load_dotenv
load_dotenv()  # Loads .env from current directory
```

**Priority order**:
1. System environment variables
2. `.env` file (if exists)
3. Default values in code

**To load a specific environment file**:
```python
load_dotenv(dotenv_path=".env.production")
```

---

## Validation

The application validates required environment variables on startup. If any required variable is missing or invalid, the application will fail to start with a clear error message.

To validate your `.env` file manually:

```bash
# Check if .env exists
test -f .env && echo "Found .env" || echo "No .env file"

# Load and verify (Unix)
export $(grep -v '^#' .env | xargs)
echo $DATABASE_URL
echo $GEMINI_API_KEY
```

---

## Additional Resources

- [PostgreSQL Connection Strings](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING)
- [Google AI Studio](https://makersuite.google.com/app/apikey)
- [Deepgram API Documentation](https://developers.deepgram.com/docs/)
- [Twilio Quickstart](https://www.twilio.com/docs/usage/tutorials/how-to-use-your-twilio-account-number)
- [Redis Connection Protocol](https://redis.io/docs/connect/patterns/)
- [Clerk Authentication](https://clerk.com/docs)
