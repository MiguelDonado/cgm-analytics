# CI/CD

**CI/CD** is three ideas stacked on top of each other. Each one automates one
more step between "I changed the code" and "the new version is running":

```
change → CI: build + test → Continuous Delivery: publish → Continuous Deployment: run it
         (every push/PR)    (a ready-to-run artifact)     (installed with no manual step)
```

| Term | What's automated | Ends with | In this project |
|---|---|---|---|
| **Continuous Integration** | Checking every change: lint, tests, builds | ✓ or ✗ on the push / PR | `.github/workflows/ci.yml` |
| **Continuous Delivery** | Producing a release anyone can run | An image in a registry (Docker Hub), ready to pull | Publishing the dashboard image |
| **Continuous Deployment** | Putting that release into a running environment | The new version running, with no manual step | The live dashboard: Posit Connect Cloud republishes it on every merge into `main` |

The "CD" in CI/CD can mean either of the last two. The difference is the last
step: with **delivery**, a person decides when to install the new version
(e.g. `docker compose pull && docker compose up -d`); with **deployment**, the
pipeline does it on its own.

## Continuous Deployment: the live dashboard

The online dashboard is deployed automatically (see `deployment.md`):

```
merge PR into main  →  Connect Cloud: pull the repo, rebuild from manifest.json  →  new version live
```

- **No GitHub Actions workflow for this step.** Connect Cloud watches the repo
  itself and republishes when `main` changes. CI runs on the PR before the
  merge, so only changes that passed CI reach `main`.
- **It doesn't use the Docker Hub image.** Connect Cloud builds the app from
  the code and `dashboard/manifest.json`. So delivery (the image, for running
  the project locally or anywhere with Docker) and deployment (the live app)
  are two separate paths from the same repo.
- **Package changes need a new manifest.** If the dashboard's packages change,
  run `rsconnect::writeManifest()` again and commit the result (see
  `deployment.md`). Otherwise the deployment fails with
  `there is no package called ...`.

The Airflow side is still updated by hand: it runs on the laptop, so a pipeline
change needs `astro dev restart`.