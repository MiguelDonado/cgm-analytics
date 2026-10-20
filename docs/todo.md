# Pending

1. Record video walkthrough
2. Record video setup and usage
3. CI/CD pipeline.

## CI/CD (GitHub Actions)

One PR per step, so the history shows the pipeline growing. CI uses fixture
readings only: never call LibreLinkUp or touch real glucose data.

- [ ] **Extras.** Dependabot (pip, GitHub Actions, Docker), branch protection
  requiring CI to pass, a reusable workflow / composite action for the uv
  setup, CodeQL and `trivy` image scanning, status badges in the README.
- [ ] **Publish the images.** Push them to Docker Hub, or ship the whole
  Compose project.

