# DELTA Plant

### AI Plant Health and Robotics Orchestrator for Precision Agriculture

<p align="center">
  <a href="https://proctor81.github.io/DELTA-PLANT/">
    <img src="https://img.shields.io/badge/Live%20Demo-GitHub%20Pages-19f5c1?style=for-the-badge&logo=githubpages&logoColor=06131f" alt="Live Demo" />
  </a>
  <a href="https://t.me/DELTAPLANO_bot">
    <img src="https://img.shields.io/badge/Access-DELTAPLANO-79e7ff?style=for-the-badge&logo=telegram&logoColor=06131f" alt="Access DELTAPLANO" />
  </a>
  <a href="https://github.com/proctor81/delta-plant">
    <img src="https://img.shields.io/badge/GitHub-Repository-0f172a?style=for-the-badge&logo=github&logoColor=ffffff" alt="GitHub Repository" />
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-2563eb?logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/Platform-Raspberry%20Pi%205-dc2626?logo=raspberrypi&logoColor=white" alt="Raspberry Pi 5" />
  <img src="https://img.shields.io/badge/AI-Hybrid%20Edge%20Vision-0ea5e9" alt="Hybrid Edge Vision" />
  <img src="https://img.shields.io/badge/XAI-LayerCAM-f59e0b" alt="LayerCAM" />
  <img src="https://img.shields.io/badge/Classes-33%20PlantVillage-10b981" alt="33 Plant Classes" />
  <img src="https://img.shields.io/badge/Version-v3.2-22c55e" alt="Version 3.2" />
</p>

DELTA Plant is a premium deep-tech platform for AI plant health diagnostics, explainable edge vision, robotics orchestration, and precision agriculture workflows. It unifies leaf disease detection, sensor-aware reasoning, agronomic recommendations, DELTAPLANO conversational access, and deployment-ready operations for Raspberry Pi 5.

Built for researchers, agritech teams, biotech innovators, and venture capital audiences, DELTA Plant presents a differentiated narrative: cinematic product experience on GitHub Pages, production-oriented edge AI in the repository, and a clear bridge between research credibility and operational usability.

## Website Preview

The repository now includes a GitHub Pages-ready landing page in [index.html](index.html) with a cinematic space-meets-biology visual language, animated hero scene, ambient soundtrack controls, investor-facing storytelling, structured SEO metadata, and direct DELTAPLANO access.

<p align="center">
  <a href="https://proctor81.github.io/DELTA-PLANT/">
    <img src="https://img.shields.io/badge/%F0%9F%8C%90%20Live%20Demo-Open%20GitHub%20Pages-19f5c1?style=for-the-badge&logo=githubpages&logoColor=06131f" alt="Live Demo" />
  </a>
</p>

