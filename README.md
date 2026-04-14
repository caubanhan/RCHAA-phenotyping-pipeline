# RCHAA phenotyping pipeline

## Overview
RCHAA phenotyping pipeline is a customized research software system for plant root phenotyping experiments in the RCHAA biotechnology lab at HCMUS, Vietnam. It is designed for high-throughput Petri dish studies, where image and time-series measurements are collected at scale and converted into structured analytical outputs.

The pipeline supports automated and semi-automated operating modes, allowing teams to balance throughput and expert oversight depending on experiment goals, data quality, and quality-control policies.

## Key Features
- End-to-end workflow for large-scale root phenotyping experiments.
- High-throughput batch execution for multi-sample and multi-timepoint studies.
- Unified handling of image sequences and temporal growth data.
- Reproducible processing flow with standardized outputs for downstream analysis.
- Modular architecture that supports configurable automation levels.
- Designed for real lab operations, including iterative experimental cycles.

## Use Case in RCHAA Lab Context
In RCHAA lab operations, experiments often involve many Petri dishes across treatment groups and observation intervals. The pipeline enables consistent processing across these datasets, reducing manual bottlenecks and improving comparability between runs.

This supports two core objectives:
- Reliable extraction of phenotype-relevant measurements from large imaging campaigns.
- Reproducible data organization for statistical analysis, reporting, and cross-experiment validation.

## System Pipeline
The system follows a staged architecture from raw experimental input to analysis-ready outputs.

```text
┌─────────────────────────────────────────────┐
│            Raw Petri Dish Images            │
├─────────────────────────────────────────────┤
│ • Time-series images of plant growth        │
│ • Captured from controlled experiments      │
└─────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│              Image Segmentation             │
├─────────────────────────────────────────────┤
│ • Plant/root region extraction              │
│ • Background removal / masking              │
│ • Preparation for quantitative analysis     │
└─────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│          Batch Feature Extraction           │
├─────────────────────────────────────────────┤
│ • Morphological measurements                │
│ • Root growth descriptors (time-series)     │
│ • Automated processing across samples       │
└─────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│             Dataset Generation              │
├─────────────────────────────────────────────┤
│ • Structured tabular datasets               │
│ • Time-series feature tables                │
│ • Export for downstream analysis            │
└─────────────────────────────────────────────┘
```

## Future Improvements
- Expanded support for additional crop and experimental protocols.
- Stronger experiment tracking and provenance auditing.
- Enhanced quality-control dashboards for run monitoring.
- Deeper integration with statistical and visualization workflows.
- Improved interoperability with institutional data management systems.

## Author Note
This repository documents an actively used lab pipeline developed to support real-world phenotyping operations in a biotechnology research environment.
