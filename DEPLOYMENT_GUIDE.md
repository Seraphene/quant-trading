# Deployment Guide: Google Cloud VM

This guide explains how to deploy your `quant-trading` system to a Google Cloud Platform (GCP) Virtual Machine and run it 24/7 using Docker.

## 1. Prerequisites (Existing VM)
This guide assumes you already have a Google Cloud VM running with **Docker** installed.

### A. Fix Permission Denied
If you see `permission denied` when running Docker, it's because your user lacks rights.
- **Quick Fix**: Add `sudo` before every command (e.g., `sudo docker build`).
- **Permanent Fix**: Run these to add yourself to the docker group:
  ```bash
  sudo usermod -aG docker $USER
  newgrp docker # This activates the change in your current session
  ```

### B. Install Docker Compose
If `docker-compose` is not found, install the modern plugin:
```bash
sudo apt-get install -y docker-compose-plugin
```
*Note: Once installed, use `docker compose` (with a space) instead of `docker-compose` (with a hyphen).*

## 2. Upload Your Code
You can use `git` or `scp` to upload your code to the VM.
- **Git**: Clone your repository directly to the VM.
- **SCP**: `gcloud compute scp --recurse . your-instance-name:~/quant-trading`

## 3. Configure Environment Variables
On the VM, create a `.env` file in the project root:
```bash
nano .env
```
Paste your credentials (Alpaca keys, Email SMTP, etc.) into this file. **Note**: The `Dockerfile` is configured to copy the rest of the code but ignores your local `.env` for security. You must create it on the VM.

## 4. Build and Run with Docker Compose

I have provided a `docker-compose.yaml` file that simplifies the setup.

### Starting the Scanner (Background):
```bash
docker-compose up -d scanner
```

### Starting the Paper Bot:
If you want to run the execution bot instead of the scanner, uncomment the `bot` section in `docker-compose.yaml` and run:
```bash
docker-compose up -d bot
```

## 5. Persistence
The system is configured to use **Volumes**. This means your trade data (`data/`) and your notification history (`logs/`) are stored on the VM itself, not just inside the container. If you update the code or restart the container, your data will **not** be lost.

## 6. Monitoring
- **Check Logs**: `docker-compose logs -f scanner`
- **Stop Everything**: `docker-compose down`
- **Check Status**: `docker-compose ps`

## 6. Security Note
Never commit your `.env` file to a public repository. The `.dockerignore` file ensures your local secrets stay local.