![DELTA Plant Website Preview](https://www.image2url.com/r2/default/images/1778746172507-65d54433-1fec-459e-808b-141f7769e16c.png)

| Preview Layer | What it Communicates |
| --- | --- |
| Hero experience | AI Plant Health, DELTAPLANO access, deep-tech visual identity, edge benchmarking, and cinematic motion design |
| Technology section | EfficientFormerV2-S1, LayerCAM explainability, hybrid edge vision, sensor fusion, and orchestration architecture |
| Demo and docs surface | Telegram bot, benchmark visibility, manual, model card, release notes, and GitHub repository pathways |

## Why DELTA Plant

- Edge-native AI plant health platform for real-world agritech environments
- Hybrid visual intelligence with MobileNetV2 production baseline and EfficientFormerV2-S1 optional backend
- Explainable AI with LayerCAM overlays for clearer diagnostics and stakeholder trust
- DELTAPLANO Telegram access for conversational operations and rapid field usage
- Sensor fusion, expert rules, quantum-inspired risk scoring, and agronomic recommendations
- GitHub Pages storytelling optimized for AI search, deep-tech discovery, and investor visibility

## Public Benchmark Snapshot

DELTA Plant publicly highlights a 600-image, 33-class PlantVillage validation sample as the main benchmark reference surface.

| Metric | Value |
| --- | --- |
| Public sample | 600 validation images |
| Coverage | 33 plant classes |
| General model top-1 accuracy | 89.33% |
| General model top-3 accuracy | 99.00% |
| EfficientFormer document estimate | 92.91% top-1 / 100.00% top-3 |
| Mean edge latency | 41.360 ms on Raspberry Pi 5 |

Reference artifacts:

- [Public benchmark report](logs/vision_eval/public_600_dual/BENCHMARK_600.md)
- [Benchmark summary JSON](logs/vision_eval/public_600_dual/comparison_summary.json)
- [Model card](MODEL_CARD.md)
- [Release notes](RELEASE.md)

## Core Technology

| Layer | DELTA Plant Capability |
| --- | --- |
| Edge vision | MobileNetV2 baseline plus EfficientFormerV2-S1 TFLite pipeline |
| Explainability | LayerCAM heatmaps and overlays for plant diagnosis interpretation |
| Orchestration | DELTA agent coordinating vision, sensors, diagnosis, and recommendations |
| Interfaces | GitHub Pages, DELTAPLANO bot, CLI, admin panel, optional REST API |
| Sensor intelligence | Temperature, humidity, pressure, light, CO2, pH, and EC |
| MLOps pipeline | Training, export, evaluation, benchmarking, dissemination, manual regeneration |

## Product Highlights

- AI Plant Health landing page engineered for GitHub Pages and search visibility
- DELTAPLANO bot entry point for frictionless conversational interaction
- LayerCAM-powered explainable diagnosis with overlay-ready visual outputs
- Public benchmark storytelling aligned with v3.2 documentation surfaces
- Research-to-deployment positioning for agritech, biotech, and deep-tech narratives
- Edge execution pathway centered on Raspberry Pi 5 operations

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --preflight --enable-api --enable-telegram --daemon
```

To preview the landing page locally:

```bash
python -m http.server 8080
```

Then open `http://localhost:8080` and browse the landing page from [index.html](index.html).

## Documentation Hub

- [Live website](https://proctor81.github.io/DELTA-PLANT/)
- [Access DELTAPLANO](https://t.me/DELTAPLANO_bot)
- [User manual PDF](Manuale/DELTA_Manuale_Utente.pdf)
- [Technical architecture](Manuale/DELTA_3.0_ARCHITECTURE.md)
- [Model card](MODEL_CARD.md)
- [Release notes](RELEASE.md)
- [DELTA Orchestrator README](README_DELTA_ORCHESTRATOR.md)
- [LLM chat README](README_LLM_CHAT.md)

## Repository Structure

```text
ai/                 Training, export, evaluation, and TFLite tooling
core/               Runtime configuration and orchestrator logic
diagnosis/          Expert rules and diagnostic engine
interface/          CLI, admin panel, API, and Telegram integration
Manuale/            PDF manual generator and technical architecture docs
tools/              Benchmarking, dissemination, and pipeline automation
vision/             Vision backends including EfficientFormer classifier
index.html          Premium GitHub Pages landing page
```

## Audience Fit

DELTA Plant is designed to resonate with multiple high-value audiences without diluting the technical substance:

- Venture capital and deep-tech investors evaluating defensible AI infrastructure
- AI researchers exploring explainable edge vision and deployment realism
- Agritech and biotech teams looking for operational plant intelligence workflows
- Precision agriculture operators seeking interpretable, portable diagnostics

## Deployment Notes

The landing page is intentionally built with plain HTML, Tailwind CSS via CDN, custom CSS, and vanilla JavaScript so it can deploy directly on GitHub Pages without a build step.

The repository also includes a GitHub Actions workflow that republishes a minimal `gh-pages` branch whenever the landing page files or social preview assets change on `main`.

## License

See [LICENSE](LICENSE) for repository terms.
