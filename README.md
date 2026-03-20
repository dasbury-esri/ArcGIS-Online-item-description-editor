# AGO Item Description Editor

This repository contains an ArcGIS Online notebook workflow for scanning, reviewing, and updating the Terms of Use section of ArcGIS Online items at scale.

The workflow is designed to help identify outdated or unwanted text and HTML in the `licenseInfo` field, review proposed replacements safely, and then apply updates only after confirmation.

## Repository Contents

- `AGO_Item_Description_Editor.ipynb`: main notebook workflow
- `helper_functions.py`: shared helper functions used by the notebook
- `Esri_ToU.html`: canonical replacement HTML used by the dry-run and update steps

## ArcGIS Online Notebook

Placeholder link:

- [ArcGIS Online notebook link goes here](https://example.com/replace-with-arcgis-notebook-link)

## Typical Workflow

1. Set up and authenticate.
2. Scan content for target strings or HTML.
3. Save or reload scan results.
4. Build and export a dry-run plan.
5. Create and review the HTML comparison report.
6. Apply updates after explicit confirmation.
7. Export final success and error results.

## Notes

- In ArcGIS Online, keep `helper_functions.py` available in `/arcgis/home` alongside the notebook.
- The notebook defaults to a dedicated output folder so generated files are easier to find.
- Review the dry-run output and report before applying any updates.