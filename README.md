# AGO Item Description Editor

This repository contains an ArcGIS Online notebook workflow for scanning, reviewing, and updating the Terms of Use section of ArcGIS Online item description pages at scale.

The workflow is designed to help identify outdated or unwanted text and HTML in the `licenseInfo` field, review proposed replacements safely, and apply updates only after confirmation.

## Which Notebook To Use

- `AGO_Item_Description_Editor.ipynb`: source notebook for development and maintenance
- `Bulk editor for ArcGIS Online Item Description pages.ipynb`: portable notebook for sharing with other users; it bootstraps `helper_functions.py` and `Esri_ToU.html` automatically during Step 1

Use the source notebook when you are editing logic, refining UX, or updating the workflow.

Use the portable notebook when you want a single file that can be shared and run more consistently in ArcGIS Online.

## Repository Contents

- `AGO_Item_Description_Editor.ipynb`: source notebook
- `Bulk editor for ArcGIS Online Item Description pages.ipynb`: generated portable notebook
- `helper_functions.py`: shared helper functions used by the source notebook
- `Esri_ToU.html`: canonical replacement HTML used by the dry-run and update steps
- `scripts/generate_bootstrap_notebook.py`: generator script for rebuilding the portable notebook from the source files

## ArcGIS Online Notebook

Placeholder link:

- [ArcGIS Online notebook link goes here](https://example.com/replace-with-arcgis-notebook-link)

## Typical Workflow

1. Set up and authenticate.
2. Scan content for target strings or HTML.
3. Save or reload scan results.
4. Do a dry-run to build and export a HTML review page.
5. Review the HTML comparison report. After checking the items you want to edit, export those items as JSON.
6. Import the JSON file back to the notebook.
7. Apply updates only after explicit confirmation.
8. Export final success and error results.

## Regenerating The Portable Notebook

If you update the source notebook, helper module, or canonical HTML file, regenerate the portable notebook with:

```bash
python scripts/generate_bootstrap_notebook.py
```

This rebuilds `Bulk editor for ArcGIS Online Item Description pages.ipynb` from the current repo state.

## Notes

- The source notebook expects `helper_functions.py` to be available in the runtime environment.
- The portable notebook writes its bundled assets into the runtime automatically during Step 1.
- The workflow defaults to a dedicated output folder so generated files are easier to find.
- Review the dry-run output and report before applying any updates.