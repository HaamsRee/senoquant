# API Reference

This page is generated automatically from docstrings using `mkdocstrings`.

## Package Overview

::: senoquant
    options:
      members: false

## Core Components

### Main Widget

::: senoquant._widget.SenoQuantWidget

### Utilities

::: senoquant.utils

## Reader

::: senoquant.reader.core
    options:
      filters:
        - "!^_"

## Segmentation

### Backend

::: senoquant.tabs.segmentation.backend

### Models Base Classes

::: senoquant.tabs.segmentation.models.base

### Model Implementations

::: senoquant.tabs.segmentation.models.cpsam.model

::: senoquant.tabs.segmentation.models.default_2d.model

::: senoquant.tabs.segmentation.models.default_3d.model

::: senoquant.tabs.segmentation.models.nuclear_dilation.model

::: senoquant.tabs.segmentation.models.perinuclear_rings.model

## Spot Detection

### Backend

::: senoquant.tabs.spots.backend

### Detector Base Classes

::: senoquant.tabs.spots.models.base

### Detector Implementations

::: senoquant.tabs.spots.models.udwt.model

::: senoquant.tabs.spots.models.rmp.model

## Quantification

### Backend

::: senoquant.tabs.quantification.backend

### Features Base Classes

::: senoquant.tabs.quantification.features.base

### ROI Configuration

::: senoquant.tabs.quantification.features.roi

### Marker Feature

::: senoquant.tabs.quantification.features.marker.config

::: senoquant.tabs.quantification.features.marker.feature

::: senoquant.tabs.quantification.features.marker.export
    options:
      filters:
        - "!^_"

::: senoquant.tabs.quantification.features.marker.morphology
    options:
      filters:
        - "!^_"

::: senoquant.tabs.quantification.features.marker.thresholding
    options:
      filters:
        - "!^_"

### Spots Feature

::: senoquant.tabs.quantification.features.spots.config

::: senoquant.tabs.quantification.features.spots.feature

::: senoquant.tabs.quantification.features.spots.export
    options:
      filters:
        - "!^_"

::: senoquant.tabs.quantification.features.spots.morphology
    options:
      filters:
        - "!^_"

## Batch Processing

### Backend

::: senoquant.tabs.batch.backend
    options:
      filters:
        - "!^_"

### Configuration

::: senoquant.tabs.batch.config
    options:
      filters:
        - "!^_"

### I/O Utilities

::: senoquant.tabs.batch.io
    options:
      filters:
        - "!^_"

### Viewer Shim

::: senoquant.tabs.batch.layers

## Settings

::: senoquant.tabs.settings.backend
