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
| **Continuous Deployment** | Putting that release into a running environment | The new version running, with no manual step | Not used: the stack runs on the laptop and is updated by hand (`astro dev restart`) |

The "CD" in CI/CD can mean either of the last two. The difference is the last
step: with **delivery**, a person decides when to install the new version
(e.g. `docker compose pull && docker compose up -d`); with **deployment**, the
pipeline does it on its own.