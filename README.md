# MXToolbox (MXroute & Cloudflare Email Manager)

MXToolbox is a self-hosted Flask-based web application designed to simplify email hosting management on the MXroute platform. It integrates directly with **MXroute** for mail service management and **Cloudflare** for automated DNS provisioning (MX, SPF, DKIM, and verification records). 

Authentication is supported via OpenID Connect (OIDC) with fine-grained access control, allowing administrators to delegate specific domain management to individual users.

---

## Features

- **Domain Management**: Register and unregister domains on MXroute.
- **Cloudflare Integration**: Automatic creation of Cloudflare DNS zones, TXT verification records, and all required email records (MX, SPF, DKIM).
- **Email Account Management**: Create, update quotas/passwords, and delete email addresses.
- **Email Forwarders**: Create and delete email aliases/forwarders.
- **Spam Control**: Manage spam protection settings for each domain.
- **Delegated Access Control**: Administrators can assign specific domains to OIDC-authenticated users, allowing them to manage only their designated email domains.
- **Robust Authentication**: Integration with OpenID Connect (SSO) with a secure, local admin fallback.

---

## Configuration

To run the application, copy the example environment file:
```bash
cp .env.example .env
```
And configure the variables inside `.env`:

### 1. MXroute Settings
- `MX_SERVER`: The hostname of your MXroute server (e.g., `blizzard.mxrouting.net`).
- `MX_USER`: Your MXroute administrator username.
- `MX_API_KEY`: Your MXroute API key.

### 2. Cloudflare Settings
- `CF_API_TOKEN`: A Cloudflare API Token with permissions to edit DNS records and zones (`Zone.Zone:Edit`, `Zone.DNS:Edit`).
- `CF_ACCOUNT_ID`: Your Cloudflare Account ID.

### 3. Authentication & Security
- `OIDC_ENABLED`: Set to `true` to restrict access using OpenID Connect + Local Admin, or `false` to run in local developer mode (which bypasses login as a mock admin).
- `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET`: Credentials from your OIDC Identity Provider.
- `OIDC_DISCOVERY_URL`: The discovery document URL (e.g., `https://auth.example.com/.well-known/openid-configuration`).
- `OIDC_REDIRECT_URI`: The callback endpoint (e.g., `https://your-domain.com/oidc/callback`).
- `OIDC_ADMIN_USERS`: Comma-separated list of emails that should have super-administrator privileges.
- `SECRET_KEY`: A long, random string used by Flask to sign session cookies securely.

### 4. Local Fallback Admin
- `ADMIN_USER`: The username for local fallback (defaults to `admin`).
- `ADMIN_PASSWORD`: A secure password for the fallback administrator.

---

## How to Run Locally

### Prerequisites
- Python 3.11+

### Installation & Execution
1. Create a Python virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python app.py
   ```
   The application will start by default on `http://127.0.0.1:5000`.

---

## Deployment with Docker

The application includes a `Dockerfile` and `docker-compose.yml` for easy containerized deployment.

> [!IMPORTANT]
> The application stores domain delegation assignments in a file named `domain_mapping.json` inside the root directory. To prevent losing delegation data when the Docker container is updated or restarted, you must mount this file (or its parent directory) as a persistent volume.

### Using Docker Compose (Recommended)
Docker Compose automatically reads configuration options from the `.env` file in the same directory.

1. Configure your `.env` file.
2. Initialize and run the containers in detached (background) mode:
   ```bash
   docker-compose up --build -d
   ```

To persist the `domain_mapping.json` configuration, update your `docker-compose.yml` to include a volume mount:
```yaml
version: '3.8'

services:
  mxtoolbox:
    build: .
    container_name: mxtoolbox
    restart: always
    ports:
      - "5000:5000"
    env_file:
      - .env
    volumes:
      - ./domain_mapping.json:/app/domain_mapping.json
```

### Using Raw Docker Commands
1. Build the Docker image:
   ```bash
   docker build -t mxtoolbox .
   ```
2. Run the container, mounting the local `.env` and `domain_mapping.json`:
   ```bash
   touch domain_mapping.json
   docker run -d \
     --name mxtoolbox \
     -p 5000:5000 \
     --env-file .env \
     -v $(pwd)/domain_mapping.json:/app/domain_mapping.json \
     --restart always \
     mxtoolbox
   ```
