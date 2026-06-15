# MXToolbox (MXroute Email Manager)

MXToolbox is a self-hosted Flask-based web application designed to simplify email hosting management on the MXroute platform. It integrates directly with **MXroute** for mail service management and **Cloudflare** for automated DNS provisioning (MX, SPF, DKIM, and verification records).
Authentication is supported via both OpenID Connect (OIDC) and traditional local credentials (username/password), with fine-grained access control to delegate specific domain management to individual users.

## Why?

This started as a way to easily onboard new users to MXroute email domains I own, and a way to reset email passwords for the people I manage email addresses for without needing to go through the pain of logging into each domain individually at mxRoute. I got carried away with the scope creep and ended up trying to get usage out of all of the possibilities of the mxRoute API. After that I figured I could get it to automatically setup cloudflare DNS records to go with it.

> [!IMPORTANT]
> This tool is 90% vibe coded. And was done so to fix a particular annoyance I had and to learn some python, javascript and how to use API's. It's probably not the most robust or secure thing in the world. It's targeted to my specific needs and uses case and is not meant for the public, however if you want to use it for your own use case, be my guest. And if you feel generous enough to point out my shortcomings, please do so in the issues tab. 

---

## Features

- **Domain Management**: Register and unregister domains on MXroute.
- **Cloudflare Integration**: Automatic creation of Cloudflare DNS zones, TXT verification records, and all required email records (MX, SPF, DKIM).
- **Email Account Management**: Create, update quotas/passwords, and delete email addresses.
- **Email Forwarders**: Create and delete email aliases/forwarders.
- **Spam Control**: Manage spam protection settings for each domain.
- **Delegated Access Control**: Administrators can assign specific domains to individual users, allowing them to manage only their designated email domains.
- **Robust Authentication**: Integration with OpenID Connect (SSO), as well as a traditional credentials database (username/password) with fallback capabilities.

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
- `OIDC_ENABLED`: Set to `true` to authenticate via OpenID Connect + Local Admin, or `false` to restrict access purely using local database-driven username/password credentials.
- `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET`: Credentials from your OIDC Identity Provider.
- `OIDC_DISCOVERY_URL`: The discovery document URL (e.g., `https://auth.example.com/.well-known/openid-configuration`).
- `OIDC_REDIRECT_URI`: The callback endpoint (e.g., `https://your-domain.com/oidc/callback`).
- `OIDC_SCOPES`: The authorization scopes requested from the provider (defaults to `openid email profile groups`).
- `OIDC_ADMIN_USERS`: Comma-separated list of emails that should have super-administrator privileges.
- `OIDC_ADMIN_GROUP`: OIDC group name that automatically grants admin privileges (defaults to `administrators`).
- `SECRET_KEY`: A long, random string used by Flask to sign session cookies securely.

### 4. Local Fallback Admin
- `ADMIN_USER`: The username for local fallback (defaults to `admin`).
- `ADMIN_PASSWORD`: A secure password for the fallback administrator.

---

## How to Run Locally

### Prerequisites
- Python 3.11+

### Installation & Execution
1. Clone the repository:
   * **Using SSH:**
     ```bash
     git clone git@github.com:t0msh/mxtoolbox.git
     cd mxtoolbox
     ```
   * **Using HTTPS:**
     ```bash
     git clone https://github.com/t0msh/mxtoolbox.git
     cd mxtoolbox
     ```
2. Create a Python virtual environment:
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
> To prevent losing data when the Docker container is updated or restarted, you must persist the SQLite database (`mxtoolbox.db`) using a volume.

### Using Docker Compose (Recommended)
Docker Compose automatically reads configuration options from the `.env` file and persists the database in a named volume (`mxtoolbox_data`).

1. Configure your `.env` file.
2. Build and start the containers in detached (background) mode:
   ```bash
   docker compose up --build -d
   ```

The default `docker-compose.yml` configuration:
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
    environment:
      - DATABASE_FILE=/data/mxtoolbox.db
    volumes:
      - mxtoolbox_data:/data

volumes:
  mxtoolbox_data:
```

### Using Raw Docker Commands
1. Build the Docker image:
   ```bash
   docker build -t mxtoolbox .
   ```
2. Run the container, configuring the database location and mounting a persistent volume:
   ```bash
   docker run -d \
     --name mxtoolbox \
     -p 5000:5000 \
     --env-file .env \
     -e DATABASE_FILE=/data/mxtoolbox.db \
     -v mxtoolbox_data:/data \
     --restart always \
     mxtoolbox
   ```
